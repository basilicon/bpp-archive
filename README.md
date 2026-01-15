# 🎨 Broken Picture Phone Archive

A dynamic web application built with **Flask** designed to archive and showcase "Broken Picture Phone" (Telestrations) games. This app organizes games by date, tracks user aliases across different sessions, and even catalogs recurring characters appearing in player drawings.

## 📖 Table of Contents
* [Features](#features)
* [Data Model](#data-model)
* [Tech Stack](#tech-stack)
* [Installation](#installation)
* [Usage](#usage)
* [Project Structure](#project-structure)

---

## ✨ Features

* **Game Management:** Automatically groups books created on the same date into "Game Nights."
* **Alias Tracking:** Support for "True Names" vs "Aliases." One user can have multiple names across different games, but all their contributions are linked to a single profile.
* **Character Cataloging:** Tags specific drawings with recognizable characters, allowing users to browse all panels featuring a specific person or mascot.
* **Deep Search:** Search for books by their starting caption, or find users and characters by name.
* **Component-Based UI:** Built with reusable Jinja2 macros for consistent Game, Book, and Panel previews.

---

## 🏗 Data Model

The application uses a relational database to handle the complex "telephone" structure:

* **User:** The "True" identity of a player.
* **Alias:** The name a player used during a specific game.
* **Game:** A collection of books from a specific date.
* **Book:** A chain of alternating text and image panels.
* **Page:** An individual "panel" in a book (either Text or Image).
* **Character:** Recognizable entities that can be tagged in Image Pages.

---

## 🛠 Tech Stack

* **Backend:** Python 3.x, Flask
* **Database:** SQLAlchemy (SQLite)
* **Frontend:** Jinja2 Templates, Bootstrap 5
* **Images:** Dynamic image rendering for game panels and character profiles.

---

## 🚀 Installation

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/yourusername/broken-picture-phone-archive.git](https://github.com/yourusername/broken-picture-phone-archive.git)
    cd broken-picture-phone-archive
    ```

2.  **Create a virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install flask flask-sqlalchemy
    ```

4.  **Initialize and Seed the database:**
    This will create the `brokenpicturephone.db` file and populate it with sample games, users, and drawings.
    ```bash
    python seed.py
    ```

5.  **Run the application:**
    ```bash
    python app.py
    ```
    Visit `http://127.0.0.1:5000` in your browser.

---

## 🔍 Usage

### Navigating the Archive
* **Home:** View the most recent books and a list of featured characters.
* **Game Detail:** See every book played during a specific session and a list of all participants involved.
* **Book Detail:** View the full "telephone" chain, seeing how a simple prompt evolved (or devolved) into the final panel.
* **User Profiles:** See a user's bio and a gallery of every panel they have drawn across all games.

---

## 📂 Project Structure

```text
├── app.py              # Main Flask application and routing logic
├── models.py           # SQLAlchemy database models and relationships
├── seed.py             # Script to populate the DB with dummy data
├── static/             # CSS and static assets
└── templates/          # Jinja2 HTML templates
    ├── macros.html     # Reusable UI components (GamePreview, PanelComponent, etc.)
    ├── base.html       # Global layout and navigation
    ├── index.html      # Homepage
    ├── search.html     # Search interface and results
    ├── game_detail.html
    ├── book_detail.html
    ├── user_detail.html
    └── character_detail.html
```
