import base64
import uuid
from b2sdk.v2 import InMemoryAccountInfo, B2Api
import os
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

# Backblaze Credentials (Store these in environment variables for security!)
B2_KEY_ID = os.getenv("B2_KEY_ID", "your_key_id")
B2_APPLICATION_KEY = os.getenv("B2_APPLICATION_KEY", "your_application_key")
B2_BUCKET_NAME = os.getenv("B2_BUCKET_NAME", "your_bucket_name")

info = InMemoryAccountInfo()
b2_api = B2Api(info)
b2_api.authorize_account("production", B2_KEY_ID, B2_APPLICATION_KEY)
bucket = b2_api.get_bucket_by_name(B2_BUCKET_NAME)

def upload_b64img_to_b2(base64_str):
    if "base64," in base64_str:
        base64_str = base64_str.split("base64,")[1]
    
    image_data = base64.b64decode(base64_str)
    filename = f"panels/{uuid.uuid4()}.png"
    
    # Upload to B2
    file_info = bucket.upload_bytes(image_data, filename)
    
    # Construct the public URL
    # Format: https://f005.backblazeb2.com/file/BUCKET_NAME/FILENAME
    # Note: Check your B2 bucket settings to find your specific "Friendly URL" endpoint
    public_url = f"https://f005.backblazeb2.com/file/{B2_BUCKET_NAME}/{filename}"
    return public_url

def delete_b2_file(file_url):
    # Extract the filename from the URL
    # Assuming file_url is in the format: https://f005.backblazeb2.com/file/BUCKET_NAME/FILENAME
    parts = file_url.split('/')
    if len(parts) < 5:
        return False  # Invalid URL format
    
    filename = '/'.join(parts[5:])  # Get everything after the bucket name
    try:
        file_info = bucket.get_file_info_by_name(filename)
        bucket.delete_file_version(file_info.id_, filename)
        return True
    except Exception as e:
        print(f"Error deleting file from B2: {e}")
        return False    
    
if __name__ == "__main__":
    # delete test
    # delete_b2_file(f"https://f005.backblazeb2.com/file/{B2_BUCKET_NAME}/blue_tower.png")
    pass