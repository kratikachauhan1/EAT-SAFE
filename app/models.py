from app.database import get_db, close_connection

def create_user(full_name, username, email, password_hash):
    """Create a new user account in SQLite database."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO users (full_name, username, email, password_hash)
        VALUES (?, ?, ?, ?)
        """,
        (full_name.strip(), username.strip().lower(), email.strip().lower(), password_hash)
    )
    user_id = cursor.lastrowid
    conn.commit()
    close_connection(conn)
    return user_id


def get_user_by_id(user_id):
    """Fetch user record by ID."""
    if not user_id:
        return None
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    close_connection(conn)
    return dict(user) if user else None


def get_user_by_email(email):
    """Fetch user by email address."""
    if not email:
        return None
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE LOWER(email) = ?", (email.strip().lower(),))
    user = cursor.fetchone()
    close_connection(conn)
    return dict(user) if user else None


def get_user_by_username(username):
    """Fetch user by username."""
    if not username:
        return None
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE LOWER(username) = ?", (username.strip().lower(),))
    user = cursor.fetchone()
    close_connection(conn)
    return dict(user) if user else None


def get_user_by_email_or_username(login_input):
    """Fetch user by either username or email address."""
    if not login_input:
        return None
    input_clean = login_input.strip().lower()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM users WHERE LOWER(username) = ? OR LOWER(email) = ?",
        (input_clean, input_clean)
    )
    user = cursor.fetchone()
    close_connection(conn)
    return dict(user) if user else None


def update_user_profile(user_id, full_name, username, email):
    """Update profile details for a user."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE users
        SET full_name = ?, username = ?, email = ?
        WHERE user_id = ?
        """,
        (full_name.strip(), username.strip().lower(), email.strip().lower(), user_id)
    )
    conn.commit()
    close_connection(conn)


def update_user_password(user_id, password_hash):
    """Update password hash for a user."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET password_hash = ? WHERE user_id = ?",
        (password_hash, user_id)
    )
    conn.commit()
    close_connection(conn)


def delete_user_account(user_id):
    """Permanently delete user account and associated scans/allergies."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_allergies WHERE user_id = ?", (user_id,))
    
    cursor.execute("SELECT scan_id FROM scans WHERE user_id = ?", (user_id,))
    scan_ids = [row['scan_id'] for row in cursor.fetchall()]
    for sid in scan_ids:
        cursor.execute("DELETE FROM detection_results WHERE scan_id = ?", (sid,))
    cursor.execute("DELETE FROM scans WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    
    conn.commit()
    close_connection(conn)


def get_all_allergens():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM allergens ORDER BY category_name ASC")
    allergens = [dict(row) for row in cursor.fetchall()]
    close_connection(conn)
    return allergens


def get_user_allergy_ids(user_id):
    if not user_id:
        return set()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT allergen_id FROM user_allergies WHERE user_id = ?", (user_id,))
    allergy_ids = [row['allergen_id'] for row in cursor.fetchall()]
    close_connection(conn)
    return set(allergy_ids)


def update_user_allergies(user_id, allergen_ids):
    if not user_id:
        return
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_allergies WHERE user_id = ?", (user_id,))
    for aid in allergen_ids:
        cursor.execute(
            "INSERT INTO user_allergies (user_id, allergen_id) VALUES (?, ?)",
            (user_id, int(aid))
        )
    conn.commit()
    close_connection(conn)


def save_scan(user_id, image_path, ocr_raw_text, ocr_confidence):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO scans (user_id, image_path, ocr_raw_text, ocr_confidence)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, image_path, ocr_raw_text, ocr_confidence)
    )
    scan_id = cursor.lastrowid
    conn.commit()
    close_connection(conn)
    return scan_id


def save_detection_results(scan_id, results):
    conn = get_db()
    cursor = conn.cursor()
    for res in results:
        cursor.execute(
            """
            INSERT INTO detection_results 
            (scan_id, allergen_id, matched_term, evidence_text, statement_type, is_user_allergy, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scan_id,
                res['allergen_id'],
                res['matched_term'],
                res['evidence_text'],
                res['statement_type'],
                res['is_user_allergy'],
                res.get('confidence', 1.0)
            )
        )
    conn.commit()
    close_connection(conn)


def get_scan_details(scan_id, user_id=None):
    conn = get_db()
    cursor = conn.cursor()
    if user_id:
        cursor.execute("SELECT * FROM scans WHERE scan_id = ? AND user_id = ?", (scan_id, user_id))
    else:
        cursor.execute("SELECT * FROM scans WHERE scan_id = ?", (scan_id,))
        
    scan = cursor.fetchone()
    if not scan:
        close_connection(conn)
        return None
    
    scan_dict = dict(scan)
    
    cursor.execute(
        """
        SELECT dr.*, a.category_name, a.category_code
        FROM detection_results dr
        JOIN allergens a ON dr.allergen_id = a.allergen_id
        WHERE dr.scan_id = ?
        """,
        (scan_id,)
    )
    results = [dict(row) for row in cursor.fetchall()]
    close_connection(conn)
    
    scan_dict['results'] = results
    return scan_dict


def get_scan_history(user_id, limit=50):
    if not user_id:
        return []
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM scans WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit)
    )
    scans = [dict(row) for row in cursor.fetchall()]
    
    for scan in scans:
        cursor.execute(
            """
            SELECT dr.*, a.category_name
            FROM detection_results dr
            JOIN allergens a ON dr.allergen_id = a.allergen_id
            WHERE dr.scan_id = ?
            """,
            (scan['scan_id'],)
        )
        scan['results'] = [dict(row) for row in cursor.fetchall()]
        
    close_connection(conn)
    return scans
