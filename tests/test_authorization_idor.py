import json
import pytest
from werkzeug.security import generate_password_hash
from app import create_app
from app.database import init_db, get_db
from app.models import (
    create_user, get_user_by_id, save_scan, get_scan_details,
    add_user_custom_allergen, get_user_custom_allergens
)
from app.services.product_service import save_product, is_product_saved


@pytest.fixture
def app():
    test_app = create_app({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-idor-secret-key-2026',
        'ENVIRONMENT': 'development'
    })
    with test_app.app_context():
        init_db()
        db = get_db()
        db.execute("DELETE FROM saved_products")
        db.execute("DELETE FROM detection_results")
        db.execute("DELETE FROM scans")
        db.execute("DELETE FROM user_custom_allergens")
        db.execute("DELETE FROM user_allergies")
        db.execute("DELETE FROM users")
        db.commit()
    yield test_app


@pytest.fixture
def client(app):
    return app.test_client()


def create_test_user(app, username, email, password="Password123!"):
    with app.app_context():
        pwd_hash = generate_password_hash(password)
        uid = create_user(username.capitalize(), username, email, pwd_hash)
        return uid


# ===================================================
# 1. SCAN RESULTS AUTHORIZATION & IDOR
# ===================================================

def test_user_cannot_access_another_users_scan(app):
    """Ensure User B cannot view User A's scan result details (IDOR protection)."""
    user_a_id = create_test_user(app, "alice_scan", "alice_scan@example.com")
    user_b_id = create_test_user(app, "bob_scan", "bob_scan@example.com")

    with app.app_context():
        scan_a_id = save_scan(
            user_a_id,
            "uploads/alice_confidential_label.jpg",
            "Ingredients: wheat flour, milk solids",
            95.0
        )

    # Bob logs in and tries to access Alice's scan
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = user_b_id

    res = client.get(f'/result/{scan_a_id}', follow_redirects=False)
    # Must be forbidden (403) or redirect to history without leaking Alice's scan
    assert res.status_code in [403, 302]
    if res.status_code == 302:
        assert '/history' in res.headers.get('Location', '')

    # Verify Alice's scan is still intact
    with app.app_context():
        details = get_scan_details(scan_a_id, user_id=user_a_id)
        assert details is not None
        assert details['user_id'] == user_a_id


def test_user_cannot_delete_another_users_scan(app):
    """Ensure User B cannot delete User A's scan record via POST /history/delete/{scan_id}."""
    user_a_id = create_test_user(app, "alice_del", "alice_del@example.com")
    user_b_id = create_test_user(app, "bob_del", "bob_del@example.com")

    with app.app_context():
        scan_a_id = save_scan(user_a_id, "uploads/alice_item.jpg", "Ingredients: peanuts", 90.0)

    # Bob logs in and sends delete request targeting Alice's scan
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = user_b_id

    res = client.post(f'/history/delete/{scan_a_id}', follow_redirects=True)
    assert res.status_code == 200

    # Scan must still exist for Alice
    with app.app_context():
        details = get_scan_details(scan_a_id, user_id=user_a_id)
        assert details is not None
        assert details['scan_id'] == scan_a_id


# ===================================================
# 2. SAVED PRODUCTS AUTHORIZATION & IDOR
# ===================================================

def test_user_cannot_save_or_unsave_another_users_scan(app):
    """Ensure User B cannot save another user's scan or unsave their products."""
    user_a_id = create_test_user(app, "alice_prod", "alice_prod@example.com")
    user_b_id = create_test_user(app, "bob_prod", "bob_prod@example.com")

    with app.app_context():
        scan_a_id = save_scan(user_a_id, "uploads/alice_cookies.jpg", "wheat, sugar", 88.0)
        # Alice saves her product
        save_product(user_a_id, scan_a_id, product_name="Alice's Cookies")

    # Bob logs in and tries to save Alice's scan to his own saved products
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = user_b_id

    res = client.post(f'/products/save/{scan_a_id}', data={'product_name': "Bob's Stolen Item"}, follow_redirects=True)
    # The application denies access and returns 403 or redirects away
    assert res.status_code in [403, 200, 302]

    with app.app_context():
        # Bob must NOT have this product saved
        assert not is_product_saved(user_b_id, scan_a_id)
        # Alice's product must remain saved
        assert is_product_saved(user_a_id, scan_a_id)

    # Bob tries to unsave Alice's product
    res_unsave = client.post(f'/products/unsave/{scan_a_id}', follow_redirects=True)
    assert res_unsave.status_code in [200, 302]

    with app.app_context():
        # Alice's product must STILL be saved
        assert is_product_saved(user_a_id, scan_a_id)


