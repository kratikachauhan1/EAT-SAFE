import os
import re
import logging
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

from app.database import get_db, is_postgres
from app.models import (
    create_user, get_user_by_id, get_user_by_email, get_user_by_username,
    get_user_by_email_or_username, update_user_profile, update_user_password,
    delete_user_account, get_all_allergens, get_user_allergy_ids,
    update_user_allergies, save_scan, save_detection_results,
    get_scan_details, get_scan_history
)
from app.preprocessing import preprocess_image
from app.ocr import extract_text_from_image
from app.allergen_detector import detect_allergens_in_text
from app.personalisation import evaluate_personalisation
from app.upload_utils import validate_and_save_upload, is_allowed_extension

logger = logging.getLogger('eatsafe')

bp = Blueprint('main', __name__)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not get_user_by_id(session.get('user_id')):
            session.pop('user_id', None)
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('main.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


@bp.context_processor
def inject_user():
    user = None
    if 'user_id' in session:
        user = get_user_by_id(session['user_id'])
    return dict(current_user=user)


# ===================================================
# AUTHENTICATION ROUTES (REGISTER, LOGIN, LOGOUT)
# ===================================================

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session and get_user_by_id(session.get('user_id')):
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Input validations
        if not full_name or not username or not email or not password or not confirm_password:
            flash('All required fields must be filled.', 'danger')
            return render_template('register.html')

        email_regex = r'^[^@]+@[^@]+\.[^@]+$'
        if not re.match(email_regex, email):
            flash('Please enter a valid email address.', 'danger')
            return render_template('register.html')

        if not re.match(r'^[a-zA-Z0-9_]{3,30}$', username):
            flash('Username must be 3-30 characters long and contain only letters, numbers, or underscores.', 'danger')
            return render_template('register.html')

        if password != confirm_password:
            flash('Password and Confirm Password do not match.', 'danger')
            return render_template('register.html')

        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'danger')
            return render_template('register.html')

        if get_user_by_username(username):
            flash('Username is already taken. Please choose another.', 'danger')
            return render_template('register.html')

        if get_user_by_email(email):
            flash('Email address is already registered. Please login or use another email.', 'danger')
            return render_template('register.html')

        try:
            pwd_hash = generate_password_hash(password)
            user_id = create_user(full_name, username, email, pwd_hash)
            logger.info(f"User registered successfully: username='{username}', user_id={user_id}")

            session.clear()
            session['user_id'] = user_id
            flash('Account created successfully! Welcome to EAT SAFE.', 'success')
            return redirect(url_for('main.index'))
        except Exception as e:
            logger.error(f"Error creating user '{username}': {e}")
            flash('An error occurred while creating your account. Please try again.', 'danger')
            return render_template('register.html')

    return render_template('register.html')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session and get_user_by_id(session.get('user_id')):
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        login_input = request.form.get('login_input', '').strip()
        password = request.form.get('password', '')

        if not login_input or not password:
            flash('Please enter your username/email and password.', 'danger')
            return render_template('login.html')

        user = get_user_by_email_or_username(login_input)
        if not user or not user.get('password_hash') or not check_password_hash(user['password_hash'], password):
            logger.warning(f"Failed login attempt for input: '{login_input}'")
            flash('Invalid username/email or password.', 'danger')
            return render_template('login.html')

        session.clear()
        session['user_id'] = user['user_id']
        logger.info(f"User logged in successfully: user_id={user['user_id']}")
        flash(f"Welcome back, {user.get('full_name') or user['username']}!", 'success')

        next_page = request.args.get('next')
        if next_page and next_page.startswith('/') and not next_page.startswith('//'):
            return redirect(next_page)
        return redirect(url_for('main.index'))

    return render_template('login.html')


@bp.route('/logout')
def logout():
    user_id = session.get('user_id')
    session.clear()
    logger.info(f"User logged out: user_id={user_id}")
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('main.login'))


# ===================================================
# SETTINGS & ACCOUNT MANAGEMENT ROUTES
# ===================================================

@bp.route('/settings')
@login_required
def settings():
    user = get_user_by_id(session['user_id'])
    return render_template('settings.html', user=user)


