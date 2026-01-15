from flask import Flask, render_template, request, abort, session, redirect, url_for, flash
from models import db, User, Alias, Game, Book, Page, Character, AdminKey
from sqlalchemy import Engine, or_, Date, event
from functools import wraps
import os
from datetime import datetime
import uuid
import base64
from import_bpp import process_html_content
import json
from b2blaze import upload_b64img_to_b2, delete_b2_file

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///brokenpicturephone.db'
db.init_app(app)

@app.route('/')
def index():
    # Main page: Recent books and characters
    recent_books = Book.query.order_by(Book.id.desc()).limit(5).all()
    characters = Character.query.limit(5).all()
    return render_template('index.html', books=recent_books, characters=characters)

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

@event.listens_for(Page, 'after_delete')
def delete_page_file(mapper, connection, target):
    if target.type == 'image' and target.content_url:
        # delete from b2 using the URL
        delete_b2_file(target.content_url)

@app.context_processor
def utility_processor():
    return dict(getattr=getattr)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'secret_key_for_sessions')

    app.run(debug=True, port=5001)