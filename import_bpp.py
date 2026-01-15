import re
from bs4 import BeautifulSoup
from datetime import datetime

def cast_date(date_str):
    try:
        creation_date = datetime.strptime(date_str, "%m/%d/%Y").isoformat()
    except:
        creation_date = datetime.strptime(date_str, "%d/%m/%Y").isoformat()

    return creation_date

def process_html_content(content): 
    soup = BeautifulSoup(content, "html.parser")

    game = {}
    books = []

    # --- Extract game date ---
    h1 = soup.find("h1")
    date_match = re.search(r"Broken Picturephone\s*-\s*([\d\/]+),?\s*([\d:]+)", h1.text)
    if not date_match:
        print(f"No date found in content, skipping")
        return
    date_str = date_match.group(1).replace(",","")
    
    game["date"] = cast_date(date_str)

    # --- Process each comic (article) ---
    for article in soup.find_all("article"):
        h2 = article.find("h2")
        if not h2:
            continue

        pages = []
        game_title = h2.text.strip()

        # --- Process each panel (section) ---
        for seq, section in enumerate(article.find_all("section"), start=1):
            h3 = section.find("h3")
            if not h3:
                continue
            # Extract author
            author_match = re.search(r"Page \d+,\s*(.*):", h3.text)
            author_name = author_match.group(1).strip() if author_match else "Unknown"

            # Panel content
            img = section.find("img")
            if img and img.get("src", "").startswith("data:image/png;base64,"):
                panel_type = "drawing"
                content = img["src"]
            else:
                panel_type = "description"
                h4 = section.find("h4")
                content = h4.text.strip() if h4 else ""

            pages.append({
                "sequence": seq,
                "type": panel_type,
                "content": content,
                "author": author_name
            })
        
        books.append({
            "title": game_title,
            "pages": pages
        })

    game["books"] = books
    return game

if __name__ == "__main__":
    with open("instance/data/4YGN BPP.html", "r") as f:
        html_content = f.read()
    
    game_data = process_html_content(html_content)
    
    # save to json file
    import json
    with open("instance/data/4YGN_BPP.json", "w") as f:
        json.dump(game_data, f, indent=4)