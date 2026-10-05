import pytest
from app import create_app
from app.allergen_detector import detect_allergens_in_text


@pytest.fixture
def client():
    app = create_app({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test_key_secret'
    })
    with app.test_client() as client:
        yield client


def test_public_routes_how_it_works_and_about(client):
    res_how = client.get('/how-it-works')
    assert res_how.status_code == 200
    assert b"How EAT SAFE Works" in res_how.data
    assert b"Tesseract OCR Extraction" in res_how.data

    res_about = client.get('/about')
    assert res_about.status_code == 200
    assert b"About EAT SAFE" in res_about.data
    assert b"FSSAI Food Safety Regulations" in res_about.data


def test_tabbed_auth_containers(client):
    res_login = client.get('/login')
    assert res_login.status_code == 200
    assert b"auth-back-link" in res_login.data
    assert b"auth-tab" in res_login.data
    assert b"Keep me signed in" in res_login.data

    res_reg = client.get('/register')
    assert res_reg.status_code == 200
    assert b"auth-back-link" in res_reg.data
    assert b"auth-tab" in res_reg.data


def test_barcode_scanner_page(client):
    res = client.get('/scan/barcode')
    assert res.status_code == 200
    assert b"Html5Qrcode" in res.data
    assert b"Start Live Camera Barcode Scanner" in res.data


def test_derivative_allergen_detection():
    text = "Ingredients: wheat flour, sodium caseinate, whey powder, arachis oil, albumin, soya lecithin."
    results = detect_allergens_in_text(text)
    matched_codes = {r['category_code'] for r in results}
    
    assert 'MILK' in matched_codes
    assert 'EGG' in matched_codes
    assert 'PEANUT' in matched_codes
    assert 'SOY' in matched_codes
    assert 'GLUTEN' in matched_codes
