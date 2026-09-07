import os
import sqlite3
import json

DATABASE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'allergen_app.db')
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'schema.sql')
KB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'allergen_kb.json')


def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize SQLite database tables and seed FSSAI allergen categories from KB JSON."""
    conn = get_db()
    cursor = conn.cursor()
    
    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        cursor.executescript(f.read())
        
    # Seed default user if none exists
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO users (username, email) VALUES (?, ?)",
            ("default_user", "user@example.com")
        )
        
    # Seed allergens from KB JSON
    if os.path.exists(KB_PATH):
        with open(KB_PATH, 'r', encoding='utf-8') as f:
            kb_data = json.load(f)
            
        for category in kb_data.get('categories', []):
            cursor.execute(
                """
                INSERT OR IGNORE INTO allergens (category_code, category_name, description)
                VALUES (?, ?, ?)
                """,
                (category['code'], category['name'], category.get('description', ''))
            )
            
    conn.commit()
    conn.close()
