import io
import json
import pytest
from werkzeug.security import generate_password_hash
from PIL import Image

from app import create_app
from app.database import init_db, get_db
from app.models import (
    create_user, save_scan, get_scan_details, get_user_allergy_ids,
    add_user_custom_allergen, get_user_custom_allergens
)
from app.services.auth_service import validate_password_strength, check_login_rate_limit, record_failed_login
from app.services.product_service import save_product, is_product_saved, get_user_saved_products, lookup_barcode


@pytest.fixture
def app():
    app = create_app({'TESTING': True, 'WTF_CSRF_ENABLED': False, 'SECRET_KEY': 'test-secret-prod'})
    with app.app_context():
        init_db()
        db = get_db()
        db.execute("DELETE FROM saved_products")
        db.execute("DELETE FROM detection_results")
        db.execute("DELETE FROM scans")
        db.execute("DELETE FROM user_custom_allergens")
        db.execute("DELETE FROM user_allergies")
        db.execute("DELETE FROM users")
        db.commit()
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def test_password_policy_validation():
    """Verify password strength validation rules."""
    valid, err = validate_password_strength("Short1!")
    assert not valid
    assert "8 characters" in err

    valid, err = validate_password_strength("123456789")
    assert not valid
    assert "letter" in err

    valid, err = validate_password_strength("abcdefgh")
    assert not valid
    assert "number or special" in err

    valid, err = validate_password_strength("StrongPass123!")
    assert valid
    assert err is None


def test_login_rate_limiting(client, app):
    """Verify login rate-limiting throttling locks account after 5 failed attempts."""
    with app.app_context():
        pwd_hash = generate_password_hash("Pass1234!")
        create_user("Rate User", "rateuser", "rateuser@example.com", pwd_hash)

    # 5 Failed login attempts
    for _ in range(5):
        client.post('/login', data={'login_input': 'rateuser', 'password': 'WrongPassword!'}, follow_redirects=True)

    # 6th attempt should trigger rate limiting lockout
    res = client.post('/login', data={'login_input': 'rateuser', 'password': 'Pass1234!'}, follow_redirects=True)
    assert b"temporarily locked" in res.data or b"multiple failed login attempts" in res.data


def test_strict_user_data_isolation(client, app):
    """Prove User B cannot view, save, or delete User A's scans or custom terms."""
    with app.app_context():
        pwd = generate_password_hash("Pass1234!")
        user_a_id = create_user("User Alpha", "useralpha", "useralpha@example.com", pwd)
        user_b_id = create_user("User Beta", "userbeta", "userbeta@example.com", pwd)

        # User A creates scan and custom term
        scan_a_id = save_scan(user_a_id, "uploads/scan_alpha.jpg", "Alpha ingredients text", 95.0)
        custom_a_id = add_user_custom_allergen(user_a_id, "Monosodium Glutamate")

    # Log in as User B
    client.post('/login', data={'login_input': 'userbeta', 'password': 'Pass1234!'}, follow_redirects=True)

    # 1. User B tries to view User A's scan result -> Forbidden (403)
    res_view = client.get(f'/result/{scan_a_id}')
    assert res_view.status_code == 403 or b"access denied" in res_view.data

    # 2. User B tries to delete User A's custom term -> custom term remains belonging to User A
    client.post(f'/profile/custom/delete/{custom_a_id}', follow_redirects=True)
    with app.app_context():
        terms_a = get_user_custom_allergens(user_a_id)
        assert len(terms_a) == 1

    # 3. User B tries to delete User A's scan history -> scan remains
    client.post(f'/history/delete/{scan_a_id}', follow_redirects=True)
    with app.app_context():
        scan_a = get_scan_details(scan_a_id)
        assert scan_a is not None


def test_saved_products_flow(client, app):
    """Test saving and unsaving scanned products."""
    with app.app_context():
        pwd = generate_password_hash("Pass1234!")
        user_id = create_user("Save User", "saveuser", "saveuser@example.com", pwd)
        scan_id = save_scan(user_id, "uploads/save_test.jpg", "Test ingredients list", 90.0)

    # Login
    client.post('/login', data={'login_input': 'saveuser', 'password': 'Pass1234!'}, follow_redirects=True)

    # Save Product
    res_save = client.post(f'/products/save/{scan_id}', data={'product_name': 'Organic Biscuit'}, follow_redirects=True)
    assert res_save.status_code == 200

    with app.app_context():
        assert is_product_saved(user_id, scan_id)
        saved_list = get_user_saved_products(user_id)
        assert len(saved_list) == 1
        assert saved_list[0]['product_name'] == 'Organic Biscuit'

    # Unsave Product
    res_unsave = client.post(f'/products/unsave/{scan_id}', follow_redirects=True)
    assert res_unsave.status_code == 200

    with app.app_context():
        assert not is_product_saved(user_id, scan_id)


def test_onboarding_and_data_export(client, app):
    """Test onboarding flow and GDPR data export."""
    client.post('/register', data={
        'full_name': 'Export User',
        'username': 'exportuser',
        'email': 'exportuser@example.com',
        'password': 'Password123!',
        'confirm_password': 'Password123!'
    }, follow_redirects=True)

    # Onboarding POST
    res_onboard = client.post('/onboarding', data={'allergens': ['1', '2']}, follow_redirects=True)
    assert res_onboard.status_code == 200

    # Data Export GET
    res_export = client.get('/settings/export')
    assert res_export.status_code == 200
    assert res_export.mimetype == 'application/json'
    export_json = json.loads(res_export.data)
    assert export_json['account_info']['username'] == 'exportuser'
    assert 'monitored_allergens' in export_json


def test_barcode_lookup_provider():
    """Verify barcode provider abstraction handles invalid inputs gracefully."""
    found, data, msg = lookup_barcode("invalid_barcode_text")
    assert not found
    assert "digits only" in msg or "not found" in msg


def test_version_and_health_endpoints(client):
    """Verify /version and /health endpoints return valid JSON and status 200."""
    res_version = client.get('/version')
    assert res_version.status_code == 200
    version_data = json.loads(res_version.data)
    assert version_data['application'] == 'EAT SAFE'
    assert 'version' in version_data
    assert version_data['status'] == 'ok'

    res_health = client.get('/health')
    assert res_health.status_code == 200
    health_data = json.loads(res_health.data)
    assert health_data['status'] == 'healthy'
    assert health_data['database'] == 'connected'
    assert 'version' in health_data

