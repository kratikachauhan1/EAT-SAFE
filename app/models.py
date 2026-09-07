from app.database import get_db

def get_default_user():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users ORDER BY user_id ASC LIMIT 1")
    user = cursor.fetchone()
    conn.close()
    return user

def get_all_allergens():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM allergens ORDER BY category_name ASC")
    allergens = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return allergens

def get_user_allergy_ids(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT allergen_id FROM user_allergies WHERE user_id = ?", (user_id,))
    allergy_ids = [row['allergen_id'] for row in cursor.fetchall()]
    conn.close()
    return set(allergy_ids)

def update_user_allergies(user_id, allergen_ids):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_allergies WHERE user_id = ?", (user_id,))
    for aid in allergen_ids:
        cursor.execute(
            "INSERT INTO user_allergies (user_id, allergen_id) VALUES (?, ?)",
            (user_id, int(aid))
        )
    conn.commit()
    conn.close()

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
    conn.close()
    return scan_id

def save_detection_results(scan_id, results):
    """
    results is a list of dicts:
    [{'allergen_id': 1, 'matched_term': 'milk', 'evidence_text': 'milk solids', 
      'statement_type': 'explicit', 'is_user_allergy': 1, 'confidence': 0.95}]
    """
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
    conn.close()

def get_scan_details(scan_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM scans WHERE scan_id = ?", (scan_id,))
    scan = cursor.fetchone()
    if not scan:
        conn.close()
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
    conn.close()
    
    scan_dict['results'] = results
    return scan_dict

def get_scan_history(user_id, limit=20):
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
        
    conn.close()
    return scans
