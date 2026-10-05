import logging
import requests
from app.database import get_db, close_connection, is_postgres
from app.models import get_scan_details

logger = logging.getLogger('eatsafe')


def save_product(user_id, scan_id, product_name=None, notes=None):
    """Save a scan/product to user's saved products repository."""
    if not user_id or not scan_id:
        return False, "Invalid user or scan ID."
        
    scan = get_scan_details(scan_id, user_id=user_id)
    if not scan:
        return False, "Scan not found or access denied."

    conn = get_db()
    cursor = conn.cursor()
    pg = is_postgres()
    
    p_name = product_name.strip() if product_name and product_name.strip() else f"Scanned Food #{scan_id}"
    p_notes = notes.strip() if notes else ""

    try:
        if pg:
            cursor.execute(
                """
                INSERT INTO saved_products (user_id, scan_id, product_name, notes)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, scan_id) DO UPDATE SET product_name = EXCLUDED.product_name, notes = EXCLUDED.notes
                """,
                (user_id, scan_id, p_name, p_notes)
            )
        else:
            cursor.execute(
                """
                INSERT INTO saved_products (user_id, scan_id, product_name, notes)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, scan_id) DO UPDATE SET product_name = excluded.product_name, notes = excluded.notes
                """,
                (user_id, scan_id, p_name, p_notes)
            )
        conn.commit()
        close_connection(conn)
        logger.info(f"Saved product for user_id={user_id}, scan_id={scan_id}")
        return True, "Product saved successfully!"
    except Exception as e:
        logger.error(f"Error saving product for scan_id={scan_id}: {e}")
        close_connection(conn)
        return False, "Could not save product."


def unsave_product(user_id, scan_id):
    """Remove product from user's saved products repository."""
    if not user_id or not scan_id:
        return False
    conn = get_db()
    cursor = conn.cursor()
    ph = "%s" if is_postgres() else "?"
    cursor.execute(f"DELETE FROM saved_products WHERE user_id = {ph} AND scan_id = {ph}", (user_id, scan_id))
    conn.commit()
    close_connection(conn)
    return True


def get_user_saved_products(user_id):
    """Retrieve list of products saved by a specific user."""
    if not user_id:
        return []
    conn = get_db()
    cursor = conn.cursor()
    pg = is_postgres()

    if pg:
        cursor.execute(
            """
            SELECT sp.*, s.image_path, s.ocr_confidence, s.created_at as scan_created_at
            FROM saved_products sp
            JOIN scans s ON sp.scan_id = s.scan_id
            WHERE sp.user_id = %s
            ORDER BY sp.created_at DESC
            """,
            (user_id,)
        )
    else:
        cursor.execute(
            """
            SELECT sp.*, s.image_path, s.ocr_confidence, s.created_at as scan_created_at
            FROM saved_products sp
            JOIN scans s ON sp.scan_id = s.scan_id
            WHERE sp.user_id = ?
            ORDER BY sp.created_at DESC
            """,
            (user_id,)
        )
    saved = [dict(row) for row in cursor.fetchall()]
    
    # Attach scan details to each saved product
    for item in saved:
        item['scan_details'] = get_scan_details(item['scan_id'], user_id=user_id)
        
    close_connection(conn)
    return saved


def is_product_saved(user_id, scan_id):
    """Check whether a given scan is saved by the user."""
    if not user_id or not scan_id:
        return False
    conn = get_db()
    cursor = conn.cursor()
    ph = "%s" if is_postgres() else "?"
    cursor.execute(f"SELECT 1 FROM saved_products WHERE user_id = {ph} AND scan_id = {ph}", (user_id, scan_id))
    row = cursor.fetchone()
    close_connection(conn)
    return bool(row)


def lookup_barcode(barcode):
    """
    Barcode lookup provider abstraction using Open Food Facts API with fallback.
    Returns: (found: bool, product_data: dict, message: str)
    """
    clean_barcode = str(barcode).strip()
    if not clean_barcode or not clean_barcode.isdigit():
        return False, None, "Invalid barcode format. Barcodes must contain numeric digits only."

    url = f"https://world.openfoodfacts.org/api/v0/product/{clean_barcode}.json"
    headers = {'User-Agent': 'EATSAFE - Food Allergen Detector App'}

    try:
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('status') == 1 and 'product' in data:
                prod = data['product']
                name = prod.get('product_name') or prod.get('product_name_en') or "Unknown Product"
                brand = prod.get('brands') or "Generic"
                img_url = prod.get('image_front_url') or prod.get('image_url')
                ingredients = prod.get('ingredients_text') or prod.get('ingredients_text_en')
                allergens_tags = prod.get('allergens_tags', [])

                if not ingredients:
                    return True, {
                        'barcode': clean_barcode,
                        'name': name,
                        'brand': brand,
                        'image_url': img_url,
                        'ingredients_text': '',
                        'allergens_tags': allergens_tags,
                        'is_complete': False
                    }, "Product found, but ingredient label text is incomplete. Please take a photo of the physical ingredient label for accurate screening."

                return True, {
                    'barcode': clean_barcode,
                    'name': name,
                    'brand': brand,
                    'image_url': img_url,
                    'ingredients_text': ingredients,
                    'allergens_tags': allergens_tags,
                    'is_complete': True
                }, "Product data retrieved successfully!"

    except Exception as e:
        logger.warning(f"Barcode API lookup failed for barcode '{clean_barcode}': {e}")

    return False, None, f"Product barcode '{clean_barcode}' not found in public database. Please capture a photo of the ingredient label directly."