@bp.route('/settings/profile', methods=['POST'])
@login_required
def update_profile():
    user_id = session['user_id']
    user = get_user_by_id(user_id)

    full_name = request.form.get('full_name', '').strip()
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()

    if not full_name or not username or not email:
        flash('Full name, username, and email cannot be empty.', 'danger')
        return redirect(url_for('main.settings'))

    if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
        flash('Please enter a valid email address.', 'danger')
        return redirect(url_for('main.settings'))

    if username.lower() != user['username'].lower():
        existing_u = get_user_by_username(username)
        if existing_u and existing_u['user_id'] != user_id:
            flash('Username is already taken by another account.', 'danger')
            return redirect(url_for('main.settings'))

    if email.lower() != (user['email'] or '').lower():
        existing_e = get_user_by_email(email)
        if existing_e and existing_e['user_id'] != user_id:
            flash('Email address is already in use by another account.', 'danger')
            return redirect(url_for('main.settings'))

    update_user_profile(user_id, full_name, username, email)
    logger.info(f"Profile updated for user_id={user_id}")
    flash('Profile details updated successfully!', 'success')
    return redirect(url_for('main.settings'))


@bp.route('/settings/password', methods=['POST'])
@login_required
def change_password():
    user_id = session['user_id']
    user = get_user_by_id(user_id)

    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_new_password = request.form.get('confirm_new_password', '')

    if not current_password or not new_password or not confirm_new_password:
        flash('Please fill out all password fields.', 'danger')
        return redirect(url_for('main.settings'))

    if not check_password_hash(user['password_hash'], current_password):
        flash('Current password is incorrect.', 'danger')
        return redirect(url_for('main.settings'))

    if new_password != confirm_new_password:
        flash('New Password and Confirm New Password do not match.', 'danger')
        return redirect(url_for('main.settings'))

    if len(new_password) < 6:
        flash('New password must be at least 6 characters long.', 'danger')
        return redirect(url_for('main.settings'))

    new_hash = generate_password_hash(new_password)
    update_user_password(user_id, new_hash)
    logger.info(f"Password changed for user_id={user_id}")
    flash('Password changed successfully!', 'success')
    return redirect(url_for('main.settings'))


@bp.route('/settings/delete', methods=['POST'])
@login_required
def delete_account():
    user_id = session['user_id']
    confirm = request.form.get('confirm_delete')
    if confirm != 'DELETE':
        flash('Please type DELETE to confirm account deletion.', 'danger')
        return redirect(url_for('main.settings'))

    delete_user_account(user_id)
    session.clear()
    logger.info(f"Account deleted permanently: user_id={user_id}")
    flash('Your account and all associated data have been permanently deleted.', 'info')
    return redirect(url_for('main.login'))


# ===================================================
# MAIN PROTECTED APPLICATION ROUTES
# ===================================================

@bp.route('/')
@login_required
def index():
    user_id = session['user_id']
    user = get_user_by_id(user_id)
    user_allergy_ids = get_user_allergy_ids(user_id)
    allergens = get_all_allergens()
    
    selected_allergens = [a for a in allergens if a['allergen_id'] in user_allergy_ids]
    recent_scans = get_scan_history(user_id, limit=10)

    total_scans = len(recent_scans)
    allergens_flagged_count = sum(
        1 for s in recent_scans if any(r.get('is_user_allergy') == 1 for r in s.get('results', []))
    )
    last_scan_date = str(recent_scans[0]['created_at'])[:10] if recent_scans else "No scans yet"

    metrics = {
        'total_scans': total_scans,
        'allergens_flagged': allergens_flagged_count,
        'profile_allergens_count': len(selected_allergens),
        'last_scan': last_scan_date
    }
    
    return render_template(
        'index.html',
        user=user,
        selected_allergens=selected_allergens,
        recent_scans=recent_scans[:5],
        metrics=metrics
    )


@bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user_id = session['user_id']
    user = get_user_by_id(user_id)
    allergens = get_all_allergens()

    if request.method == 'POST':
        selected_ids = request.form.getlist('allergens')
        update_user_allergies(user_id, selected_ids)
        logger.info(f"Updated allergy profile for user_id={user_id}, count={len(selected_ids)}")
        flash('Allergy profile updated successfully!', 'success')
        return redirect(url_for('main.profile'))

    user_allergy_ids = get_user_allergy_ids(user_id)
    return render_template('profile.html', user=user, allergens=allergens, user_allergy_ids=user_allergy_ids)


