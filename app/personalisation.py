from app.models import get_all_allergens

def evaluate_personalisation(detected_items, user_allergy_ids, is_ocr_reliable=True, ocr_confidence=0.0):
    """
    Intersects detected allergens with the user's allergy profile IDs.
    Returns:
        personal_summary (dict): Categorized results, status flag, and explanation notes.
    """
    all_db_allergens = get_all_allergens()
    category_code_to_id = {a['category_code']: a['allergen_id'] for a in all_db_allergens}
    category_id_to_name = {a['allergen_id']: a['category_name'] for a in all_db_allergens}

    matched_user_results = []
    other_detected_results = []

    user_explicit_warnings = []
    user_precautionary_cautions = []

    for item in detected_items:
        cat_code = item['category_code']
        allergen_id = category_code_to_id.get(cat_code)
        
        is_user_allergy = False
        if allergen_id and allergen_id in user_allergy_ids:
            is_user_allergy = True

        res_record = {
            'allergen_id': allergen_id,
            'category_name': item['category_name'],
            'category_code': cat_code,
            'matched_term': item['matched_term'],
            'evidence_text': item['evidence_text'],
            'statement_type': item['statement_type'],
            'is_user_allergy': 1 if is_user_allergy else 0,
            'confidence': item.get('confidence', 1.0)
        }

        if is_user_allergy:
            matched_user_results.append(res_record)
            if item['statement_type'] == 'explicit':
                user_explicit_warnings.append(res_record)
            else:
                user_precautionary_cautions.append(res_record)
        else:
            other_detected_results.append(res_record)

    # Determine overall status code and user-facing title
    if not is_ocr_reliable:
        overall_status = "UNREADABLE"
        status_color = "warning"
        status_title = "Low OCR Confidence - Manual Inspection Required"
        status_message = (
            "The label image text could not be read with high reliability. "
            "Please check the physical packaging manually before consuming or upload a clearer photo."
        )
    elif user_explicit_warnings:
        overall_status = "DANGER"
        status_color = "danger"
        status_title = "PERSONALALLERGEN WARNING DETECTED!"
        status_message = (
            f"Explicit ingredients matching your personal allergy profile were found on this label: "
            f"{', '.join(sorted(set(w['category_name'] for w in user_explicit_warnings)))}."
        )
    elif user_precautionary_cautions:
        overall_status = "CAUTION"
        status_color = "caution"
        status_title = "Precautionary Allergen Caution"
        status_message = (
            f"Precautionary statements ('May contain') matching your allergy profile were detected: "
            f"{', '.join(sorted(set(w['category_name'] for w in user_precautionary_cautions)))}."
        )
    elif other_detected_results:
        overall_status = "CLEAR_USER_SAFE"
        status_color = "info"
        status_title = "No Selected Allergens Detected"
        status_message = (
            "None of your selected personal allergens were detected in the readable label text. "
            "However, other allergens were found on the product label."
        )
    else:
        overall_status = "NO_ALLERGENS_FOUND"
        status_color = "success"
        status_title = "No Allergens Identified"
        status_message = "No major FSSAI allergen terms were identified in the scanned label text."

    user_allergy_names = [category_id_to_name.get(aid, "Unknown") for aid in user_allergy_ids]

    summary = {
        'overall_status': overall_status,
        'status_color': status_color,
        'status_title': status_title,
        'status_message': status_message,
        'is_ocr_reliable': is_ocr_reliable,
        'ocr_confidence': ocr_confidence,
        'user_explicit_warnings': user_explicit_warnings,
        'user_precautionary_cautions': user_precautionary_cautions,
        'other_detected_results': other_detected_results,
        'all_detected_records': matched_user_results + other_detected_results,
        'user_selected_allergies': user_allergy_names,
        'disclaimer': (
            "IMPORTANT SAFETY DISCLAIMER: Personalised Allergen Detection is an assistive screening aid "
            "and not a medical diagnostic tool or guarantee of 100% safety. "
            "Always inspect the physical packaging manually before consumption."
        )
    }

    return summary
