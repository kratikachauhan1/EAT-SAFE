import os
import uuid
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename

from app.models import (
    get_default_user, get_all_allergens, get_user_allergy_ids,
    update_user_allergies, save_scan, save_detection_results,
    get_scan_details, get_scan_history
)
from app.preprocessing import preprocess_image
from app.ocr import extract_text_from_image
from app.allergen_detector import detect_allergens_in_text
from app.personalisation import evaluate_personalisation

bp = Blueprint('main', __name__)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'bmp', 'tiff'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@bp.route('/')
def index():
    user = get_default_user()
    user_allergy_ids = get_user_allergy_ids(user['user_id'])
    allergens = get_all_allergens()
    
    selected_allergens = [a for a in allergens if a['allergen_id'] in user_allergy_ids]
    recent_scans = get_scan_history(user['user_id'], limit=10)

    # Compute metrics for SaaS Dashboard
    total_scans = len(recent_scans)
    allergens_flagged_count = sum(
        1 for s in recent_scans if any(r.get('is_user_allergy') == 1 for r in s.get('results', []))
    )
    last_scan_date = recent_scans[0]['created_at'][:10] if recent_scans else "No scans yet"

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
def profile():
    user = get_default_user()
    allergens = get_all_allergens()

    if request.method == 'POST':
        selected_ids = request.form.getlist('allergens')
        update_user_allergies(user['user_id'], selected_ids)
        flash('Allergy profile updated successfully!', 'success')
        return redirect(url_for('main.profile'))

    user_allergy_ids = get_user_allergy_ids(user['user_id'])
    return render_template('profile.html', user=user, allergens=allergens, user_allergy_ids=user_allergy_ids)


@bp.route('/scan', methods=['GET', 'POST'])
def scan():
    user = get_default_user()
    user_allergy_ids = get_user_allergy_ids(user['user_id'])

    if request.method == 'POST':
        # Check if file uploaded or sample selected
        file = request.files.get('label_image')
        sample_choice = request.form.get('sample_choice')
        
        saved_filename = None
        uploads_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'uploads')
        os.makedirs(uploads_dir, exist_ok=True)

        if file and file.filename != '' and allowed_file(file.filename):
            ext = file.filename.rsplit('.', 1)[1].lower()
            saved_filename = f"scan_{uuid.uuid4().hex[:8]}.{ext}"
            file_path = os.path.join(uploads_dir, saved_filename)
            file.save(file_path)
        elif sample_choice:
            sample_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'sample_labels', sample_choice)
            if os.path.exists(sample_path):
                ext = sample_choice.rsplit('.', 1)[1].lower() if '.' in sample_choice else 'jpg'
                saved_filename = f"sample_{uuid.uuid4().hex[:8]}.{ext}"
                dest_path = os.path.join(uploads_dir, saved_filename)
                with open(sample_path, 'rb') as sf, open(dest_path, 'wb') as df:
                    df.write(sf.read())

        if not saved_filename:
            flash('Please upload a valid image file or choose a sample label.', 'danger')
            return redirect(url_for('main.scan'))

        full_img_path = os.path.join(uploads_dir, saved_filename)
        rel_img_path = f"uploads/{saved_filename}"

        # Pipeline execution
        # 1. Image Preprocessing with OpenCV
        processed_img, _ = preprocess_image(full_img_path)

        # 2. OCR with pytesseract
        ocr_text, ocr_conf, is_reliable = extract_text_from_image(processed_img)

        # 3. Detection & Matching
        detected_items = detect_allergens_in_text(ocr_text)

        # 4. Personalisation Engine
        summary = evaluate_personalisation(
            detected_items, 
            user_allergy_ids, 
            is_ocr_reliable=is_reliable, 
            ocr_confidence=ocr_conf
        )

        # 5. Store in Database
        scan_id = save_scan(user['user_id'], rel_img_path, ocr_text, ocr_conf)
        save_detection_results(scan_id, summary['all_detected_records'])

        return redirect(url_for('main.result', scan_id=scan_id))

    # Available sample label choices
    samples_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'sample_labels')
    samples = []
    if os.path.exists(samples_dir):
        samples = [f for f in os.listdir(samples_dir) if allowed_file(f)]

    return render_template('scan.html', samples=samples, user_allergy_count=len(user_allergy_ids))


@bp.route('/result/<int:scan_id>')
def result(scan_id):
    user = get_default_user()
    scan_data = get_scan_details(scan_id)
    if not scan_data:
        flash('Scan result not found.', 'danger')
        return redirect(url_for('main.history'))

    user_allergy_ids = get_user_allergy_ids(user['user_id'])
    
    # Reconstruct detection items for personalisation presentation
    detected_items = []
    for r in scan_data['results']:
        detected_items.append({
            'category_code': r['category_code'],
            'category_name': r['category_name'],
            'matched_term': r['matched_term'],
            'evidence_text': r['evidence_text'],
            'statement_type': r['statement_type'],
            'confidence': r['confidence']
        })

    is_reliable = (scan_data['ocr_confidence'] >= 40.0) and (len(scan_data['ocr_raw_text'].strip()) >= 8)
    summary = evaluate_personalisation(
        detected_items, 
        user_allergy_ids, 
        is_ocr_reliable=is_reliable, 
        ocr_confidence=scan_data['ocr_confidence']
    )

    return render_template('result.html', scan=scan_data, summary=summary)


@bp.route('/history')
def history():
    user = get_default_user()
    scans = get_scan_history(user['user_id'], limit=50)
    return render_template('history.html', scans=scans)
