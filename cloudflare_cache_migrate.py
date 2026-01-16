from models import db, Page, Character
from dotenv import load_dotenv
import os

load_dotenv()  # Load environment variables from .env file

B2_BUCKET_NAME = os.getenv("B2_BUCKET_NAME", "your_bucket_name")
IMAGE_SERVER_URL = os.getenv("IMAGE_SERVER_URL", "https://images.freefnafgamesbecauseipiratedthem.com/")

def migrate_cache_urls():
    with db.app.app_context():
        # All pages with content URLs that start with the old B2 URL need to be updated to the new Cloudflare URL
        pages = Page.query.all()
        for page in pages:
            # not all pages have content URLs, so we check if it exists first
            if page.content_url and page.content_url.startswith("https://f005.backblazeb2.com/file/"):
                # Extract the filename from the old URL
                filename = page.content_url.split("/")[-2:]
                # Construct the new URL using the Cloudflare domain
                new_url = f"{IMAGE_SERVER_URL}/{'/'.join(filename)}"
                # Update the entry's URL
                page.content_url = new_url
        # print only the number of pages updated
        print(f"Updated {len(pages)} page URLs.")
        
        # Characters might also have image URLs that need updating
        characters = Character.query.all()
        for character in characters:
            if character.image_url and character.image_url.startswith("https://f005.backblazeb2.com/file/"):
                filename = character.image_url.split("/")[-2:]
                new_url = f"{IMAGE_SERVER_URL}/{'/'.join(filename)}"
                character.image_url = new_url
                print(f"Updated image URL for character {character.id}: {new_url}")

        db.session.commit()