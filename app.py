from flask import Flask, render_template, request, abort, session, redirect, url_for, flash, copy_current_request_context, jsonify
from models import db, User, Alias, Game, Book, Page, Character, AdminKey, DailyChallenge, page_characters
from sqlalchemy import Engine, or_, Date, event, func, text
from sqlalchemy.exc import IntegrityError
from functools import wraps
import os
from datetime import datetime, date
import random
import uuid
from import_bpp import process_html_content
import json
from b2blaze import upload_b64img_to_b2, delete_b2_file
from dotenv import load_dotenv
import base64
import threading
import pytz
import gc

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
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_size": 5,
    "max_overflow": 0 # don't allow extra connections beyond pool_size
}
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-for-sessions')
app.config['MAX_CONTENT_LENGTH'] = 25 * 1024 * 1024  # 25 MB upload limit
db.init_app(app)

@app.route('/')
def index():
    # Show the 3 most recent games at the top
    recent_games = Game.query.order_by(Game.date.desc()).limit(4).all()

    # Get today's challenge ID to pass to the JS
    tz = pytz.timezone('America/New_York')
    today_date = datetime.now(tz).date()
    challenge = DailyChallenge.query.filter_by(date=today_date).first()
    challenge_id = challenge.id if challenge else None

    return render_template('index.html', recent_games=recent_games, challenge_id=challenge_id)

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

    # 4. Games by Title
    games = Game.query.filter(Game.title.ilike(f'%{query}%')).all()

    return render_template('search.html', query=query, books=books, characters=characters, users=users, games=games)

@app.route('/panel/<int:page_id>')
def panel_detail(page_id):
    panel = Page.query.get_or_404(page_id)

    all_characters = []
    # Don't load all characters unless admin, save bandwidth
    if session.get('is_admin'):
        all_characters = Character.query.order_by(Character.name).all()
    return render_template('panel_detail.html', panel=panel, all_characters=all_characters)

@app.route('/panel/random')
def panel_random():
    # This just loads the empty "shell" page
    return render_template('panel_random.html')

@app.route('/api/panel/random')
def api_panel_random():
    untagged_only = request.args.get('untagged', 'false').lower() == 'true'

    # Get a random panel
    panel = Page.query.filter(Page.type == 'image')

    if untagged_only:
        panel = panel.filter(~Page.characters.any())

    panel = panel.order_by(func.random()).first()
    
    if not panel:
        return jsonify({"error": "No panels found"}), 404

    # Prepare data for JSON
    return jsonify({
        "id": panel.id,
        "content_url": panel.content_url,
        "book_id": panel.book_id,
        "game_id": panel.book.game_id,
        "author": panel.author_alias.name,
        "author_id": panel.author_alias.user_id,
        "prompt": panel.book.pages[0].content_text, # The first text page
        "sequence": panel.sequence
    })

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
    
    # 1. Get the current page from the query string (default to 1)
    page_num = request.args.get('page', 1, type=int)
    
    # 2. Define how many drawings to show per page
    per_page = 20 
    
    # 3. Get alias IDs
    aliases_ids = [a.id for a in user.aliases]
    
    # 4. Change .all() to .paginate()
    # This returns a Pagination object instead of a list
    drawings_pagination = Page.query\
        .join(Book, Page.book_id == Book.id)\
        .join(Game, Book.game_id == Game.id)\
        .filter(
            Page.alias_id.in_(aliases_ids), 
            Page.type == 'image'
        )\
        .order_by(Game.date.desc(), Page.id.desc())\
        .paginate(page=page_num, per_page=per_page, error_out=False)
    
    return render_template('user_detail.html', 
                           user=user, 
                           drawings=drawings_pagination)

@app.route('/characters')
def character_list():
    page = request.args.get('page', 1, type=int)
    # Sort by name alphabetically
    pagination = characters_with_counts = db.session.query(
        Character, 
        func.count(Page.id).label('appearance_count')
    ).outerjoin(Character.pages) \
     .group_by(Character.id) \
     .order_by(func.count(Page.id).desc()) \
     .paginate(
        page=page, per_page=18, error_out=False
    )
    characters = pagination.items
    return render_template('character_list.html', characters=characters, pagination=pagination)

@app.route('/character/<int:char_id>')
def character_detail(char_id):
    character = Character.query.get_or_404(char_id)
    
    # Get current page from URL
    page_num = request.args.get('page', 1, type=int)
    per_page = 15  # 5 columns x 3 rows looks great on a grid
    
    # Query Pages that are associated with this character
    # We use .any(id=char_id) for many-to-many relationships
    pagination = Page.query.filter(Page.characters.any(id=char_id)) \
        .order_by(Page.id.desc()) \
        .paginate(page=page_num, per_page=per_page, error_out=False)
        
    return render_template('character_detail.html', 
                           character=character, 
                           drawings=pagination)

