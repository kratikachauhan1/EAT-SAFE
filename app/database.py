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


def is_production():
    """Check if the current runtime environment is production."""
    env = os.environ.get('ENVIRONMENT', os.environ.get('FLASK_ENV', os.environ.get('APP_ENV', ''))).lower()
    return env == 'production'


def get_db():
    """
    Get active database connection. Supports both SQLite (local dev)
    and PostgreSQL (production environment).
    Strictly forbids ephemeral SQLite fallback in production.
    """
    db_url = get_database_url()
    use_pg = db_url.startswith('postgresql://')
    is_prod = is_production()

    if is_prod and not use_pg:
        logger.critical("FATAL: Production environment requires PostgreSQL via DATABASE_URL. Ephemeral SQLite fallback is disabled.")
        raise RuntimeError(
            "FATAL: Production environment requires a valid PostgreSQL DATABASE_URL. "
            "Ephemeral SQLite fallback is strictly prohibited to prevent data loss."
        )

    if has_app_context():
        if 'db' not in g:
            if use_pg:
                try:
                    import psycopg2
                    from psycopg2.extras import RealDictCursor
                    g.db = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
                    g.db_type = 'postgres'
                except Exception as e:
                    logger.critical(f"FATAL: Failed to connect to PostgreSQL database: {e}")
                    if is_prod:
                        raise RuntimeError(f"FATAL: Production environment failed to connect to PostgreSQL: {e}") from e
                    logger.warning("Falling back to SQLite for local development.")
                    use_pg = False
            
            if not use_pg:
                os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
                g.db = sqlite3.connect(DATABASE_PATH, timeout=30.0)
                g.db.row_factory = sqlite3.Row
                g.db.execute("PRAGMA foreign_keys = ON")
                try:
                    g.db.execute("PRAGMA journal_mode = WAL")
                    g.db.execute("PRAGMA busy_timeout = 30000")
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
            logger.critical(f"FATAL: Failed to connect to PostgreSQL database: {e}")
            if is_prod:
                raise RuntimeError(f"FATAL: Production environment failed to connect to PostgreSQL: {e}") from e
            logger.warning("Falling back to SQLite for local development.")
            
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 30000")
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

        CREATE TABLE IF NOT EXISTS ingredients (
            ingredient_id SERIAL PRIMARY KEY,
            canonical_name VARCHAR(255) NOT NULL UNIQUE,
            category_code VARCHAR(100),
            description TEXT,
            is_allergen INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS ingredient_aliases (
            alias_id SERIAL PRIMARY KEY,
            ingredient_id INTEGER NOT NULL REFERENCES ingredients(ingredient_id) ON DELETE CASCADE,
            alias_name VARCHAR(255) NOT NULL,
            language VARCHAR(10) DEFAULT 'en',
            match_type VARCHAR(50) DEFAULT 'exact',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ingredient_id, alias_name)
        );

        CREATE TABLE IF NOT EXISTS ingredient_relationships (
            relationship_id SERIAL PRIMARY KEY,
            parent_ingredient_id INTEGER NOT NULL REFERENCES ingredients(ingredient_id) ON DELETE CASCADE,
            child_ingredient_id INTEGER NOT NULL REFERENCES ingredients(ingredient_id) ON DELETE CASCADE,
            relationship_type VARCHAR(50) NOT NULL,
            confidence REAL DEFAULT 1.0,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(parent_ingredient_id, child_ingredient_id, relationship_type)
        );

        CREATE TABLE IF NOT EXISTS knowledge_sources (
            source_id SERIAL PRIMARY KEY,
            source_name VARCHAR(255) NOT NULL UNIQUE,
            source_url TEXT,
            version VARCHAR(50),
            retrieved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS knowledge_versions (
            version_id SERIAL PRIMARY KEY,
            version_tag VARCHAR(50) NOT NULL UNIQUE,
            description TEXT,
            records_count INTEGER DEFAULT 0,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_ingredient_aliases_name ON ingredient_aliases(alias_name);
        CREATE INDEX IF NOT EXISTS idx_ingredients_canonical ON ingredients(canonical_name);
        CREATE INDEX IF NOT EXISTS idx_ingredient_relationships_child ON ingredient_relationships(child_ingredient_id);
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
    total_kb_terms = 0
    if os.path.exists(KB_PATH):
        with open(KB_PATH, 'r', encoding='utf-8') as f:
            kb_data = json.load(f)

        # 1. Seed Knowledge Source & Version
        if pg:
            cursor.execute("""
                INSERT INTO knowledge_sources (source_name, source_url, version)
                VALUES (%s, %s, %s)
                ON CONFLICT (source_name) DO NOTHING
            """, ('FSSAI Food Safety Standards & Open Food Facts Taxonomy', 'https://fssai.gov.in', 'v1.0'))
            cursor.execute("""
                INSERT INTO knowledge_versions (version_tag, description, records_count)
                VALUES (%s, %s, %s)
                ON CONFLICT (version_tag) DO NOTHING
            """, ('v1.0.0-fssai', 'Standardized food allergen & ingredient relational graph', 0))
        else:
            cursor.execute("""
                INSERT OR IGNORE INTO knowledge_sources (source_name, source_url, version)
                VALUES (?, ?, ?)
            """, ('FSSAI Food Safety Standards & Open Food Facts Taxonomy', 'https://fssai.gov.in', 'v1.0'))
            cursor.execute("""
                INSERT OR IGNORE INTO knowledge_versions (version_tag, description, records_count)
                VALUES (?, ?, ?)
            """, ('v1.0.0-fssai', 'Standardized food allergen & ingredient relational graph', 0))

        # 2. Seed Allergens and Canonical Ingredients
        for category in kb_data.get('categories', []):
            code = category['code']
            name = category['name']
            group = category.get('group', 'Common')
            desc = category.get('description', '')
            terms = category.get('terms', [])
            total_kb_terms += len(terms)
            synonyms_str = ", ".join(terms)

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
                cursor.execute(
                    """
                    INSERT INTO ingredients (canonical_name, category_code, description, is_allergen)
                    VALUES (%s, %s, %s, 1)
                    ON CONFLICT (canonical_name) DO UPDATE
                    SET category_code = EXCLUDED.category_code,
                        description = EXCLUDED.description
                    RETURNING ingredient_id
                    """,
                    (name, code, desc)
                )
                parent_row = cursor.fetchone()
                parent_id = parent_row['ingredient_id'] if isinstance(parent_row, dict) else (parent_row[0] if parent_row else None)

                if parent_id:
                    for term in terms:
                        cursor.execute(
                            """
                            INSERT INTO ingredient_aliases (ingredient_id, alias_name, language, match_type)
                            VALUES (%s, %s, 'en', 'exact')
                            ON CONFLICT (ingredient_id, alias_name) DO NOTHING
                            """,
                            (parent_id, term.lower().strip())
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
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO ingredients (canonical_name, category_code, description, is_allergen)
                    VALUES (?, ?, ?, 1)
                    """,
                    (name, code, desc)
                )
                cursor.execute("SELECT ingredient_id FROM ingredients WHERE canonical_name = ?", (name,))
                parent_row = cursor.fetchone()
                parent_id = parent_row['ingredient_id'] if isinstance(parent_row, sqlite3.Row) else (parent_row[0] if parent_row else None)

                if parent_id:
                    for term in terms:
                        cursor.execute(
                            """
                            INSERT OR IGNORE INTO ingredient_aliases (ingredient_id, alias_name, language, match_type)
                            VALUES (?, ?, 'en', 'exact')
                            """,
                            (parent_id, term.lower().strip())
                        )

        # 3. Seed Canonical Derivative Relationships
        DERIVATIVE_SPECS = [
            ("Whey", "Milk & Dairy", "derived_from", 1.0, "Protein fraction of milk during curdling"),
            ("Casein", "Milk & Dairy", "derived_from", 1.0, "Major protein component of mammal milk"),
            ("Ghee", "Milk & Dairy", "derived_from", 1.0, "Clarified butter originating from milk"),
            ("Lactose", "Milk & Dairy", "derived_from", 1.0, "Disaccharide sugar derived from milk"),
            ("Butter", "Milk & Dairy", "derived_from", 1.0, "Dairy product made from churning milk fat"),
            ("Cheese", "Milk & Dairy", "derived_from", 1.0, "Coagulated dairy product"),
            ("Ovalbumin", "Egg", "derived_from", 1.0, "Primary protein found in egg white"),
            ("Lysozyme", "Egg", "derived_from", 1.0, "Enzyme isolated from egg whites"),
            ("Peanut Butter", "Peanut", "derived_from", 1.0, "Paste ground from roasted peanuts"),
            ("Peanut Oil", "Peanut", "derived_from", 1.0, "Lipid extract pressed from peanuts"),
            ("Soy Lecithin", "Soy", "derived_from", 1.0, "Emulsifier extracted from soybean oil"),
            ("Tofu", "Soy", "derived_from", 1.0, "Coagulated soy milk curd"),
            ("Gluten", "Cereals Containing Gluten (Wheat, Barley, Rye, Oats)", "derived_from", 1.0, "Structural protein composite found in wheat"),
            ("Semolina", "Cereals Containing Gluten (Wheat, Barley, Rye, Oats)", "derived_from", 1.0, "Coarse purified wheat middlings"),
            ("Tahini", "Sesame", "derived_from", 1.0, "Paste made from toasted sesame seeds"),
        ]

        for child_name, parent_cat_name, rel_type, conf, notes in DERIVATIVE_SPECS:
            if pg:
                cursor.execute("""
                    INSERT INTO ingredients (canonical_name, category_code, description, is_allergen)
                    VALUES (%s, (SELECT category_code FROM ingredients WHERE canonical_name = %s LIMIT 1), %s, 1)
                    ON CONFLICT (canonical_name) DO NOTHING
                """, (child_name, parent_cat_name, notes))
                cursor.execute("""
                    INSERT INTO ingredient_relationships (parent_ingredient_id, child_ingredient_id, relationship_type, confidence, notes)
                    SELECT p.ingredient_id, c.ingredient_id, %s, %s, %s
                    FROM ingredients p, ingredients c
                    WHERE p.canonical_name = %s AND c.canonical_name = %s
                    ON CONFLICT (parent_ingredient_id, child_ingredient_id, relationship_type) DO NOTHING
                """, (rel_type, conf, notes, parent_cat_name, child_name))
            else:
                cursor.execute("""
                    INSERT OR IGNORE INTO ingredients (canonical_name, category_code, description, is_allergen)
                    VALUES (?, (SELECT category_code FROM ingredients WHERE canonical_name = ? LIMIT 1), ?, 1)
                """, (child_name, parent_cat_name, notes))
                cursor.execute("""
                    INSERT OR IGNORE INTO ingredient_relationships (parent_ingredient_id, child_ingredient_id, relationship_type, confidence, notes)
                    SELECT p.ingredient_id, c.ingredient_id, ?, ?, ?
                    FROM ingredients p, ingredients c
                    WHERE p.canonical_name = ? AND c.canonical_name = ?
                """, (rel_type, conf, notes, parent_cat_name, child_name))

    conn.commit()
    close_connection(conn)
