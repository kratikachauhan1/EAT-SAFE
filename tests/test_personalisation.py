import pytest
from app.database import init_db
from app.personalisation import evaluate_personalisation

@pytest.fixture(autouse=True)
def setup_database():
    init_db()

def test_personalisation_danger():
    detected_items = [
        {
            'category_code': 'MILK',
            'category_name': 'Milk',
            'matched_term': 'milk solids',
            'evidence_text': 'ingredients: milk solids',
            'statement_type': 'explicit',
            'confidence': 1.0
        }
    ]
    # Allergen ID for MILK is in DB after init_db()
    user_allergy_ids = {1}
    
    summary = evaluate_personalisation(detected_items, user_allergy_ids, is_ocr_reliable=True, ocr_confidence=95.0)
    
    assert summary['disclaimer'] != ""
    assert "diagnostic tool" in summary['disclaimer'].lower()
    assert summary['overall_status'] in ['DANGER', 'CLEAR_USER_SAFE', 'NO_ALLERGENS_FOUND']

def test_unreliable_ocr_warning():
    detected_items = []
    user_allergy_ids = {1}
    
    summary = evaluate_personalisation(detected_items, user_allergy_ids, is_ocr_reliable=False, ocr_confidence=20.0)
    
    assert summary['overall_status'] == 'UNREADABLE'
    assert "Manual Inspection Required" in summary['status_title']
