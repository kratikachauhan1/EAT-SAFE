from app.database import get_db, close_connection, is_postgres

def create_user(full_name, username, email, password_hash):
    """Create a new user account in SQLite / PostgreSQL database."""
    conn = get_db()
    cursor = conn.cursor()
    if is_postgres():
        cursor.execute(
            """
            INSERT INTO users (full_name, username, email, password_hash)
            VALUES (%s, %s, %s, %s) RETURNING user_id
            """,
            (full_name.strip(), username.strip().lower(), email.strip().lower(), password_hash)
        )
        row = cursor.fetchone()
        user_id = row['user_id'] if isinstance(row, dict) else row[0]
    else:
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
    if is_postgres():
        cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    else:
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
    if is_postgres():
        cursor.execute("SELECT * FROM users WHERE LOWER(email) = %s", (email.strip().lower(),))
    else:
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
    if is_postgres():
        cursor.execute("SELECT * FROM users WHERE LOWER(username) = %s", (username.strip().lower(),))
    else:
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
    if is_postgres():
        cursor.execute(
            "SELECT * FROM users WHERE LOWER(username) = %s OR LOWER(email) = %s",
            (input_clean, input_clean)
        )
    else:
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
    if is_postgres():
        cursor.execute(
            """
            UPDATE users
            SET full_name = %s, username = %s, email = %s
            WHERE user_id = %s
            """,
            (full_name.strip(), username.strip().lower(), email.strip().lower(), user_id)
        )
    else:
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
    if is_postgres():
        cursor.execute("UPDATE users SET password_hash = %s WHERE user_id = %s", (password_hash, user_id))
    else:
        cursor.execute("UPDATE users SET password_hash = ? WHERE user_id = ?", (password_hash, user_id))
    conn.commit()
    close_connection(conn)


def delete_user_account(user_id):
    """Permanently delete user account and associated scans/allergies."""
    conn = get_db()
    cursor = conn.cursor()
    ph = "%s" if is_postgres() else "?"
    cursor.execute(f"DELETE FROM user_allergies WHERE user_id = {ph}", (user_id,))
    cursor.execute(f"DELETE FROM user_custom_allergens WHERE user_id = {ph}", (user_id,))
    
    cursor.execute(f"SELECT scan_id FROM scans WHERE user_id = {ph}", (user_id,))
    scan_ids = [row['scan_id'] for row in cursor.fetchall()]
    for sid in scan_ids:
        cursor.execute(f"DELETE FROM detection_results WHERE scan_id = {ph}", (sid,))
    cursor.execute(f"DELETE FROM scans WHERE user_id = {ph}", (user_id,))
    cursor.execute(f"DELETE FROM users WHERE user_id = {ph}", (user_id,))
    
    conn.commit()
    close_connection(conn)


def get_all_allergens(search_query=None, group_filter=None):
    """
    Fetch all database allergens with optional search query and category group filtering.
    """
    conn = get_db()
    cursor = conn.cursor()
    pg = is_postgres()
    
    query = "SELECT * FROM allergens WHERE 1=1"
    params = []
    
    if group_filter and group_filter.strip() and group_filter.strip().lower() != 'all':
        if pg:
            query += " AND LOWER(category_group) = %s"
        else:
            query += " AND LOWER(category_group) = ?"
        params.append(group_filter.strip().lower())

    if search_query and search_query.strip():
        term = f"%{search_query.strip().lower()}%"
        if pg:
            query += " AND (LOWER(category_name) LIKE %s OR LOWER(category_code) LIKE %s OR LOWER(synonyms) LIKE %s OR LOWER(description) LIKE %s)"
        else:
            query += " AND (LOWER(category_name) LIKE ? OR LOWER(category_code) LIKE ? OR LOWER(synonyms) LIKE ? OR LOWER(description) LIKE ?)"
        params.extend([term, term, term, term])

    query += " ORDER BY category_group ASC, category_name ASC"
    cursor.execute(query, tuple(params))
    allergens = [dict(row) for row in cursor.fetchall()]
    close_connection(conn)
    return allergens


