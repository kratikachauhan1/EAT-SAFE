import os
import re
import json
import uuid
import logging
from functools import wraps
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash,
    session, jsonify, make_response
)
from app.personalisation import evaluate_personalisation
from werkzeug.security import generate_password_hash, check_password_hash

from app.database import get_db, is_postgres
from app.models import (
    create_user, get_user_by_id, get_user_by_email, get_user_by_username,
    get_user_by_email_or_username, update_user_profile, update_user_password,
    get_all_allergens, get_user_allergy_ids, update_user_allergies,
    get_user_custom_allergens, add_user_custom_allergen, delete_user_custom_allergen,
    get_scan_details, get_scan_history, get_paginated_scan_history, delete_user_scan,
    get_dashboard_metrics, complete_user_onboarding
)
from app.services.storage_service import storage_service
from app.services.scan_service import (
    create_and_enqueue_scan, get_scan_status, _SCAN_STATUS_MAP
)
from app.services.auth_service import (
    validate_password_strength, check_login_rate_limit, record_failed_login,
    clear_login_rate_limit, export_user_data, delete_user_account_complete
)
from app.services.product_service import (
    save_product, unsave_product, get_user_saved_products, is_product_saved, lookup_barcode
)
from app.upload_utils import is_allowed_extension

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
    return dict(current_user=user, str=str)


# ===================================================
# PUBLIC LANDING & AUTHENTICATION ROUTES
# ===================================================

@bp.route('/')
def index():
    if 'user_id' in session and get_user_by_id(session.get('user_id')):
        return redirect(url_for('main.dashboard'))
    return render_template('landing.html')


@bp.route('/dashboard')
@login_required
def dashboard():
    user_id = session['user_id']
    user = get_user_by_id(user_id)
    user_allergy_ids = get_user_allergy_ids(user_id)
    allergens = get_all_allergens()
    
    selected_allergens = [a for a in allergens if a['allergen_id'] in user_allergy_ids]
    recent_scans = get_scan_history(user_id, limit=5)
    saved_products = get_user_saved_products(user_id)[:4]
    metrics = get_dashboard_metrics(user_id)

    return render_template(
        'index.html',
        user=user,
        selected_allergens=selected_allergens,
        recent_scans=recent_scans,
        saved_products=saved_products,
        metrics=metrics
    )


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session and get_user_by_id(session.get('user_id')):
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Validations
        if not full_name or not username or not email or not password or not confirm_password:
            flash('All required fields must be filled.', 'danger')
            return render_template('register.html')

        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            flash('Please enter a valid email address.', 'danger')
            return render_template('register.html')

        if not re.match(r'^[a-zA-Z0-9_]{3,30}$', username):
            flash('Username must be 3-30 characters long and contain only letters, numbers, or underscores.', 'danger')
            return render_template('register.html')

        if password != confirm_password:
            flash('Password and Confirm Password do not match.', 'danger')
            return render_template('register.html')

        is_strong, pwd_err = validate_password_strength(password)
        if not is_strong:
            flash(pwd_err, 'danger')
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
            session.permanent = True
            flash('Account created successfully! Welcome to EAT SAFE.', 'success')
            return redirect(url_for('main.onboarding'))
        except Exception as e:
            logger.error(f"Error creating user '{username}': {e}")
            flash('An error occurred while creating your account. Please try again.', 'danger')
            return render_template('register.html')

    return render_template('register.html')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session and get_user_by_id(session.get('user_id')):
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        login_input = request.form.get('login_input', '').strip()
        password = request.form.get('password', '')
        remember_me = bool(request.form.get('remember_me'))

        if not login_input or not password:
            flash('Please enter your username/email and password.', 'danger')
            return render_template('login.html')

        # Check login rate limiting / lockout
        allowed, limit_msg = check_login_rate_limit(login_input)
        if not allowed:
            flash(limit_msg, 'danger')
            return render_template('login.html')

        user = get_user_by_email_or_username(login_input)
        if not user or not user.get('password_hash') or not check_password_hash(user['password_hash'], password):
            record_failed_login(login_input)
            logger.warning(f"Failed login attempt for input: '{login_input}'")
            flash('Invalid username/email or password.', 'danger')
            return render_template('login.html')

        # Successful Login
        clear_login_rate_limit(login_input)
        session.clear()
        session['user_id'] = user['user_id']
        session.permanent = remember_me

        logger.info(f"User logged in successfully: user_id={user['user_id']}")
        flash(f"Welcome back, {user.get('full_name') or user['username']}!", 'success')

        next_page = request.args.get('next')
        if next_page and next_page.startswith('/') and not next_page.startswith('//'):
            return redirect(next_page)
        return redirect(url_for('main.dashboard'))

    return render_template('login.html')