@app.route('/daily')
def daily_game():
    tz = pytz.timezone('America/New_York')
    today_date = datetime.now(tz).date()

    # 1. Check if the challenge already exists
    challenge = DailyChallenge.query.filter_by(date=today_date).first()

    if not challenge:
        # 2. Convert date to a float between -1 and 1 for Postgres setseed()
        # We use the integer timestamp and a bit of math to generate a seed
        seed_value = int(today_date.strftime('%Y%m%d')) / 100000000.0
        
        # 3. Set the seed in the current database session
        db.session.execute(text(f"SELECT setseed({seed_value})"))

        # 4. Use the DB to pick the panel. 
        # Because the seed is set, func.random() will return the SAME panel for this date.
        sql_query = text("""
            select p.*
            from page p
            join alias a on a.id = p.alias_id
            where p.type = 'image'
            and a.user_id is not null
            and not exists (
                select 1
                from page_characters pc
                where pc.page_id = p.id
                and (pc.character_id = 164 or pc.character_id = 169 or pc.character_id = 253)
            )
            order by random()
            limit 1;
        """)

        daily_panel = db.session.execute(sql_query).fetchone()

        if daily_panel:
            new_challenge = DailyChallenge(date=today_date, page_id=daily_panel.id)
            db.session.add(new_challenge)
            try:
                db.session.commit()
                challenge = new_challenge
            except IntegrityError:
                # Someone else's request finished a millisecond faster
                db.session.rollback()
                challenge = DailyChallenge.query.filter_by(date=today_date).first()

    # 3. Use the stored panel
    panel = challenge.panel
    
    # Get the first text prompt for the clue
    first_prompt = Page.query.filter_by(book_id=panel.book_id, type='text')\
                             .order_by(Page.sequence.asc()).first()
    
    correct_author_id = panel.author_alias.user_id if panel.author_alias else None

    authors = db.session.query(User.id, User.true_name).all()
    # sort authors by true_name
    authors = sorted(authors, key=lambda u: u.true_name.lower())
    
    return render_template('daily.html', 
                           panel=panel, 
                           challenge=challenge,
                           correct_author_id=correct_author_id,
                           first_prompt=first_prompt, 
                           authors=authors)

# Decorator to protect admin routes
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            return "Unauthorized", 401
        return f(*args, **kwargs)
    return decorated_function

# 1. The "Login" Route - Now handles the POST from your Navbar
@app.route('/admin/auth', methods=['POST'])
def admin_auth():
    # Use .form.get because the navbar uses a POST form
    key = request.form.get('admin_key') 
    
    all_keys = AdminKey.query.all()
    for admin_key in all_keys:
        if admin_key.check_key(key):
            session['is_admin'] = True
            session.permanent = True # Keeps you logged in for a while
            flash("Admin access granted.")
            # Redirect back to where you were, or dashboard if unknown
            return redirect(url_for('admin_dashboard'))
    
    flash("Invalid Admin Key.")
    return redirect(url_for('index'))

# 2. The Dashboard
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    # needs to try to login here

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

    # sort users by true_name
    existing_users = sorted(existing_users, key=lambda u: u.true_name.lower())
    
    return render_template('admin/import_map.html', 
                           authors=sorted(list(found_authors)), 
                           users=existing_users)