def get_user_allergy_ids(user_id):
    """Fetch set of allergen_ids monitored by a specific user."""
    if not user_id:
        return set()
    conn = get_db()
    cursor = conn.cursor()
    if is_postgres():
        cursor.execute("SELECT allergen_id FROM user_allergies WHERE user_id = %s", (user_id,))
    else:
        cursor.execute("SELECT allergen_id FROM user_allergies WHERE user_id = ?", (user_id,))
    allergy_ids = [row['allergen_id'] for row in cursor.fetchall()]
    close_connection(conn)
    return set(allergy_ids)


def update_user_allergies(user_id, allergen_ids):
    """Update active allergen monitoring selections for a user."""
    if not user_id:
        return
    conn = get_db()
    cursor = conn.cursor()
    pg = is_postgres()
    
    if pg:
        cursor.execute("DELETE FROM user_allergies WHERE user_id = %s", (user_id,))
    else:
        cursor.execute("DELETE FROM user_allergies WHERE user_id = ?", (user_id,))
        
    for aid in allergen_ids:
        if str(aid).isdigit():
            if pg:
                cursor.execute(
                    "INSERT INTO user_allergies (user_id, allergen_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (user_id, int(aid))
                )
            else:
                cursor.execute(
                    "INSERT OR IGNORE INTO user_allergies (user_id, allergen_id) VALUES (?, ?)",
                    (user_id, int(aid))
                )
    conn.commit()
    close_connection(conn)