@bp.route('/scan', methods=['GET', 'POST'])
@login_required
def scan():
    user_id = session['user_id']
    user = get_user_by_id(user_id)
    user_allergy_ids = get_user_allergy_ids(user_id)

    if request.method == 'POST':
        file = request.files.get('label_image')
        sample_choice = request.form.get('sample_choice')
        
        saved_filename = None
        uploads_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'uploads')

        if file and file.filename != '':
            saved_filename, error_msg = validate_and_save_upload(file, uploads_dir)
            if error_msg:
                flash(error_msg, 'danger')
                return redirect(url_for('main.scan'))
        elif sample_choice:
            sample_choice_clean = os.path.basename(sample_choice)
            if is_allowed_extension(sample_choice_clean):
                sample_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'sample_labels', sample_choice_clean)
                if os.path.exists(sample_path):
                    import uuid
                    ext = sample_choice_clean.rsplit('.', 1)[1].lower() if '.' in sample_choice_clean else 'jpg'
                    saved_filename = f"sample_{uuid.uuid4().hex[:8]}.{ext}"
                    dest_path = os.path.join(uploads_dir, saved_filename)
                    os.makedirs(uploads_dir, exist_ok=True)
                    with open(sample_path, 'rb') as sf, open(dest_path, 'wb') as df:
                        df.write(sf.read())

        if not saved_filename:
            flash('Please upload a valid label image file or select a sample label.', 'danger')
            return redirect(url_for('main.scan'))

        full_img_path = os.path.join(uploads_dir, saved_filename)
        rel_img_path = f"uploads/{saved_filename}"

        try:
            # Pipeline execution
            # 1. Image Preprocessing with OpenCV
            processed_img, _ = preprocess_image(full_img_path)

            # 2. OCR with pytesseract
            ocr_text, ocr_conf, is_reliable = extract_text_from_image(processed_img)

            # 3. Detection & Matching
            detected_items = detect_allergens_in_text(ocr_text)

            # 4. Personalisation Engine for currently logged-in user
            summary = evaluate_personalisation(
                detected_items, 
                user_allergy_ids, 
                is_ocr_reliable=is_reliable, 
                ocr_confidence=ocr_conf
            )

            # 5. Store in Database for user_id
            scan_id = save_scan(user_id, rel_img_path, ocr_text, ocr_conf)
            save_detection_results(scan_id, summary['all_detected_records'])

            logger.info(f"Scan processed successfully: scan_id={scan_id}, user_id={user_id}, ocr_conf={ocr_conf}")
            return redirect(url_for('main.result', scan_id=scan_id))

        except Exception as e:
            logger.error(f"Error processing food label scan for user_id={user_id}: {e}")
            flash('An error occurred while processing the food label image. Please try again with a clearer image.', 'danger')
            return redirect(url_for('main.scan'))

    samples_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'sample_labels')
    samples = []
    if os.path.exists(samples_dir):
        samples = [f for f in os.listdir(samples_dir) if is_allowed_extension(f)]

    return render_template('scan.html', samples=samples, user_allergy_count=len(user_allergy_ids))


@bp.route('/result/<int:scan_id>')
@login_required
def result(scan_id):
    user_id = session['user_id']
    user = get_user_by_id(user_id)
    
    # Server-Side Authorization Check: verify scan belongs to current user
    scan_data = get_scan_details(scan_id, user_id=user_id)
    if not scan_data:
        logger.warning(f"Unauthorized or invalid scan access attempt: scan_id={scan_id}, user_id={user_id}")
        flash('Scan result not found or access denied.', 'danger')
        return redirect(url_for('main.history')), 403

    user_allergy_ids = get_user_allergy_ids(user_id)
    
    detected_items = []
    for r in scan_data.get('results', []):
        detected_items.append({
            'category_code': r['category_code'],
            'category_name': r['category_name'],
            'matched_term': r['matched_term'],
            'evidence_text': r['evidence_text'],
            'statement_type': r['statement_type'],
            'confidence': r['confidence']
        })

    raw_text = scan_data.get('ocr_raw_text') or ''
    is_reliable = (scan_data.get('ocr_confidence', 0.0) >= 40.0) and (len(raw_text.strip()) >= 8)
    summary = evaluate_personalisation(
        detected_items, 
        user_allergy_ids, 
        is_ocr_reliable=is_reliable, 
        ocr_confidence=scan_data.get('ocr_confidence', 0.0)
    )

    return render_template('result.html', scan=scan_data, summary=summary)


@bp.route('/history')
@login_required
def history():
    user_id = session['user_id']
    scans = get_scan_history(user_id, limit=50)
    return render_template('history.html', scans=scans)