@bp.route('/logout')
def logout():
    user_id = session.get('user_id')
    session.clear()
    logger.info(f"User logged out: user_id={user_id}")
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('main.login'))


@bp.route('/onboarding', methods=['GET', 'POST'])
@login_required
def onboarding():
    user_id = session['user_id']
    user = get_user_by_id(user_id)
    allergens = get_all_allergens()

    if request.method == 'POST':
        selected_ids = request.form.getlist('allergens')
        update_user_allergies(user_id, selected_ids)
        complete_user_onboarding(user_id)
        flash('Your allergen profile is configured! You are ready to scan your first food label.', 'success')
        return redirect(url_for('main.scan'))

    user_allergy_ids = get_user_allergy_ids(user_id)
    return render_template('onboarding.html', user=user, allergens=allergens, user_allergy_ids=user_allergy_ids)


# ===================================================
# FOOD LABEL & BARCODE SCANNING
# ===================================================

@bp.route('/scan', methods=['GET', 'POST'])
def scan():
    user_id = session.get('user_id')
    is_logged_in = bool(user_id and get_user_by_id(user_id))
    user_allergy_ids = get_user_allergy_ids(user_id) if is_logged_in else set()
    user_custom_terms = get_user_custom_allergens(user_id) if is_logged_in else []

    if request.method == 'POST':
        file = request.files.get('label_image')
        sample_choice = request.form.get('sample_choice')
        
        saved_filename = None
        rel_img_path = None
        full_img_path = None

        if file and file.filename != '':
            rel_img_path, error_msg = storage_service.save_file(file)
            if error_msg:
                flash(error_msg, 'danger')
                return redirect(url_for('main.scan'))
            full_img_path = os.path.abspath(os.path.join(storage_service.upload_folder, os.path.basename(rel_img_path)))

        elif sample_choice:
            sample_choice_clean = os.path.basename(sample_choice)
            if is_allowed_extension(sample_choice_clean):
                sample_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'sample_labels', sample_choice_clean)
                if os.path.exists(sample_path):
                    ext = sample_choice_clean.rsplit('.', 1)[1].lower() if '.' in sample_choice_clean else 'jpg'
                    saved_filename = f"sample_{uuid.uuid4().hex[:8]}.{ext}"
                    dest_path = os.path.abspath(os.path.join(storage_service.upload_folder, saved_filename))
                    with open(sample_path, 'rb') as sf, open(dest_path, 'wb') as df:
                        df.write(sf.read())
                    rel_img_path = f"uploads/{saved_filename}"
                    full_img_path = dest_path

        if not rel_img_path:
            flash('Please upload a valid food label image file or select a sample label.', 'danger')
            return redirect(url_for('main.scan'))

        # Run Scan Pipeline Task
        scan_id = create_and_enqueue_scan(
            full_img_path,
            rel_img_path,
            user_id=user_id if is_logged_in else None,
            user_allergy_ids=user_allergy_ids,
            user_custom_terms=user_custom_terms,
            async_mode=False # Immediate synchronous processing for smooth UX
        )

        if is_logged_in:
            return redirect(url_for('main.result', scan_id=scan_id))
        else:
            session['guest_scan'] = _SCAN_STATUS_MAP.get(scan_id, {}).get('summary', {})
            session['guest_img_path'] = rel_img_path
            return redirect(url_for('main.guest_result'))

    samples_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'sample_labels')
    samples = []
    if os.path.exists(samples_dir):
        samples = [f for f in os.listdir(samples_dir) if is_allowed_extension(f)]

    return render_template('scan.html', samples=samples, user_allergy_count=len(user_allergy_ids))


