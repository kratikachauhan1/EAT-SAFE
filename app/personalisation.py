from app.models import get_all_allergens

def evaluate_personalisation(detected_items, user_allergy_ids, is_ocr_reliable=True, ocr_confidence=0.0, user_custom_terms=None, ocr_raw_text=""):
    """
    Intersects detected allergens with the user's active allergy profile IDs and custom monitored terms.
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

    # Check for custom user-monitored ingredient terms in label text
    matched_custom_terms = []
    if user_custom_terms and ocr_raw_text:
        text_lower = ocr_raw_text.lower()
        for custom_item in user_custom_terms:
            t_name = custom_item.get('term_name', '') if isinstance(custom_item, dict) else str(custom_item)
            if t_name and t_name.strip().lower() in text_lower:
                matched_custom_terms.append(t_name.strip())

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
        status_title = "PERSONAL ALLERGEN WARNING DETECTED!"
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
    elif matched_custom_terms:
        overall_status = "CAUTION"
        status_color = "caution"
        status_title = "Custom Monitored Ingredient Match Detected"
        status_message = (
            f"Ingredients matching your custom monitored terms were detected on this label: "
            f"{', '.join(sorted(set(matched_custom_terms)))}."
        )
    elif other_detected_results:
        overall_status = "CLEAR_USER_SAFE"
        status_color = "info"
        status_title = "No Monitored Allergen Detected for Your Profile"
        status_message = (
            "No monitored allergen matching your active profile was detected in the scanned label text. "
            "However, other allergen categories were present on the product label."
        )
    else:
        overall_status = "NO_ALLERGENS_FOUND"
        status_color = "success"
        status_title = "No Monitored Allergen Identified"
        status_message = "No monitored FSSAI allergen terms were detected in the scanned label text."

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
        'matched_custom_terms': matched_custom_terms,
        'all_detected_records': matched_user_results + other_detected_results,
        'user_selected_allergies': user_allergy_names,
        'disclaimer': (
            "IMPORTANT SAFETY DISCLAIMER: EATSAFE is an assistive label-screening aid and not a medical diagnostic tool "
            "or guarantee of food safety. Results depend on the text successfully extracted from the label. "
            "Always inspect the physical packaging manually before consumption."
        )
    }

    return summary