def get_user_custom_allergens(user_id):
    """Fetch custom ingredient terms monitored by a specific user."""
    if not user_id:
        return []
    conn = get_db()
    cursor = conn.cursor()
    if is_postgres():
        cursor.execute("SELECT * FROM user_custom_allergens WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
    else:
        cursor.execute("SELECT * FROM user_custom_allergens WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    customs = [dict(row) for row in cursor.fetchall()]
    close_connection(conn)
    return customs


def add_user_custom_allergen(user_id, term_name, description="User-custom monitored ingredient"):
    """Add a custom monitored ingredient term for a user."""
    if not user_id or not term_name.strip():
        return None
    conn = get_db()
    cursor = conn.cursor()
    if is_postgres():
        cursor.execute(
            """
            INSERT INTO user_custom_allergens (user_id, term_name, description)
            VALUES (%s, %s, %s) RETURNING custom_id
            """,
            (user_id, term_name.strip(), description.strip())
        )
        row = cursor.fetchone()
        custom_id = row['custom_id'] if isinstance(row, dict) else row[0]
    else:
        cursor.execute(
            """
            INSERT INTO user_custom_allergens (user_id, term_name, description)
            VALUES (?, ?, ?)
            """,
            (user_id, term_name.strip(), description.strip())
        )
        custom_id = cursor.lastrowid
    conn.commit()
    close_connection(conn)
    return custom_id


def delete_user_custom_allergen(user_id, custom_id):
    """Remove a user custom monitored ingredient term."""
    if not user_id or not custom_id:
        return
    conn = get_db()
    cursor = conn.cursor()
    if is_postgres():
        cursor.execute("DELETE FROM user_custom_allergens WHERE custom_id = %s AND user_id = %s", (custom_id, user_id))
    else:
        cursor.execute("DELETE FROM user_custom_allergens WHERE custom_id = ? AND user_id = ?", (custom_id, user_id))
    conn.commit()
    close_connection(conn)


def save_scan(user_id, image_path, ocr_raw_text, ocr_confidence):
    conn = get_db()
    cursor = conn.cursor()
    if is_postgres():
        cursor.execute(
            """
            INSERT INTO scans (user_id, image_path, ocr_raw_text, ocr_confidence)
            VALUES (%s, %s, %s, %s) RETURNING scan_id
            """,
            (user_id, image_path, ocr_raw_text, ocr_confidence)
        )
        row = cursor.fetchone()
        scan_id = row['scan_id'] if isinstance(row, dict) else row[0]
    else:
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
    pg = is_postgres()
    for res in results:
        aid = res.get('allergen_id')
        if not aid:
            continue
        if pg:
            cursor.execute(
                """
                INSERT INTO detection_results 
                (scan_id, allergen_id, matched_term, evidence_text, statement_type, is_user_allergy, confidence)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    scan_id,
                    aid,
                    res['matched_term'],
                    res['evidence_text'],
                    res['statement_type'],
                    res['is_user_allergy'],
                    res.get('confidence', 1.0)
                )
            )
        else:
            cursor.execute(
                """
                INSERT INTO detection_results 
                (scan_id, allergen_id, matched_term, evidence_text, statement_type, is_user_allergy, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scan_id,
                    aid,
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
    pg = is_postgres()
    
    if user_id:
        if pg:
            cursor.execute("SELECT * FROM scans WHERE scan_id = %s AND user_id = %s", (scan_id, user_id))
        else:
            cursor.execute("SELECT * FROM scans WHERE scan_id = ? AND user_id = ?", (scan_id, user_id))
    else:
        if pg:
            cursor.execute("SELECT * FROM scans WHERE scan_id = %s", (scan_id,))
        else:
            cursor.execute("SELECT * FROM scans WHERE scan_id = ?", (scan_id,))
        
    scan = cursor.fetchone()
    if not scan:
        close_connection(conn)
        return None
    
    scan_dict = dict(scan)
    
    if pg:
        cursor.execute(
            """
            SELECT dr.*, a.category_name, a.category_code
            FROM detection_results dr
            JOIN allergens a ON dr.allergen_id = a.allergen_id
            WHERE dr.scan_id = %s
            """,
            (scan_id,)
        )
    else:
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
    pg = is_postgres()
    
    if pg:
        cursor.execute(
            "SELECT * FROM scans WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
            (user_id, limit)
        )
    else:
        cursor.execute(
            "SELECT * FROM scans WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        )
    scans = [dict(row) for row in cursor.fetchall()]
    
    for scan in scans:
        if pg:
            cursor.execute(
                """
                SELECT dr.*, a.category_name
                FROM detection_results dr
                JOIN allergens a ON dr.allergen_id = a.allergen_id
                WHERE dr.scan_id = %s
                """,
                (scan['scan_id'],)
            )
        else:
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


def get_paginated_scan_history(user_id, page=1, per_page=12, search_query=None, status_filter=None, sort_order='newest'):
    """Fetch user scans with server-side pagination, search, status filtering, and sorting."""
    if not user_id:
        return {'scans': [], 'total': 0, 'page': page, 'pages': 1}

    conn = get_db()
    cursor = conn.cursor()
    pg = is_postgres()

    query = "SELECT * FROM scans WHERE user_id = " + ("%s" if pg else "?")
    params = [user_id]

    if search_query and search_query.strip():
        term = f"%{search_query.strip().lower()}%"
        if pg:
            query += " AND LOWER(ocr_raw_text) LIKE %s"
        else:
            query += " AND LOWER(ocr_raw_text) LIKE ?"
        params.append(term)

    if status_filter and status_filter.strip() and status_filter.strip().lower() != 'all':
        if pg:
            query += " AND LOWER(status) = %s"
        else:
            query += " AND LOWER(status) = ?"
        params.append(status_filter.strip().lower())

    # Count total matching records
    count_sql = f"SELECT COUNT(*) as cnt FROM ({query}) as total_scans" if pg else f"SELECT COUNT(*) as cnt FROM ({query})"
    cursor.execute(count_sql, tuple(params))
    row = cursor.fetchone()
    total_count = row['cnt'] if isinstance(row, dict) else (row[0] if row else 0)

    order_clause = " ORDER BY created_at DESC" if sort_order == 'newest' else " ORDER BY created_at ASC"
    query += order_clause

    offset = (max(1, page) - 1) * per_page
    if pg:
        query += " LIMIT %s OFFSET %s"
    else:
        query += " LIMIT ? OFFSET ?"
    params.extend([per_page, offset])

    cursor.execute(query, tuple(params))
    scans = [dict(r) for r in cursor.fetchall()]

    for scan in scans:
        if pg:
            cursor.execute(
                "SELECT dr.*, a.category_name FROM detection_results dr JOIN allergens a ON dr.allergen_id = a.allergen_id WHERE dr.scan_id = %s",
                (scan['scan_id'],)
            )
        else:
            cursor.execute(
                "SELECT dr.*, a.category_name FROM detection_results dr JOIN allergens a ON dr.allergen_id = a.allergen_id WHERE dr.scan_id = ?",
                (scan['scan_id'],)
            )
        scan['results'] = [dict(r) for r in cursor.fetchall()]

    close_connection(conn)

    total_pages = max(1, (total_count + per_page - 1) // per_page)
    return {
        'scans': scans,
        'total': total_count,
        'page': page,
        'per_page': per_page,
        'pages': total_pages
    }


def delete_user_scan(user_id, scan_id):
    """Delete a specific scan belonging to user."""
    if not user_id or not scan_id:
        return False
    conn = get_db()
    cursor = conn.cursor()
    pg = is_postgres()
    ph = "%s" if pg else "?"

    # Check scan ownership
    cursor.execute(f"SELECT image_path FROM scans WHERE scan_id = {ph} AND user_id = {ph}", (scan_id, user_id))
    scan = cursor.fetchone()
    if not scan:
        close_connection(conn)
        return False

    img_path = scan['image_path']

    cursor.execute(f"DELETE FROM detection_results WHERE scan_id = {ph}", (scan_id,))
    cursor.execute(f"DELETE FROM saved_products WHERE scan_id = {ph}", (scan_id,))
    cursor.execute(f"DELETE FROM scans WHERE scan_id = {ph} AND user_id = {ph}", (scan_id, user_id))

    conn.commit()
    close_connection(conn)

    # Remove storage file
    from app.services.storage_service import storage_service
    storage_service.delete_file(img_path)
    return True


def get_dashboard_metrics(user_id):
    """Compute aggregate dashboard metrics using optimized database queries."""
    if not user_id:
        return {'total_scans': 0, 'allergens_flagged': 0, 'profile_allergens_count': 0, 'saved_products_count': 0, 'last_scan': 'No scans yet'}

    conn = get_db()
    cursor = conn.cursor()
    ph = "%s" if is_postgres() else "?"

    cursor.execute(f"SELECT COUNT(*) as cnt FROM scans WHERE user_id = {ph}", (user_id,))
    row = cursor.fetchone()
    total_scans = row['cnt'] if isinstance(row, dict) else (row[0] if row else 0)

    cursor.execute(
        f"SELECT COUNT(DISTINCT s.scan_id) as cnt FROM scans s JOIN detection_results dr ON s.scan_id = dr.scan_id WHERE s.user_id = {ph} AND dr.is_user_allergy = 1",
        (user_id,)
    )
    row = cursor.fetchone()
    allergens_flagged = row['cnt'] if isinstance(row, dict) else (row[0] if row else 0)

    cursor.execute(f"SELECT COUNT(*) as cnt FROM user_allergies WHERE user_id = {ph}", (user_id,))
    row = cursor.fetchone()
    profile_allergens_count = row['cnt'] if isinstance(row, dict) else (row[0] if row else 0)

    cursor.execute(f"SELECT COUNT(*) as cnt FROM saved_products WHERE user_id = {ph}", (user_id,))
    row = cursor.fetchone()
    saved_products_count = row['cnt'] if isinstance(row, dict) else (row[0] if row else 0)

    cursor.execute(f"SELECT created_at FROM scans WHERE user_id = {ph} ORDER BY created_at DESC LIMIT 1", (user_id,))
    last_row = cursor.fetchone()
    last_scan = str(last_row['created_at'])[:10] if last_row else "No scans yet"

    close_connection(conn)
    return {
        'total_scans': total_scans,
        'allergens_flagged': allergens_flagged,
        'profile_allergens_count': profile_allergens_count,
        'saved_products_count': saved_products_count,
        'last_scan': last_scan
    }


def complete_user_onboarding(user_id):
    """Mark onboarding process completed for a user."""
    conn = get_db()
    cursor = conn.cursor()
    ph = "%s" if is_postgres() else "?"
    cursor.execute(f"UPDATE users SET onboarding_completed = 1 WHERE user_id = {ph}", (user_id,))
    conn.commit()
    close_connection(conn)