def test_user_saved_products_list_isolation(app):
    """Ensure User B's /products page does not display User A's saved items."""
    user_a_id = create_test_user(app, "alice_list", "alice_list@example.com")
    user_b_id = create_test_user(app, "bob_list", "bob_list@example.com")

    with app.app_context():
        scan_a_id = save_scan(user_a_id, "uploads/alice_unique_item.jpg", "oats", 90.0)
        save_product(user_a_id, scan_a_id, product_name="Unique Alice Biscuit 998877")

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = user_b_id

    res = client.get('/products')
    assert res.status_code == 200
    assert "Unique Alice Biscuit 998877" not in res.get_data(as_text=True)


# ===================================================
# 3. CUSTOM ALLERGENS AUTHORIZATION & IDOR
# ===================================================

def test_user_cannot_delete_another_users_custom_allergen(app):
    """Ensure User B cannot delete User A's custom monitored allergen."""
    user_a_id = create_test_user(app, "alice_cust", "alice_cust@example.com")
    user_b_id = create_test_user(app, "bob_cust", "bob_cust@example.com")

    with app.app_context():
        custom_id_a = add_user_custom_allergen(user_a_id, "Monosodium Glutamate", "Causes headaches")

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = user_b_id

    # Bob attempts to delete Alice's custom allergen
    res = client.post(f'/profile/custom/delete/{custom_id_a}', follow_redirects=True)
    assert res.status_code == 200

    # Alice's custom allergen must still exist
    with app.app_context():
        alice_allergens = get_user_custom_allergens(user_a_id)
        assert any(a['term_name'] == "Monosodium Glutamate" for a in alice_allergens)


# ===================================================
# 4. GDPR DATA EXPORT & ACCOUNT ISOLATION
# ===================================================

def test_export_data_only_contains_authenticated_user_records(app):
    """Ensure /settings/export only exports the current user's data and not other users."""
    user_a_id = create_test_user(app, "alice_export", "alice_export@example.com")
    user_b_id = create_test_user(app, "bob_export", "bob_export@example.com")

    with app.app_context():
        scan_a_id = save_scan(user_a_id, "uploads/alice_secret.jpg", "milk", 99.0)
        save_product(user_a_id, scan_a_id, product_name="Alice Secret Cheese")

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = user_b_id

    res = client.get('/settings/export')
    assert res.status_code == 200
    export_json = json.loads(res.data)

    # Bob's export must reflect Bob's profile, not Alice's
    assert export_json['account_info']['user_id'] == user_b_id
    assert export_json['account_info']['username'] == 'bob_export'
    assert "Alice Secret Cheese" not in str(export_json)


def test_cache_control_headers_on_authenticated_and_dynamic_pages(app):
    """Verify dynamic routes serve strict no-store headers to prevent CDN/proxy account caching."""
    client = app.test_client()
    user_id = create_test_user(app, "cache_user", "cache_user@example.com")

    with client.session_transaction() as sess:
        sess['user_id'] = user_id

    routes_to_test = ['/dashboard', '/profile', '/settings', '/products', '/history']
    for r in routes_to_test:
        resp = client.get(r)
        cc = resp.headers.get('Cache-Control', '')
        assert 'no-store' in cc, f"Route {r} missing 'no-store' in Cache-Control"
        assert 'private' in cc, f"Route {r} missing 'private' in Cache-Control"