@bp.route('/scan/barcode', methods=['GET', 'POST'])
def scan_barcode():
    if request.method == 'POST':
        barcode = request.form.get('barcode', '').strip()
        found, product_data, msg = lookup_barcode(barcode)
        if not found or not product_data:
            flash(msg, 'warning')
            return render_template('barcode_scan.html', barcode=barcode)

        if not product_data.get('is_complete'):
            flash(msg, 'info')
            return render_template('barcode_result.html', product=product_data, is_complete=False)

        # Evaluate ingredients from barcode API
        user_id = session.get('user_id')
        is_logged_in = bool(user_id and get_user_by_id(user_id))
        user_allergy_ids = get_user_allergy_ids(user_id) if is_logged_in else set()
        user_custom_terms = get_user_custom_allergens(user_id) if is_logged_in else []

        from app.allergen_detector import detect_allergens_in_text
        from app.personalisation import evaluate_personalisation

        raw_text = product_data['ingredients_text']
        detected_items = detect_allergens_in_text(raw_text)
        summary = evaluate_personalisation(
            detected_items,
            user_allergy_ids,
            is_ocr_reliable=True,
            ocr_confidence=100.0,
            user_custom_terms=user_custom_terms,
            ocr_raw_text=raw_text
        )
        return render_template('barcode_result.html', product=product_data, summary=summary, is_complete=True)

    return render_template('barcode_scan.html')


@bp.route('/api/scans/<int:scan_id>/status')
def api_scan_status(scan_id):
    """Real-time scan processing status polling API."""
    status_info = get_scan_status(scan_id)
    if not status_info:
        return jsonify({'status': 'not_found', 'message': 'Scan ID not found'}), 404
    return jsonify(status_info)


@bp.route('/result/guest')
def guest_result():
    summary = session.get('guest_scan')
    rel_img_path = session.get('guest_img_path', '')
    if not summary:
        flash('No recent guest scan found. Please upload a label to scan.', 'info')
        return redirect(url_for('main.scan'))

    scan_record = {
        'scan_id': 0,
        'image_path': rel_img_path,
        'ocr_raw_text': summary.get('status_message', ''),
        'ocr_confidence': summary.get('ocr_confidence', 0.0)
    }

    return render_template(
        'result.html',
        scan=scan_record,
        summary=summary,
        is_guest=True,
        is_saved=False
    )


@bp.route('/result/<int:scan_id>')
@login_required
def result(scan_id):
    user_id = session['user_id']
    
    # Server-Side Authorization Check: verify scan belongs to current user
    scan_data = get_scan_details(scan_id, user_id=user_id)
    if not scan_data:
        logger.warning(f"Unauthorized scan access attempt: scan_id={scan_id}, user_id={user_id}")
        flash('Scan result not found or access denied.', 'danger')
        return redirect(url_for('main.history')), 403

    user_allergy_ids = get_user_allergy_ids(user_id)
    user_custom_terms = get_user_custom_allergens(user_id)
    
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
        ocr_confidence=scan_data.get('ocr_confidence', 0.0),
        user_custom_terms=user_custom_terms,
        ocr_raw_text=raw_text
    )

    saved_flag = is_product_saved(user_id, scan_id)
    return render_template('result.html', scan=scan_data, summary=summary, is_guest=False, is_saved=saved_flag)


# ===================================================
# SAVED PRODUCTS & BARCODE API
# ===================================================

@bp.route('/products')
@login_required
def saved_products():
    user_id = session['user_id']
    saved = get_user_saved_products(user_id)
    return render_template('saved_products.html', saved_products=saved)


@bp.route('/products/save/<int:scan_id>', methods=['POST'])
@login_required
def save_product_action(scan_id):
    user_id = session['user_id']
    product_name = request.form.get('product_name')
    notes = request.form.get('notes')
    success, msg = save_product(user_id, scan_id, product_name=product_name, notes=notes)
    flash(msg, 'success' if success else 'danger')
    return redirect(url_for('main.result', scan_id=scan_id))


@bp.route('/products/unsave/<int:scan_id>', methods=['POST'])
@login_required
def unsave_product_action(scan_id):
    user_id = session['user_id']
    unsave_product(user_id, scan_id)
    flash('Product removed from your saved products list.', 'info')
    return redirect(url_for('main.saved_products'))


# ===================================================
# ALLERGEN PROFILE & SEARCH API
# ===================================================

@bp.route('/api/allergens/search')
def api_search_allergens():
    q = request.args.get('q', '').strip()
    group = request.args.get('group', '').strip()
    allergens = get_all_allergens(search_query=q, group_filter=group)
    return jsonify({'status': 'success', 'allergens': allergens, 'count': len(allergens)})


@bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user_id = session['user_id']
    allergens = get_all_allergens()
    custom_allergens = get_user_custom_allergens(user_id)

    if request.method == 'POST':
        selected_ids = request.form.getlist('allergens')
        update_user_allergies(user_id, selected_ids)
        logger.info(f"Updated allergy profile for user_id={user_id}, count={len(selected_ids)}")
        flash('Allergy profile updated successfully!', 'success')
        return redirect(url_for('main.profile'))

    user_allergy_ids = get_user_allergy_ids(user_id)
    return render_template(
        'profile.html',
        allergens=allergens,
        user_allergy_ids=user_allergy_ids,
        custom_allergens=custom_allergens
    )


