import os
import sqlite3
import json
import logging
from flask import g, has_app_context

logger = logging.getLogger('eatsafe')

DATABASE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'allergen_app.db')
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'schema.sql')
KB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'allergen_kb.json')


def get_database_url():
    """Retrieve DATABASE_URL from environment variables and normalize PostgreSQL scheme."""
    url = os.environ.get('DATABASE_URL', '')
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
    return url


def is_postgres():
    """Check if the configured database is PostgreSQL."""
    return get_database_url().startswith('postgresql://')


def get_db():
    """
    Get active database connection. Supports both SQLite (local dev)
    and PostgreSQL (production environment).
    """
    db_url = get_database_url()
    use_pg = db_url.startswith('postgresql://')

    if has_app_context():
        if 'db' not in g:
            if use_pg:
                try:
                    import psycopg2
                    from psycopg2.extras import RealDictCursor
                    g.db = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
                    g.db_type = 'postgres'
                except Exception as e:
                    logger.error(f"Failed to connect to PostgreSQL database: {e}. Falling back to SQLite.")
                    use_pg = False
            
            if not use_pg:
                os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
                g.db = sqlite3.connect(DATABASE_PATH, timeout=20.0)
                g.db.row_factory = sqlite3.Row
                g.db.execute("PRAGMA foreign_keys = ON")
                try:
                    g.db.execute("PRAGMA journal_mode = WAL")
                except sqlite3.OperationalError:
                    pass
                g.db_type = 'sqlite'
        return g.db

    # Outside Flask application context
    if use_pg:
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            return psycopg2.connect(db_url, cursor_factory=RealDictCursor)
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL database: {e}. Falling back to SQLite.")
            
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH, timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError:
        pass
    return conn


def close_connection(conn=None):
    """Close database connection if outside Flask request lifecycle."""
    if not has_app_context() and conn:
        try:
            conn.close()
        except Exception:
            pass


def close_db(e=None):
    """Teardown handler to close g.db at the end of a Flask request."""
    db = g.pop('db', None)
    if db is not None:
        try:
            db.close()
        except Exception:
            pass


def init_db():
    """Initialize database schema and seed FSSAI allergen categories from KB JSON."""
    conn = get_db()
    cursor = conn.cursor()
    pg = is_postgres()
    
    if pg:
        pg_schema = """
        CREATE TABLE IF NOT EXISTS users (
            user_id SERIAL PRIMARY KEY,
            full_name TEXT,
            username VARCHAR(255) NOT NULL UNIQUE,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS allergens (
            allergen_id SERIAL PRIMARY KEY,
            category_code VARCHAR(100) NOT NULL UNIQUE,
            category_name VARCHAR(255) NOT NULL,
            description TEXT
        );

        CREATE TABLE IF NOT EXISTS user_allergies (
            user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            allergen_id INTEGER NOT NULL REFERENCES allergens(allergen_id) ON DELETE CASCADE,
            PRIMARY KEY (user_id, allergen_id)
        );

        CREATE TABLE IF NOT EXISTS scans (
            scan_id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            image_path TEXT NOT NULL,
            ocr_raw_text TEXT,
            ocr_confidence REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS detection_results (
            result_id SERIAL PRIMARY KEY,
            scan_id INTEGER NOT NULL REFERENCES scans(scan_id) ON DELETE CASCADE,
            allergen_id INTEGER NOT NULL REFERENCES allergens(allergen_id) ON DELETE CASCADE,
            matched_term TEXT NOT NULL,
            evidence_text TEXT NOT NULL,
            statement_type VARCHAR(50) NOT NULL,
            is_user_allergy INTEGER NOT NULL DEFAULT 0,
            confidence REAL DEFAULT 1.0
        );
        """
        cursor.execute(pg_schema)
    else:
        with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
            cursor.executescript(f.read())

        # Migration logic for SQLite
        cursor.execute("PRAGMA table_info(users)")
        existing_columns = [col[1] for col in cursor.fetchall()]
        
        if 'full_name' not in existing_columns:
            try:
                cursor.execute("ALTER TABLE users ADD COLUMN full_name TEXT")
            except sqlite3.OperationalError:
                pass

        if 'password_hash' not in existing_columns:
            try:
                cursor.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
            except sqlite3.OperationalError:
                pass
        
    # Seed FSSAI Allergens from KB JSON
    if os.path.exists(KB_PATH):
        with open(KB_PATH, 'r', encoding='utf-8') as f:
            kb_data = json.load(f)
            
        for category in kb_data.get('categories', []):
            if pg:
                cursor.execute(
                    """
                    INSERT INTO allergens (category_code, category_name, description)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (category_code) DO NOTHING
                    """,
                    (category['code'], category['name'], category.get('description', ''))
                )
            else:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO allergens (category_code, category_name, description)
                    VALUES (?, ?, ?)
                    """,
                    (category['code'], category['name'], category.get('description', ''))
                )
            
    conn.commit()
    close_connection(conn)