@app.route('/admin/import/step2', methods=['POST'])
@admin_required
def import_step2():
    temp_filename = session.get('temp_game_data_file')
    if not temp_filename: return "Session expired", 400
    temp_filepath = os.path.join('instance', 'temp', temp_filename)
    
    with open(temp_filepath, 'r') as f:
        game_data = json.load(f)
    
    mapping = request.form.to_dict()
    
    # --- PRE-PROCESS USERS (Do this in the main thread to get IDs) ---
    user_map = {} # Maps author_name string to Alias.id
    for author_name, choice in mapping.items():
        if choice == 'NEW':
            u = User(true_name=author_name)
            db.session.add(u)
            db.session.flush() # Now u.id exists
            alias = Alias(name=author_name, user_id=u.id)
        else:
            user_id = int(choice)
            alias = Alias.query.filter_by(name=author_name, user_id=user_id).first()
            if not alias:
                alias = Alias(name=author_name, user_id=user_id)
        
        db.session.add(alias)
        db.session.flush()
        user_map[author_name] = alias.id # Store the actual ID

    db.session.commit() # Save the users so the background thread can see them

    # 2. DEFINE THE BACKGROUND TASK
    @copy_current_request_context
    def run_combined_import(data, user_id_map, filepath):
        with app.app_context():
            try:
                # A. Parallel Uploads First
                image_tasks = []
                for b in data['books']:
                    for p in b['pages']:
                        if p['type'] == 'drawing':
                            b64_content = p['content']
                            b2_url = upload_b64img_to_b2(b64_content, folder='panels')
                            p['b2_url'] = b2_url

                # B. Database Insertion (Now fast since images are done)
                new_game = Game(date=datetime.fromisoformat(data['date']).date())
                db.session.add(new_game)
                db.session.flush()

                for book_data in data['books']:
                    new_book = Book(game_id=new_game.id)
                    db.session.add(new_book)
                    db.session.flush()

                    for page_data in book_data['pages']:
                        p_type = 'image' if page_data['type'] == 'drawing' else 'text'
                        content = page_data.get('b2_url') if p_type == 'image' else page_data['content']

                        new_page = Page(
                            book_id=new_book.id,
                            alias_id=user_id_map[page_data['author']],
                            sequence=page_data['sequence'],
                            type=p_type,
                            content_text=content if p_type == 'text' else None,
                            content_url=content if p_type == 'image' else None
                        )
                        db.session.add(new_page)
                
                db.session.commit()
                
                # Explicitly clean up
                del data
                db.session.remove()
                gc.collect() # Force Python to release memory back to the OS
                
            except Exception as e:
                print(f"ASYNC IMPORT ERROR: {e}")
                db.session.rollback()
            finally:
                if os.path.exists(filepath):
                    os.remove(filepath)

    # 3. FIRE AND FORGET
    thread = threading.Thread(target=run_combined_import, args=(game_data, user_map, temp_filepath))
    thread.start()

    flash("Background import started! Check back in a few seconds.")
    return redirect(url_for('admin_dashboard'))

# 4. Manage Keys
@app.route('/admin/keys/add', methods=['POST'])
@admin_required
def add_admin_key():
    name = request.form.get('name')
    plain_key = request.form.get('key').strip()
    
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

    # 1. Get the current page from the URL (?page=1)
    page = request.args.get('page', 1, type=int)
    per_page = 25  # Keep this low for the Free Tier memory limit

    # 2. Use paginate instead of all()
    # error_out=False prevents 404s if a user enters a page that doesn't exist
    pagination = model.query.order_by(model.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    items = pagination.items
    columns = model.__table__.columns.keys()

    return render_template(
        'admin/table_view.html', 
        table_name=table_name, 
        items=items, 
        columns=columns, 
        pagination=pagination # Pass the whole pagination object to the HTML
    )
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

@app.route('/admin/add-character', methods=['POST'])
@admin_required
def add_character():
    name = request.form.get('name')
    panel = request.form.get('page_id')

    if not name or not panel:
        flash("Name and panel are required!")
        return redirect(request.referrer)

    # check if character with same name exists
    character = Character.query.filter_by(name=name).first()
    page = Page.query.get(panel)

    if not page:
        flash("Invalid panel specified!")
        return redirect(request.referrer)

    character_exists = character is not None

    if character_exists:
        if character not in page.characters:
            page.characters.append(character)
    else:
        character = Character(name=name, image_url="")
        db.session.add(character)

        character.pages.append(page)

    db.session.commit()

    # Check if request is AJAX
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            "id": character.id,
            "name": character.name,
            "imgSrc": character.image_url if character_exists else None
        })

    return redirect(url_for('panel_detail', page_id=request.form.get('page_id')))

@app.route('/admin/tag-character', methods=['POST'])
@admin_required
def tag_character():
    page_id = request.form.get('page_id')
    char_id = request.form.get('character_id')
    
    if not page_id or not char_id:
        flash("Missing page or character ID!")
        return redirect(request.referrer)

    panel = Page.query.get(page_id)
    character = Character.query.get(char_id)
    
    if panel and character and character not in panel.characters:
        panel.characters.append(character)
        db.session.commit()
    
        # Check if request is AJAX
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                "status": "success",
                "id": character.id,
                "name": character.name,
                "imgSrc": character.image_url
            })

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
    new_url = upload_b64img_to_b2(b64_string, folder=model_type + 's') # Organize by model type in B2

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

@app.route('/admin/edit-game-video/<int:game_id>', methods=['POST'])
@admin_required
def edit_game_video(game_id):
    game = Game.query.get_or_404(game_id)
    new_video_link = request.form.get('video_link')
    
    game.video_link = new_video_link.strip() if new_video_link else None
    db.session.commit()
    flash("Game video link updated!")
    
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