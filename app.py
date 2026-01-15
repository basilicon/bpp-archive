from flask import Flask, render_template, request, abort, session, redirect, url_for, flash
from models import db, User, Alias, Game, Book, Page, Character, AdminKey
from sqlalchemy import Engine, or_, Date, event
from functools import wraps
import os
from datetime import datetime
import uuid
from import_bpp import process_html_content
import json
from b2blaze import upload_b64img_to_b2, delete_b2_file
from dotenv import load_dotenv
import base64

load_dotenv()

app = Flask(__name__)

# Get the database URL from environment variables (Render will provide this)
# If no URL is found, fall back to your local SQLite file
database_url = os.environ.get('DATABASE_URL')

if database_url:
    # Fix for Render/Supabase: they often provide 'postgres://' 
    # but SQLAlchemy 1.4+ requires 'postgresql://'
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///brokenpicturephone.db'

# Important for Postgres: prevents connection timeout issues
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {"pool_pre_ping": True}
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-for-sessions')
db.init_app(app)

@app.route('/')
def index():
    # Show the 3 most recent games at the top
    recent_games = Game.query.order_by(Game.date.desc()).limit(3).all()
    return render_template('index.html', recent_games=recent_games)

@app.route('/search')
def search():
    query = request.args.get('q', '')
    if not query:
        return render_template('search.html')

    # Search Logic
    # 1. Books by first text page
    books = Book.query.join(Page).filter(
        Page.type == 'text',
        Page.sequence == 1,
        Page.content_text.ilike(f'%{query}%')
    ).all()
    
    # 2. Characters by name
    characters = Character.query.filter(Character.name.ilike(f'%{query}%')).all()
    
    # 3. Users by True Name
    users = User.query.filter(User.true_name.ilike(f'%{query}%')).all()

    return render_template('search.html', query=query, books=books, characters=characters, users=users)

@app.route('/game/<int:game_id>')
def game_detail(game_id):
    game = Game.query.get_or_404(game_id)
    
    # Get all users involved in this game via their aliases in the pages
    # This is a complex join: Game -> Book -> Page -> Alias -> User
    involved_users = set()
    for book in game.books:
        for page in book.pages:
            if page.author_alias and page.author_alias.user:
                involved_users.add((page.author_alias.user, page.author_alias))
    
    return render_template('game_detail.html', game=game, participants=involved_users)

@app.route('/games')
def game_list():
    page = request.args.get('page', 1, type=int)
    sort = request.args.get('sort', 'desc') # 'desc' for newest first, 'asc' for oldest
    
    query = Game.query
    if sort == 'asc':
        query = query.order_by(Game.date.asc())
    else:
        query = query.order_by(Game.date.desc())
        
    pagination = query.paginate(page=page, per_page=10, error_out=False)
    games = pagination.items
    
    return render_template('game_list.html', 
                           games=games, 
                           pagination=pagination, 
                           current_sort=sort)

@app.route('/book/<int:book_id>')
def book_detail(book_id):
    book = Book.query.get_or_404(book_id)
    return render_template('book_detail.html', book=book)

@app.route('/user/<int:user_id>')
def user_detail(user_id):
    user = User.query.get_or_404(user_id)
    # Get all pages drawn by any of the user's aliases
    aliases_ids = [a.id for a in user.aliases]
    drawn_pages = Page.query.filter(Page.alias_id.in_(aliases_ids), Page.type == 'image').all()
    return render_template('user_detail.html', user=user, drawings=drawn_pages)

@app.route('/characters')
def character_list():
    page = request.args.get('page', 1, type=int)
    # Sort by name alphabetically
    pagination = Character.query.order_by(Character.name.asc()).paginate(
        page=page, per_page=12, error_out=False
    )
    characters = pagination.items
    return render_template('character_list.html', characters=characters, pagination=pagination)

@app.route('/character/<int:char_id>')
def character_detail(char_id):
    character = Character.query.get_or_404(char_id)
    return render_template('character_detail.html', character=character)

# Decorator to protect admin routes
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            return "Unauthorized", 401
        return f(*args, **kwargs)
    return decorated_function

# 1. The "Login" Route (Sync / Auth)
@app.route('/admin/auth')
def admin_auth():
    key = request.args.get('key')
    # Check all stored admin hashes
    all_keys = AdminKey.query.all()
    for admin_key in all_keys:
        if admin_key.check_key(key):
            session['is_admin'] = True
            flash("Admin access granted.")
            return redirect(url_for('admin_dashboard'))
    
    return "Invalid Key", 403

# 2. The Dashboard
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    return render_template('admin/dashboard.html', tables=MODEL_MAP.keys())

