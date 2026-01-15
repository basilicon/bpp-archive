from app import app
from models import db, AdminKey
import os
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

# run once in python shell or seed.py
with app.app_context():
    first_key = AdminKey(key_name="Master")
    first_key.set_key(os.getenv("ADMIN_KEY", "developmentkey123"))
    db.session.add(first_key)
    db.session.commit()