from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# Association table for Characters appearing in Pages (Many-to-Many)
page_characters = db.Table('page_characters',
    db.Column('page_id', db.Integer, db.ForeignKey('page.id'), primary_key=True),
    db.Column('character_id', db.Integer, db.ForeignKey('character.id'), primary_key=True)
)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    true_name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    aliases = db.relationship('Alias', backref='user', lazy=True)

class Alias(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    pages = db.relationship('Page', backref='author_alias', lazy=True)

class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    title = db.Column(db.String(200)) # Optional title
    books = db.relationship('Book', backref='game', lazy=True)

    @property
    def display_title(self):
        if self.title:
            return self.title
        return f"Game Night {self.date.strftime('%m/%d/%Y')}"

    def get_preview_image(self):
        # Defaults to the first image panel of the first book
        if self.books:
            first_book = self.books[0]
            first_img = first_book.get_first_image_page()
            if first_img:
                return first_img.content_url
        return "/static/default_game.png"

class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    # Order pages by sequence number
    pages = db.relationship('Page', backref='book', lazy='dynamic', order_by='Page.sequence')

    def get_first_text_page(self):
        return self.pages.filter_by(type='text').first()

    def get_first_image_page(self):
        return self.pages.filter_by(type='image').first()

class Page(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    alias_id = db.Column(db.Integer, db.ForeignKey('alias.id'), nullable=False)
    
    sequence = db.Column(db.Integer, nullable=False) # 1, 2, 3...
    type = db.Column(db.String(10), nullable=False) # 'text' or 'image'
    content_text = db.Column(db.Text) # Null if image
    content_url = db.Column(db.String(200)) # Null if text

    # For image pages that feature characters
    characters = db.relationship('Character', secondary=page_characters, lazy='subquery',
        backref=db.backref('pages', lazy=True))

class Character(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    image_url = db.Column(db.String(200))

class AdminKey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key_name = db.Column(db.String(50)) # e.g., "Main Admin"
    hash = db.Column(db.String(255), nullable=False)

    def set_key(self, plain_key):
        self.hash = generate_password_hash(plain_key)

    def check_key(self, plain_key):
        return check_password_hash(self.hash, plain_key)