# 3. upload logic
@app.route('/admin/import/step1', methods=['POST'])
@admin_required
def import_step1():
    file = request.files.get('game_file')
    if not file: return "No file", 400
    
    # Use your existing process_html_content function
    html_content = file.read().decode('utf-8')
    game_data = process_html_content(html_content)
    
    # Extract unique authors from the parsed data
    found_authors = set()
    for book in game_data['books']:
        for page in book['pages']:
            found_authors.add(page['author'])
    
    # Store game data in session (Careful: sessions have size limits, 
    # for very large games, saving to a temp JSON file is better)
    # session['temp_game_data'] = game_data

    # Instead, save to a temp JSON file and store the filename in session
    temp_filename = f"temp_game_{uuid.uuid4()}.json"
    temp_filepath = os.path.join('instance', 'temp', temp_filename)
    os.makedirs(os.path.dirname(temp_filepath), exist_ok=True)
    with open(temp_filepath, 'w') as f:
        json.dump(game_data, f)
    session['temp_game_data_file'] = temp_filename
    
    # Fetch all existing users for the mapping dropdown
    existing_users = User.query.all()
    
    return render_template('admin/import_map.html', 
                           authors=sorted(list(found_authors)), 
                           users=existing_users)

@app.route('/admin/import/step2', methods=['POST'])
@admin_required
def import_step2():
    #game_data = session.get('temp_game_data')
    #if not game_data: return "Session expired", 400

    temp_filename = session.get('temp_game_data_file')
    if not temp_filename: return "Session expired", 400
    temp_filepath = os.path.join('instance', 'temp', temp_filename)
    if not os.path.exists(temp_filepath):
        return "Session expired", 400
    with open(temp_filepath, 'r') as f:
        game_data = json.load(f)

    # Get the mapping from the form: { 'AuthorName': 'user_id' or 'NEW' }
    mapping = request.form
    
    # 1. Process Game & Books
    new_game = Game(date=datetime.fromisoformat(game_data['date']).date())
    db.session.add(new_game)
    db.session.flush()

    user_cache = {} # Map author names to Alias objects

    for book_data in game_data['books']:
        new_book = Book(game_id=new_game.id)
        db.session.add(new_book)
        db.session.flush()

        for page_data in book_data['pages']:
            author_name = page_data['author']
            
            # 2. Handle the mapping/alias logic
            if author_name not in user_cache:
                choice = mapping.get(author_name) # returns user_id or 'NEW'
                
                if choice == 'NEW':
                    u = User(true_name=author_name)
                    db.session.add(u)
                    db.session.flush()
                    user_id = u.id
                else:
                    user_id = int(choice)

                # Find or create Alias for this user
                alias = Alias.query.filter_by(name=author_name, user_id=user_id).first()
                if not alias:
                    alias = Alias(name=author_name, user_id=user_id)
                    db.session.add(alias)
                    db.session.flush()
                user_cache[author_name] = alias

            # 3. Handle image saving to file system
            p_type = 'image' if page_data['type'] == 'drawing' else 'text'
            final_content = page_data['content']
            
            # Inside import_step2 loop
            if p_type == 'image':
                # Now returns a cloud URL instead of a local path
                final_content = upload_b64img_to_b2(page_data['content'])
            else:
                final_content = page_data['content']

            new_page = Page(
                book_id=new_book.id,
                alias_id=user_cache[author_name].id,
                sequence=page_data['sequence'],
                type=p_type,
                content_text=final_content if p_type == 'text' else None,
                content_url=final_content if p_type == 'image' else None # This is now the B2 URL
            )

            new_page = Page(
                book_id=new_book.id,
                alias_id=user_cache[author_name].id,
                sequence=page_data['sequence'],
                type=p_type,
                content_text=final_content if p_type == 'text' else None,
                content_url=final_content if p_type == 'image' else None
            )
            db.session.add(new_page)

    # lastly, remove the temp file and session key
    os.remove(temp_filepath)
    db.session.commit()
    session.pop('temp_game_data', None)
    flash("Game successfully imported with mapped users!")
    return redirect(url_for('admin_dashboard'))

# 4. Manage Keys
@app.route('/admin/keys/add', methods=['POST'])
@admin_required
def add_admin_key():
    name = request.form.get('name')
    plain_key = request.form.get('key')
    
    new_admin = AdminKey(key_name=name)
    new_admin.set_key(plain_key)
    db.session.add(new_admin)
    db.session.commit()
    return "Key Added"

# Map strings to models for dynamic routing
MODEL_MAP = {
    'users': User,
    'aliases': Alias,
    'games': Game,
    'books': Book,
    'pages': Page,
    'characters': Character,
    'admin_keys': AdminKey
}

@app.route('/admin/tables')
@admin_required
def list_tables():
    return render_template('admin/tables_list.html', tables=MODEL_MAP.keys())

@app.route('/admin/table/<table_name>')
@admin_required
def data_table_detail(table_name):
    model = MODEL_MAP.get(table_name)
    if not model:
        return "Table not found", 404
    items = model.query.all()
    # Get column names for the headers
    columns = model.__table__.columns.keys()
    return render_template('admin/table_view.html', table_name=table_name, items=items, columns=columns)

