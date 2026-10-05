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
    """Initialize database schema and seed FSSAI allergen categories & groups from KB JSON."""
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
            password_hash TEXT NOT NULL,
            onboarding_completed INTEGER DEFAULT 0,
            failed_login_attempts INTEGER DEFAULT 0,
            locked_until TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
            warning_explicit INTEGER DEFAULT 1,
            warning_precautionary INTEGER DEFAULT 1,
            warning_unreadable INTEGER DEFAULT 1,
            theme VARCHAR(50) DEFAULT 'light',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS allergens (
            allergen_id SERIAL PRIMARY KEY,
            category_code VARCHAR(100) NOT NULL UNIQUE,
            category_name VARCHAR(255) NOT NULL,
            category_group VARCHAR(100) DEFAULT 'Common',
            description TEXT,
            synonyms TEXT,
            is_custom INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS user_allergies (
            user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            allergen_id INTEGER NOT NULL REFERENCES allergens(allergen_id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, allergen_id)
        );

        CREATE TABLE IF NOT EXISTS user_custom_allergens (
            custom_id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            term_name VARCHAR(255) NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS products (
            product_id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            brand VARCHAR(255),
            barcode VARCHAR(100) UNIQUE,
            image_path TEXT,
            ingredients_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS scans (
            scan_id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
            product_id INTEGER REFERENCES products(product_id) ON DELETE SET NULL,
            image_path TEXT NOT NULL,
            ocr_raw_text TEXT,
            ocr_confidence REAL DEFAULT 0.0,
            status VARCHAR(50) DEFAULT 'COMPLETED',
            error_message TEXT,
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

        CREATE TABLE IF NOT EXISTS saved_products (
            saved_id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            scan_id INTEGER NOT NULL REFERENCES scans(scan_id) ON DELETE CASCADE,
            product_name TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, scan_id)
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            log_id SERIAL PRIMARY KEY,
            user_id INTEGER,
            action VARCHAR(255) NOT NULL,
            details TEXT,
            ip_address VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        cursor.execute(pg_schema)
    else:
        with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
            cursor.executescript(f.read())

        # Auto-migration checks for existing SQLite databases
        cursor.execute("PRAGMA table_info(users)")
        existing_user_cols = [col[1] for col in cursor.fetchall()]
        
        user_alter_queries = [
            ('full_name', "ALTER TABLE users ADD COLUMN full_name TEXT"),
            ('password_hash', "ALTER TABLE users ADD COLUMN password_hash TEXT"),
            ('onboarding_completed', "ALTER TABLE users ADD COLUMN onboarding_completed INTEGER DEFAULT 0"),
            ('failed_login_attempts', "ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER DEFAULT 0"),
            ('locked_until', "ALTER TABLE users ADD COLUMN locked_until TIMESTAMP"),
            ('updated_at', "ALTER TABLE users ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        ]
        for col_name, query in user_alter_queries:
            if col_name not in existing_user_cols:
                try:
                    cursor.execute(query)
                except sqlite3.OperationalError:
                    pass

        cursor.execute("PRAGMA table_info(allergens)")
        existing_alg_cols = [col[1] for col in cursor.fetchall()]

        alg_alter_queries = [
            ('category_group', "ALTER TABLE allergens ADD COLUMN category_group TEXT DEFAULT 'Common'"),
            ('synonyms', "ALTER TABLE allergens ADD COLUMN synonyms TEXT"),
            ('is_custom', "ALTER TABLE allergens ADD COLUMN is_custom INTEGER DEFAULT 0")
        ]
        for col_name, query in alg_alter_queries:
            if col_name not in existing_alg_cols:
                try:
                    cursor.execute(query)
                except sqlite3.OperationalError:
                    pass

        cursor.execute("PRAGMA table_info(scans)")
        existing_scan_cols = [col[1] for col in cursor.fetchall()]

        scan_alter_queries = [
            ('status', "ALTER TABLE scans ADD COLUMN status TEXT DEFAULT 'COMPLETED'"),
            ('error_message', "ALTER TABLE scans ADD COLUMN error_message TEXT"),
            ('product_id', "ALTER TABLE scans ADD COLUMN product_id INTEGER")
        ]
        for col_name, query in scan_alter_queries:
            if col_name not in existing_scan_cols:
                try:
                    cursor.execute(query)
                except sqlite3.OperationalError:
                    pass
        
    # Seed/Update Allergens from KB JSON
    if os.path.exists(KB_PATH):
        with open(KB_PATH, 'r', encoding='utf-8') as f:
            kb_data = json.load(f)
            
        for category in kb_data.get('categories', []):
            code = category['code']
            name = category['name']
            group = category.get('group', 'Common')
            desc = category.get('description', '')
            synonyms_str = ", ".join(category.get('terms', []))

            if pg:
                cursor.execute(
                    """
                    INSERT INTO allergens (category_code, category_name, category_group, description, synonyms, is_custom)
                    VALUES (%s, %s, %s, %s, %s, 0)
                    ON CONFLICT (category_code) DO UPDATE 
                    SET category_name = EXCLUDED.category_name,
                        category_group = EXCLUDED.category_group,
                        description = EXCLUDED.description,
                        synonyms = EXCLUDED.synonyms
                    """,
                    (code, name, group, desc, synonyms_str)
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO allergens (category_code, category_name, category_group, description, synonyms, is_custom)
                    VALUES (?, ?, ?, ?, ?, 0)
                    ON CONFLICT(category_code) DO UPDATE
                    SET category_name = excluded.category_name,
                        category_group = excluded.category_group,
                        description = excluded.description,
                        synonyms = excluded.synonyms
                    """,
                    (code, name, group, desc, synonyms_str)
                )
            
    conn.commit()
    close_connection(conn)
