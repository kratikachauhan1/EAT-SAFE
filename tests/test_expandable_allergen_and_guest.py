import pytest
from werkzeug.security import generate_password_hash
from app import create_app
from app.database import init_db, get_db
from app.models import (
    create_user, update_user_allergies, get_user_custom_allergens, add_user_custom_allergen, delete_user_custom_allergen,
    get_all_allergens
)

@pytest.fixture
def app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key-12345'
    with app.app_context():
        init_db()
        db = get_db()
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

def test_public_landing_and_guest_scan(client):
    # 1. Public Landing Page accessible without login
    res_land = client.get('/')
    assert res_land.status_code == 200
    assert b"EAT SAFE" in res_land.data
    assert b"Scan Ingredients Now" in res_land.data or b"Guest" in res_land.data

    # 2. Public Scan page accessible without login
    res_scan = client.get('/scan')
    assert res_scan.status_code == 200
    assert b"Guest Scan Mode" in res_scan.data or b"Scan Food Label" in res_scan.data

    # 3. Guest scan submission using sample label
    res_post = client.post('/scan', data={
        'sample_choice': 'sample_milk_peanut_biscuit.png'
    }, follow_redirects=True)
    assert res_post.status_code == 200
    assert b"Guest Scan Mode Result" in res_post.data or b"Create Free Profile" in res_post.data or b"General Allergen Detection" in res_post.data

def test_allergen_live_search_api(client, app):
    with app.app_context():
        # Test full search
        all_items = get_all_allergens()
        assert len(all_items) > 10

        # Test search endpoint
        res = client.get('/api/allergens/search?q=milk')
        assert res.status_code == 200
        payload = res.get_json()
        assert payload['status'] == 'success'
        items = payload['allergens']
        assert len(items) >= 1
        assert any('milk' in item['category_name'].lower() for item in items)

        # Test group filter
        res_group = client.get('/api/allergens/search?group=Nuts%20%26%20Seeds')
        assert res_group.status_code == 200
        group_items = res_group.get_json()['allergens']
        assert len(group_items) >= 1

def test_user_custom_allergens_management(client, app):
    with app.app_context():
        pass_hash = generate_password_hash("Pass1234!")
        user_id = create_user("Custom User", "customu", "customu@example.com", pass_hash)

    # Login
    client.post('/login', data={'login_input': 'customu', 'password': 'Pass1234!'}, follow_redirects=True)

    # Add custom allergen
    res_add = client.post('/profile/custom', data={
        'term_name': 'Maltodextrin',
        'description': 'Monitored additive'
    }, follow_redirects=True)
    assert res_add.status_code == 200

    with app.app_context():
        custom_terms = get_user_custom_allergens(user_id)
        assert len(custom_terms) == 1
        assert custom_terms[0]['term_name'].lower() == 'maltodextrin'
        custom_id = custom_terms[0]['custom_id']

    # Delete custom allergen
    res_del = client.post(f'/profile/custom/delete/{custom_id}', follow_redirects=True)
    assert res_del.status_code == 200

    with app.app_context():
        custom_terms_after = get_user_custom_allergens(user_id)
        assert len(custom_terms_after) == 0

def test_personalization_custom_term_scan_detection(client, app):
    with app.app_context():
        pass_hash = generate_password_hash("Pass1234!")
        user_id = create_user("Term User", "termu", "termu@example.com", pass_hash)
        update_user_allergies(user_id, [1]) # Milk
        add_user_custom_allergen(user_id, "Peanut")

    # Login and scan sample label containing Milk and Peanut
    client.post('/login', data={'login_input': 'termu', 'password': 'Pass1234!'}, follow_redirects=True)

    res_scan = client.post('/scan', data={
        'sample_choice': 'sample_milk_peanut_biscuit.png'
    }, follow_redirects=True)

    assert res_scan.status_code == 200
    assert (
        b"PERSONAL ALLERGEN WARNING" in res_scan.data or
        b"Custom Monitored Ingredient" in res_scan.data or
        b"Milk" in res_scan.data or
        b"Peanut" in res_scan.data
    )
