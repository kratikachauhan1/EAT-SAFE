import os
from app.database import init_db
from app.models import (
    get_default_user, get_all_allergens, get_user_allergy_ids,
    update_user_allergies, save_scan, save_detection_results,
    get_scan_details, get_scan_history
)
from app.nlp import normalize_text
from app.allergen_detector import detect_allergens_in_text
from app.personalisation import evaluate_personalisation

def test_end_to_end_flow():
    print("--- 1. Initializing Database ---")
    init_db()
    
    user = get_default_user()
    print(f"Default User ID: {user['user_id']}, Username: {user['username']}")

    allergens = get_all_allergens()
    print(f"Total FSSAI Allergen Categories in KB: {len(allergens)}")

    name_to_id = {a['category_name']: a['allergen_id'] for a in allergens}
    
    milk_id = name_to_id.get('Milk')
    peanut_id = name_to_id.get('Peanut')
    
    selected_ids = [milk_id, peanut_id]
    update_user_allergies(user['user_id'], selected_ids)
    
    active_allergy_ids = get_user_allergy_ids(user['user_id'])
    print(f"Configured User Allergy Profile IDs: {active_allergy_ids}")

    print("\n--- 2. Simulating Label OCR Extraction & Preprocessing ---")
    sample_label_text = (
        "CHOCOLATE BISCUITS\n"
        "INGREDIENTS: Wheat flour, sugar, milk solids, cocoa powder, soya lecithin.\n"
        "CONTAINS: MILK, GLUTEN, SOY.\n"
        "MAY CONTAIN: Peanuts and tree nuts."
    )
    print(f"Sample Label Input:\n{sample_label_text}\n")

    print("--- 3. Running NLP & Allergen Detection Engine ---")
    detected_items = detect_allergens_in_text(sample_label_text)
    print(f"Total Allergen Matches Found on Label: {len(detected_items)}")
    for d in detected_items:
        print(f" -> [{d['statement_type'].upper()}] Category: {d['category_name']}, Term: '{d['matched_term']}', Snippet: '{d['evidence_text']}'")

    print("\n--- 4. Running Personalisation Engine ---")
    summary = evaluate_personalisation(detected_items, active_allergy_ids, is_ocr_reliable=True, ocr_confidence=92.5)
    
    print(f"Personalised Status Code: {summary['overall_status']}")
    print(f"Status Title: {summary['status_title']}")
    print(f"Status Message: {summary['status_message']}")
    print(f"Explicit Warnings Count: {len(summary['user_explicit_warnings'])}")
    print(f"Precautionary Cautions Count: {len(summary['user_precautionary_cautions'])}")
    print(f"Safety Disclaimer Present: {bool(summary['disclaimer'])}")

    print("\n--- 5. Saving Scan Record to SQLite ---")
    scan_id = save_scan(user['user_id'], "uploads/sample_milk_peanut_biscuit.png", sample_label_text, 92.5)
    save_detection_results(scan_id, summary['all_detected_records'])
    print(f"Scan saved with ID: {scan_id}")

    print("\n--- 6. Verifying Database Retrieval ---")
    scan_record = get_scan_details(scan_id)
    print(f"Retrieved Scan #{scan_record['scan_id']} with {len(scan_record['results'])} detection records.")

    history = get_scan_history(user['user_id'])
    print(f"Total Scans in User History: {len(history)}")

    print("\n[SUCCESS] End-to-End Pipeline Test Completed Successfully!")

if __name__ == '__main__':
    test_end_to_end_flow()