@bp.route('/profile/custom', methods=['POST'])
@login_required
def add_custom_allergen():
    user_id = session['user_id']
    term_name = request.form.get('term_name', '').strip()
    description = request.form.get('description', '').strip()

    if not term_name:
        flash('Please enter an ingredient or term name to monitor.', 'danger')
        return redirect(url_for('main.profile'))

    add_user_custom_allergen(user_id, term_name, description)
    logger.info(f"Custom allergen added for user_id={user_id}: '{term_name}'")
    flash(f"Added '{term_name}' to your custom monitored terms list!", 'success')
    return redirect(url_for('main.profile'))


@bp.route('/profile/custom/delete/<int:custom_id>', methods=['POST'])
@login_required
def delete_custom_allergen(custom_id):
    user_id = session['user_id']
    delete_user_custom_allergen(user_id, custom_id)
    flash('Custom monitored term removed.', 'info')
    return redirect(url_for('main.profile'))


# ===================================================
# SCAN HISTORY & HISTORY DELETE
# ===================================================

@bp.route('/history')
@login_required
def history():
    user_id = session['user_id']
    page = request.args.get('page', 1, type=int)
    query = request.args.get('q', '').strip()
    status_filter = request.args.get('status', 'all').strip()
    sort_order = request.args.get('sort', 'newest').strip()

    history_data = get_paginated_scan_history(
        user_id,
        page=page,
        per_page=12,
        search_query=query,
        status_filter=status_filter,
        sort_order=sort_order
    )
    return render_template('history.html', history=history_data, query=query, status_filter=status_filter, sort_order=sort_order)


@bp.route('/history/delete/<int:scan_id>', methods=['POST'])
@login_required
def delete_scan_action(scan_id):
    user_id = session['user_id']
    success = delete_user_scan(user_id, scan_id)
    if success:
        flash('Scan record and associated image file removed.', 'info')
    else:
        flash('Could not delete scan record or access denied.', 'danger')
    return redirect(url_for('main.history'))


# ===================================================
# SETTINGS, DATA EXPORT & ACCOUNT DELETION
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

    is_strong, pwd_err = validate_password_strength(new_password)
    if not is_strong:
        flash(pwd_err, 'danger')
        return redirect(url_for('main.settings'))

    new_hash = generate_password_hash(new_password)
    update_user_password(user_id, new_hash)
    logger.info(f"Password changed for user_id={user_id}")
    flash('Password changed successfully!', 'success')
    return redirect(url_for('main.settings'))


@bp.route('/settings/export')
@login_required
def export_data_action():
    user_id = session['user_id']
    payload = export_user_data(user_id)
    if not payload:
        flash('Could not export account data.', 'danger')
        return redirect(url_for('main.settings'))

    json_str = json.dumps(payload, indent=2)
    response = make_response(json_str)
    response.headers['Content-Type'] = 'application/json'
    response.headers['Content-Disposition'] = f'attachment; filename=eatsafe_export_user_{user_id}.json'
    return response


@bp.route('/settings/delete', methods=['POST'])
@login_required
def delete_account():
    user_id = session['user_id']
    confirm = request.form.get('confirm_delete')
    if confirm != 'DELETE':
        flash('Please type DELETE to confirm account deletion.', 'danger')
        return redirect(url_for('main.settings'))

    delete_user_account_complete(user_id)
    session.clear()
    logger.info(f"Account deleted permanently: user_id={user_id}")
    flash('Your account and all associated scan data/images have been permanently deleted.', 'info')
    return redirect(url_for('main.login'))


# ===================================================
# REST API ENDPOINTS
# ===================================================

@bp.route('/api/me')
@login_required
def api_me():
    user_id = session['user_id']
    user = get_user_by_id(user_id)
    allergies = list(get_user_allergy_ids(user_id))
    custom_terms = get_user_custom_allergens(user_id)
    metrics = get_dashboard_metrics(user_id)

    return jsonify({
        'status': 'success',
        'user': {
            'user_id': user['user_id'],
            'full_name': user.get('full_name'),
            'username': user.get('username'),
            'email': user.get('email')
        },
        'allergies': allergies,
        'custom_terms': custom_terms,
        'metrics': metrics
    })
