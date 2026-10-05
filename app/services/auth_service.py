import re
import logging
from datetime import datetime, timedelta, timezone
from flask import session, request
from werkzeug.security import generate_password_hash, check_password_hash

from app.database import get_db, close_connection, is_postgres
from app.models import (
    create_user, get_user_by_id, get_user_by_email, get_user_by_username,
    get_user_by_email_or_username, update_user_profile, update_user_password,
    get_user_allergy_ids, get_user_custom_allergens, get_all_allergens,
    get_scan_history
)
from app.services.storage_service import storage_service

logger = logging.getLogger('eatsafe')

# Memory tracking for login throttling: { login_key: {'attempts': int, 'first_attempt': datetime, 'locked_until': datetime} }
_LOGIN_THROTTLE_MAP = {}
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15


def validate_password_strength(password):
    """
    Validates password strength:
    - Minimum 8 characters
    - Must contain at least one uppercase or lowercase letter
    - Must contain at least one digit or special character
    """
    if not password or len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r'[a-zA-Z]', password):
        return False, "Password must contain at least one letter."
    if not re.search(r'[\d\W]', password):
        return False, "Password must contain at least one number or special character."
    return True, None


def check_login_rate_limit(login_input):
    """Check if the given username/email is currently locked out due to failed attempts."""
    key = login_input.strip().lower()
    now = datetime.now(timezone.utc)
    
    if key in _LOGIN_THROTTLE_MAP:
        entry = _LOGIN_THROTTLE_MAP[key]
        if entry.get('locked_until') and now < entry['locked_until']:
            remaining = int((entry['locked_until'] - now).total_seconds() / 60) + 1
            return False, f"Account temporarily locked due to multiple failed login attempts. Please try again in {remaining} minute(s)."
        
        # Reset window if duration has passed
        if entry.get('first_attempt') and now - entry['first_attempt'] > timedelta(minutes=LOCKOUT_DURATION_MINUTES):
            _LOGIN_THROTTLE_MAP.pop(key, None)

    return True, None


def record_failed_login(login_input):
    """Record a failed login attempt for rate limiting."""
    key = login_input.strip().lower()
    now = datetime.now(timezone.utc)
    
    if key not in _LOGIN_THROTTLE_MAP:
        _LOGIN_THROTTLE_MAP[key] = {
            'attempts': 1,
            'first_attempt': now,
            'locked_until': None
        }
    else:
        entry = _LOGIN_THROTTLE_MAP[key]
        entry['attempts'] += 1
        if entry['attempts'] >= MAX_FAILED_ATTEMPTS:
            entry['locked_until'] = now + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
            logger.warning(f"Login rate limit exceeded for input '{key}'. Account locked for {LOCKOUT_DURATION_MINUTES}m.")


def clear_login_rate_limit(login_input):
    """Clear failed login record upon successful login."""
    key = login_input.strip().lower()
    _LOGIN_THROTTLE_MAP.pop(key, None)


def export_user_data(user_id):
    """
    Generate complete GDPR/privacy-compliant JSON export of user account data.
    """
    user = get_user_by_id(user_id)
    if not user:
        return None

    # Remove sensitive password hash from export
    user_data = {
        'user_id': user['user_id'],
        'full_name': user.get('full_name'),
        'username': user.get('username'),
        'email': user.get('email'),
        'created_at': str(user.get('created_at')),
        'onboarding_completed': bool(user.get('onboarding_completed', 0))
    }

    user_allergy_ids = get_user_allergy_ids(user_id)
    all_allergens = get_all_allergens()
    monitored_allergens = [a['category_name'] for a in all_allergens if a['allergen_id'] in user_allergy_ids]

    custom_terms = get_user_custom_allergens(user_id)
    scans = get_scan_history(user_id, limit=1000)

    # Saved Products
    conn = get_db()
    cursor = conn.cursor()
    ph = "%s" if is_postgres() else "?"
    cursor.execute(f"SELECT * FROM saved_products WHERE user_id = {ph}", (user_id,))
    saved_products = [dict(row) for row in cursor.fetchall()]
    close_connection(conn)

    export_payload = {
        'account_info': user_data,
        'monitored_allergens': monitored_allergens,
        'custom_terms': custom_terms,
        'saved_products': saved_products,
        'scan_history': scans,
        'exported_at': datetime.now(timezone.utc).isoformat()
    }
    return export_payload


def delete_user_account_complete(user_id):
    """
    Transactionally delete user account from DB and remove associated uploaded image files.
    """
    conn = get_db()
    cursor = conn.cursor()
    ph = "%s" if is_postgres() else "?"

    # 1. Fetch scan image paths to clean up files
    cursor.execute(f"SELECT image_path FROM scans WHERE user_id = {ph}", (user_id,))
    image_paths = [row['image_path'] for row in cursor.fetchall()]

    # 2. Cascade delete database entries
    cursor.execute(f"DELETE FROM user_allergies WHERE user_id = {ph}", (user_id,))
    cursor.execute(f"DELETE FROM user_custom_allergens WHERE user_id = {ph}", (user_id,))
    cursor.execute(f"DELETE FROM user_preferences WHERE user_id = {ph}", (user_id,))
    cursor.execute(f"DELETE FROM saved_products WHERE user_id = {ph}", (user_id,))
    
    cursor.execute(f"SELECT scan_id FROM scans WHERE user_id = {ph}", (user_id,))
    scan_ids = [row['scan_id'] for row in cursor.fetchall()]
    for sid in scan_ids:
        cursor.execute(f"DELETE FROM detection_results WHERE scan_id = {ph}", (sid,))
        
    cursor.execute(f"DELETE FROM scans WHERE user_id = {ph}", (user_id,))
    cursor.execute(f"DELETE FROM audit_logs WHERE user_id = {ph}", (user_id,))
    cursor.execute(f"DELETE FROM users WHERE user_id = {ph}", (user_id,))

    conn.commit()
    close_connection(conn)

    # 3. Clean up physical image files from disk
    for rel_path in image_paths:
        storage_service.delete_file(rel_path)

    logger.info(f"User account user_id={user_id} and all associated image files deleted permanently.")
