-- Production SQLite Schema for EAT SAFE Platform

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT,
    username TEXT NOT NULL UNIQUE,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    onboarding_completed INTEGER DEFAULT 0,
    failed_login_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id INTEGER PRIMARY KEY,
    warning_explicit INTEGER DEFAULT 1,
    warning_precautionary INTEGER DEFAULT 1,
    warning_unreadable INTEGER DEFAULT 1,
    theme TEXT DEFAULT 'light',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS allergens (
    allergen_id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_code TEXT NOT NULL UNIQUE,
    category_name TEXT NOT NULL,
    category_group TEXT DEFAULT 'Common',
    description TEXT,
    synonyms TEXT,
    is_custom INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS user_allergies (
    user_id INTEGER NOT NULL,
    allergen_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, allergen_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (allergen_id) REFERENCES allergens(allergen_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_custom_allergens (
    custom_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    term_name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS products (
    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    brand TEXT,
    barcode TEXT UNIQUE,
    image_path TEXT,
    ingredients_text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scans (
    scan_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    product_id INTEGER,
    image_path TEXT NOT NULL,
    ocr_raw_text TEXT,
    ocr_confidence REAL DEFAULT 0.0,
    status TEXT DEFAULT 'COMPLETED',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS detection_results (
    result_id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id INTEGER NOT NULL,
    allergen_id INTEGER NOT NULL,
    matched_term TEXT NOT NULL,
    evidence_text TEXT NOT NULL,
    statement_type TEXT CHECK(statement_type IN ('explicit', 'precautionary')) NOT NULL,
    is_user_allergy INTEGER NOT NULL DEFAULT 0,
    confidence REAL DEFAULT 1.0,
    FOREIGN KEY (scan_id) REFERENCES scans(scan_id) ON DELETE CASCADE,
    FOREIGN KEY (allergen_id) REFERENCES allergens(allergen_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS saved_products (
    saved_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    scan_id INTEGER NOT NULL,
    product_name TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (scan_id) REFERENCES scans(scan_id) ON DELETE CASCADE,
    UNIQUE(user_id, scan_id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT NOT NULL,
    details TEXT,
    ip_address TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Dynamic Relational Knowledge Schema
CREATE TABLE IF NOT EXISTS ingredients (
    ingredient_id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT NOT NULL UNIQUE,
    category_code TEXT,
    description TEXT,
    is_allergen INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_code) REFERENCES allergens(category_code) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS ingredient_aliases (
    alias_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ingredient_id INTEGER NOT NULL,
    alias_name TEXT NOT NULL,
    language TEXT DEFAULT 'en',
    match_type TEXT DEFAULT 'exact',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ingredient_id) REFERENCES ingredients(ingredient_id) ON DELETE CASCADE,
    UNIQUE(ingredient_id, alias_name)
);

CREATE TABLE IF NOT EXISTS ingredient_relationships (
    relationship_id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_ingredient_id INTEGER NOT NULL,
    child_ingredient_id INTEGER NOT NULL,
    relationship_type TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_ingredient_id) REFERENCES ingredients(ingredient_id) ON DELETE CASCADE,
    FOREIGN KEY (child_ingredient_id) REFERENCES ingredients(ingredient_id) ON DELETE CASCADE,
    UNIQUE(parent_ingredient_id, child_ingredient_id, relationship_type)
);

CREATE TABLE IF NOT EXISTS knowledge_sources (
    source_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL UNIQUE,
    source_url TEXT,
    version TEXT,
    retrieved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS knowledge_versions (
    version_id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_tag TEXT NOT NULL UNIQUE,
    description TEXT,
    records_count INTEGER DEFAULT 0,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_scans_user_id ON scans(user_id);
CREATE INDEX IF NOT EXISTS idx_scans_created_at ON scans(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_allergies_user_id ON user_allergies(user_id);
CREATE INDEX IF NOT EXISTS idx_user_custom_allergens_user_id ON user_custom_allergens(user_id);
CREATE INDEX IF NOT EXISTS idx_saved_products_user_id ON saved_products(user_id);
CREATE INDEX IF NOT EXISTS idx_detection_results_scan_id ON detection_results(scan_id);
CREATE INDEX IF NOT EXISTS idx_ingredient_aliases_name ON ingredient_aliases(alias_name);
CREATE INDEX IF NOT EXISTS idx_ingredients_canonical ON ingredients(canonical_name);
CREATE INDEX IF NOT EXISTS idx_ingredient_relationships_child ON ingredient_relationships(child_ingredient_id);

