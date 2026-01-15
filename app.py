from flask import Flask, render_template, request, abort
from models import db, User, Alias, Game, Book, Page, Character
from sqlalchemy import or_

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

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)