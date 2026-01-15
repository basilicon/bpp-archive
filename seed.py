from app import app
from models import db, User, Alias, Game, Book, Page, Character
from datetime import date, timedelta

def seed_data():
    with app.app_context():
        # 1. Reset Database
        print("Dropping old database...")
        db.drop_all()
        print("Creating new database...")
        db.create_all()

        # 2. Create Users
        print("Seeding Users...")
        u1 = User(true_name="Alice_Artist", description="Loves drawing cats.")
        u2 = User(true_name="Bob_Builder", description="Terrible at drawing, great at captions.")
        u3 = User(true_name="Charlie_Chaos", description="Intentionally ruins the chain.")
        
        db.session.add_all([u1, u2, u3])
        db.session.commit()

        # 3. Create Aliases
        # Alice uses her real name and a pen name
        a1 = Alias(name="Alice", user=u1)
        a2 = Alias(name="Picasso_V2", user=u1)
        
        # Bob uses different nicknames
        a3 = Alias(name="Bob", user=u2)
        a4 = Alias(name="BobbyB", user=u2)
        
        # Charlie uses a distinct alias
        a5 = Alias(name="ChaosMaster", user=u3)

        db.session.add_all([a1, a2, a3, a4, a5])
        db.session.commit()

        # 4. Create Characters
        print("Seeding Characters...")
        c1 = Character(name="Stickman Steve", description="A generic stickman who appears often.", image_url="https://placehold.co/100x100?text=Steve")
        c2 = Character(name="Grumpy Cat", description="A cat that hates everything.", image_url="https://placehold.co/100x100?text=Cat")
        
        db.session.add_all([c1, c2])
        db.session.commit()

        # 5. Create Games
        print("Seeding Games...")
        # Game 1: Last week
        g1 = Game(date=date.today() - timedelta(days=7), title="Friday Night Fun")
        # Game 2: Yesterday (Untitled, will default to date)
        g2 = Game(date=date.today() - timedelta(days=1))
        
        db.session.add_all([g1, g2])
        db.session.commit()

        # 6. Create Books & Pages
        print("Seeding Books and Pages...")

        # --- BOOK 1: "The Pizza Cat" (In Game 1) ---
        b1 = Book(game=g1)
        db.session.add(b1)
        db.session.commit() # Commit to get b1.id

        # Page 1: Text (Start) by Bob
        p1_1 = Page(book_id=b1.id, alias_id=a3.id, sequence=1, type='text', 
                    content_text="A grumpy cat eating a slice of pepperoni pizza.")
        
        # Page 2: Image by Alice (She draws the cat)
        p1_2 = Page(book_id=b1.id, alias_id=a1.id, sequence=2, type='image',
                    content_url="https://placehold.co/400x300?text=Cat+Eating+Pizza")
        p1_2.characters.append(c2) # Link Grumpy Cat character
        
        # Page 3: Text by Charlie (Misinterpretation)
        p1_3 = Page(book_id=b1.id, alias_id=a5.id, sequence=3, type='text',
                    content_text="A tiger choking on a frisbee.")

        # Page 4: Image by Bob (He tries to draw a tiger)
        p1_4 = Page(book_id=b1.id, alias_id=a3.id, sequence=4, type='image',
                    content_url="https://placehold.co/400x300?text=Tiger+Frisbee")

        db.session.add_all([p1_1, p1_2, p1_3, p1_4])


        # --- BOOK 2: "Alien Invasion" (In Game 1) ---
        b2 = Book(game=g1)
        db.session.add(b2)
        db.session.commit()

        # Page 1: Text
        p2_1 = Page(book_id=b2.id, alias_id=a5.id, sequence=1, type='text',
                    content_text="Aliens landing on the white house.")
        
        # Page 2: Image
        p2_2 = Page(book_id=b2.id, alias_id=a2.id, sequence=2, type='image',
                    content_url="https://placehold.co/400x300?text=UFO+Landing")
        p2_2.characters.append(c1) # Stickman Steve runs away

        db.session.add_all([p2_1, p2_2])


        # --- BOOK 3: "Untitled" (In Game 2) ---
        b3 = Book(game=g2)
        db.session.add(b3)
        db.session.commit()

        p3_1 = Page(book_id=b3.id, alias_id=a4.id, sequence=1, type='text',
                    content_text="A giant banana playing guitar.")
        p3_2 = Page(book_id=b3.id, alias_id=a1.id, sequence=2, type='image',
                    content_url="https://placehold.co/400x300?text=Musical+Banana")

        db.session.add_all([p3_1, p3_2])

        # Final Commit
        db.session.commit()
        print("Database seeded successfully!")

if __name__ == "__main__":
    seed_data()