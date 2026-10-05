import os
import uuid
import logging
from concurrent.futures import ThreadPoolExecutor
from flask import session

from app.database import get_db, close_connection, is_postgres
from app.models import (
    save_scan, save_detection_results, get_scan_details,
    get_user_allergy_ids, get_user_custom_allergens
)
from app.preprocessing import preprocess_image
from app.ocr import extract_text_from_image
from app.allergen_detector import detect_allergens_in_text
from app.personalisation import evaluate_personalisation

logger = logging.getLogger('eatsafe')

# Thread pool for asynchronous background scan processing
executor = ThreadPoolExecutor(max_workers=4)

# In-memory status progress tracking map for active scans
# { scan_id: { 'status': 'QUEUED'|'PROCESSING'|'COMPLETED'|'FAILED', 'step': str, 'progress': int, 'error': str } }
_SCAN_STATUS_MAP = {}


def get_scan_status(scan_id):
    """Retrieve current in-memory status or query database record."""
    if scan_id in _SCAN_STATUS_MAP:
        return _SCAN_STATUS_MAP[scan_id]
        
    scan_data = get_scan_details(scan_id)
    if scan_data:
        status = scan_data.get('status', 'COMPLETED')
        return {
            'scan_id': scan_id,
            'status': status,
            'step': 'Scan report ready' if status == 'COMPLETED' else 'Processing completed',
            'progress': 100 if status == 'COMPLETED' else 0,
            'error': scan_data.get('error_message')
        }
    return None


def update_scan_db_status(scan_id, status, ocr_text=None, ocr_conf=None, error_message=None):
    """Update status, OCR text, and error details in database."""
    conn = get_db()
    cursor = conn.cursor()
    pg = is_postgres()
    
    query_parts = ["status = %s" if pg else "status = ?"]
    params = [status]
    
    if ocr_text is not None:
        query_parts.append("ocr_raw_text = %s" if pg else "ocr_raw_text = ?")
        params.append(ocr_text)
    if ocr_conf is not None:
        query_parts.append("ocr_confidence = %s" if pg else "ocr_confidence = ?")
        params.append(ocr_conf)
    if error_message is not None:
        query_parts.append("error_message = %s" if pg else "error_message = ?")
        params.append(error_message)

    params.append(scan_id)
    where_clause = "WHERE scan_id = %s" if pg else "WHERE scan_id = ?"
    sql = f"UPDATE scans SET {', '.join(query_parts)} {where_clause}"
    
    cursor.execute(sql, tuple(params))
    conn.commit()
    close_connection(conn)


def process_scan_pipeline_task(scan_id, full_img_path, rel_img_path, user_id, user_allergy_ids, user_custom_terms):
    """
    Background worker task executing full food label screening pipeline:
    1. Image Preprocessing with OpenCV
    2. OCR Text Extraction with Tesseract
    3. NLP & Deterministic Allergen Detection
    4. Profile Personalisation Evaluation
    5. Database Results Persistence
    """
    _SCAN_STATUS_MAP[scan_id] = {
        'scan_id': scan_id,
        'status': 'PROCESSING',
        'step': 'Image Preprocessing (OpenCV)',
        'progress': 20,
        'error': None
    }
    
    try:
        # 1. Preprocessing
        processed_img, _ = preprocess_image(full_img_path)
        _SCAN_STATUS_MAP[scan_id].update({
            'step': 'OCR Label Text Reading (Tesseract)',
            'progress': 40
        })

        # 2. OCR Extraction
        ocr_text, ocr_conf, is_reliable = extract_text_from_image(processed_img)
        _SCAN_STATUS_MAP[scan_id].update({
            'step': 'Allergen Knowledge Base Matching',
            'progress': 60
        })

        # 3. Detection
        detected_items = detect_allergens_in_text(ocr_text)
        _SCAN_STATUS_MAP[scan_id].update({
            'step': 'Personalised Risk Evaluation',
            'progress': 80
        })

        # 4. Personalisation
        summary = evaluate_personalisation(
            detected_items,
            user_allergy_ids,
            is_ocr_reliable=is_reliable,
            ocr_confidence=ocr_conf,
            user_custom_terms=user_custom_terms,
            ocr_raw_text=ocr_text
        )

        # 5. Persist
        if scan_id > 0:
            update_scan_db_status(scan_id, 'COMPLETED', ocr_text=ocr_text, ocr_conf=ocr_conf)
            save_detection_results(scan_id, summary['all_detected_records'])

        _SCAN_STATUS_MAP[scan_id] = {
            'scan_id': scan_id,
            'status': 'COMPLETED',
            'step': 'Analysis Complete',
            'progress': 100,
            'error': None,
            'summary': summary
        }
        logger.info(f"Scan pipeline completed successfully for scan_id={scan_id}")

    except Exception as e:
        logger.error(f"Error in scan background worker task for scan_id={scan_id}: {e}")
        err_msg = "Could not complete label scan analysis. Please ensure the image is clear and try again."
        if scan_id > 0:
            update_scan_db_status(scan_id, 'FAILED', error_message=err_msg)
        _SCAN_STATUS_MAP[scan_id] = {
            'scan_id': scan_id,
            'status': 'FAILED',
            'step': 'Scan Failed',
            'progress': 0,
            'error': err_msg
        }


def create_and_enqueue_scan(full_img_path, rel_img_path, user_id=None, user_allergy_ids=None, user_custom_terms=None, async_mode=True):
    """
    Creates scan record, initializes status, and enqueues task into worker thread pool.
    """
    if user_id:
        scan_id = save_scan(user_id, rel_img_path, "", 0.0)
        update_scan_db_status(scan_id, 'QUEUED')
    else:
        scan_id = -1 # Guest scan transient ID

    user_allergy_ids = user_allergy_ids or set()
    user_custom_terms = user_custom_terms or []

    _SCAN_STATUS_MAP[scan_id] = {
        'scan_id': scan_id,
        'status': 'QUEUED',
        'step': 'Queued for processing',
        'progress': 10,
        'error': None
    }

    if async_mode:
        executor.submit(
            process_scan_pipeline_task,
            scan_id,
            full_img_path,
            rel_img_path,
            user_id,
            user_allergy_ids,
            user_custom_terms
        )
    else:
        process_scan_pipeline_task(
            scan_id,
            full_img_path,
            rel_img_path,
            user_id,
            user_allergy_ids,
            user_custom_terms
        )

    return scan_id