@app.route('/admin/table/<table_name>/edit/<int:item_id>', methods=['GET', 'POST'])
@app.route('/admin/table/<table_name>/add', methods=['GET', 'POST'])
@admin_required
def edit_item(table_name, item_id=None):
    model = MODEL_MAP.get(table_name)
    columns = [c for c in model.__table__.columns if not c.primary_key]
    item = model.query.get(item_id) if item_id else model()

    if request.method == 'POST':
        for col in columns:
            val = request.form.get(col.name)
            
            if val == "" or val is None:
                setattr(item, col.name, None)
                continue

            # --- THE FIX: Convert String to Date ---
            if isinstance(col.type, Date):
                try:
                    # HTML <input type="date"> sends YYYY-MM-DD
                    date_obj = datetime.strptime(val, '%Y-%m-%d').date()
                    setattr(item, col.name, date_obj)
                except ValueError:
                    flash(f"Invalid date format for {col.name}")
            else:
                setattr(item, col.name, val)
        
        if not item_id:
            db.session.add(item)
            
        db.session.commit()
        flash(f"Item in {table_name} updated!")
        return redirect(url_for('data_table_detail', table_name=table_name))

    return render_template('admin/edit_item.html', table_name=table_name, item=item, columns=columns)

@app.route('/admin/table/<table_name>/delete/<int:item_id>', methods=['POST'])
@admin_required
def delete_item(table_name, item_id):
    model = MODEL_MAP.get(table_name)
    item = model.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    flash("Item deleted.")
    return redirect(url_for('data_table_detail', table_name=table_name))

@app.route('/panel/<int:page_id>')
def panel_detail(page_id):
    panel = Page.query.get_or_404(page_id)
    all_characters = Character.query.order_by(Character.name).all()
    return render_template('panel_detail.html', panel=panel, all_characters=all_characters)

@app.route('/admin/tag-character', methods=['POST'])
@admin_required
def tag_character():
    page_id = request.form.get('page_id')
    char_id = request.form.get('character_id')
    
    panel = Page.query.get(page_id)
    character = Character.query.get(char_id)
    
    if panel and character and character not in panel.characters:
        panel.characters.append(character)
        db.session.commit()
        flash(f"Tagged {character.name}!")
    
    return redirect(url_for('panel_detail', page_id=page_id))

@app.route('/admin/untag-character', methods=['POST'])
@admin_required
def untag_character():
    page_id = request.form.get('page_id')
    char_id = request.form.get('character_id')
    
    panel = Page.query.get(page_id)
    character = Character.query.get(char_id)
    
    if panel and character and character in panel.characters:
        panel.characters.remove(character)
        db.session.commit()
        flash(f"Removed {character.name} from panel.")
    
    return redirect(url_for('panel_detail', page_id=page_id))

@app.route('/admin/update-image/<string:model_type>/<int:item_id>', methods=['POST'])
@admin_required
def update_image(model_type, item_id):
    # 1. Get the image from the form
    image_file = request.files.get('new_image')
    if not image_file:
        flash("No image selected!")
        return redirect(request.referrer)

    # 2. Upload to Backblaze B2
    # We convert the file to a base64-like string for our existing helper
    # or modify upload_to_b2 to accept raw bytes

    image_bytes = image_file.read()
    b64_string = base64.b64encode(image_bytes).decode('utf-8')
    new_url = upload_b64img_to_b2(b64_string)

    # 3. Update the Database
    if model_type == 'character':
        item = Character.query.get_or_404(item_id)
        item.image_url = new_url
        redirect_url = url_for('character_detail', char_id=item_id)
    elif model_type == 'game':
        item = Game.query.get_or_404(item_id)
        # We need a field to store an override image
        # Let's call it override_image_url
        item.override_image_url = new_url 
        redirect_url = url_for('game_list')
        
    db.session.commit()
    flash(f"Updated {model_type} image!")
    return redirect(redirect_url)

@app.route('/admin/edit-game-name/<int:game_id>', methods=['POST'])
@admin_required
def edit_game_name(game_id):
    game = Game.query.get_or_404(game_id)
    new_name = request.form.get('new_name')
    
    if new_name and new_name.strip():
        game.title = new_name.strip()
        db.session.commit()
        flash("Game title updated!")
    
    return redirect(url_for('game_detail', game_id=game.id))

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    flash("Logged out successfully.")
    return redirect(url_for('index'))

@event.listens_for(Page, 'after_delete')
def delete_page_file(mapper, connection, target):
    if target.type == 'image' and target.content_url:
        # delete from b2 using the URL
        delete_b2_file(target.content_url)

# We listen to the 'characters' attribute on the Page model
@event.listens_for(Page.characters, 'append')
def set_initial_character_image(target_page, value_character, initiator):
    """
    target_page: The Page (Panel) being tagged
    value_character: The Character being added to the panel
    """
    # Only proceed if the page is an image and the character has no image
    if target_page.type == 'image' and not value_character.image_url:
        value_character.image_url = target_page.content_url
        # No need to commit here; SQLAlchemy handles it in the current transaction

@app.context_processor
def utility_processor():
    return dict(getattr=getattr)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    app.run(debug=True, port=5001)