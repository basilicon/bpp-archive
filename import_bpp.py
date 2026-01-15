import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import time

# --- CONFIG ---
HTML_FOLDER = "old-games/data"  # folder containing HTML files
API_BASE = "http://localhost:5000/api"  # change to your backend URL if needed

def get_or_create_user_cache():
    """Simple in-memory cache to avoid duplicate users"""
    cache = {}
    return cache

user_cache = get_or_create_user_cache()

def get_or_create_user(username):
    if username in user_cache:
        return user_cache[username]

    # For simplicity, assume you already have an endpoint for creating users:
    # e.g., POST /api/users { "username": "xxx" }
    # If the backend doesn't create duplicates, this is fine
    response = requests.post(f"{API_BASE}/users", json={"username": username})
    response.raise_for_status()
    user_id = response.json()["user"]["user_id"]
    user_cache[username] = user_id
    return user_id

def create_game_session(date_str):
    try:
        creation_date = datetime.strptime(date_str, "%m/%d/%Y").isoformat()
    except:
        creation_date = datetime.strptime(date_str, "%d/%m/%Y").isoformat()

    data = {
        "title": f"Session on {date_str}",
        "creation_date": creation_date
    }
    response = requests.post(f"{API_BASE}/game-sessions", json=data)
    response.raise_for_status()

    return response.json()["session"]["session_id"]

def create_game(title, session_id):
    data = {"title": title, "session_id": session_id}
    response = requests.post(f"{API_BASE}/games", json=data)
    response.raise_for_status()
    return response.json()["game"]["game_id"]

def create_panel(game_id, author_id, panel_type, content, sequence_number):
    data = {
        "game_id": game_id,
        "author_id": author_id,
        "panel_type": panel_type,
        "content": content,
        "sequence_number": sequence_number
    }
    response = requests.post(f"{API_BASE}/panels", json=data)
    response.raise_for_status()
    return response.json()["panel"]["panel_id"]

def process_html_file(file_path):

    with open(file_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    print("Processing:", file_path)

    # --- Extract game date ---
    h1 = soup.find("h1")
    date_match = re.search(r"Broken Picturephone\s*-\s*([\d\/]+),?\s*([\d:]+)", h1.text)
    if not date_match:
        print(f"No date found in {file_path}, skipping")
        return
    date_str = date_match.group(1).replace(",","")
    session_id = create_game_session(date_str)

    # --- Process each comic (article) ---
    for article in soup.find_all("article"):
        h2 = article.find("h2")
        if not h2:
            continue
        game_title = h2.text.strip()
        game_id = create_game(game_title, session_id)

        # --- Process each panel (section) ---
        for seq, section in enumerate(article.find_all("section"), start=1):
            h3 = section.find("h3")
            if not h3:
                continue
            # Extract author
            author_match = re.search(r"Page \d+,\s*(.*):", h3.text)
            author_name = author_match.group(1).strip() if author_match else "Unknown"
            author_id = get_or_create_user(author_name)

            # Panel content
            img = section.find("img")
            if img and img.get("src", "").startswith("data:image/png;base64,"):
                panel_type = "drawing"
                content = img["src"]
            else:
                panel_type = "description"
                h4 = section.find("h4")
                content = h4.text.strip() if h4 else ""

            create_panel(game_id, author_id, panel_type, content, seq)

    # print(f"Processed {file_path}")

# --- MAIN ---
for filename in os.listdir(HTML_FOLDER):
    if filename.endswith(".html"):
        file_path = os.path.join(HTML_FOLDER, filename)
        process_html_file(file_path)

        # wait for 2 seconds to avoid overwhelming the server
        time.sleep(2)

print("All files processed successfully.")
