import pytest
from werkzeug.security import generate_password_hash
from app import create_app
from app.database import init_db, get_db
from app.models import (
    create_user, get_user_by_username, get_user_by_id,
    update_user_allergies, get_user_allergy_ids, save_scan, get_scan_history
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
        db.execute("DELETE FROM user_allergies")
        db.execute("DELETE FROM users")
        db.commit()
    yield app

@pytest.fixture
def client(app):
    return app.test_client()

def test_registration_and_login(client):
    # TEST 1: Create Account -> account created -> redirect/login works
    res = client.post('/register', data={
        'full_name': 'User One',
        'username': 'user1',
        'email': 'user1@example.com',
        'password': 'Password123!',
        'confirm_password': 'Password123!'
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b"user1" in res.data or b"User One" in res.data

    # Log out after registration to test unauthenticated & invalid login paths
    client.get('/logout')

    # TEST 2: Wrong password -> login rejected with flash message
    res = client.post('/login', data={
        'login_input': 'user1',
        'password': 'WrongPassword!'
    }, follow_redirects=True)
    assert b"Invalid username/email or password" in res.data

    # TEST 3: Correct login -> Dashboard opens
    res = client.post('/login', data={
        'login_input': 'user1',
        'password': 'Password123!'
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b"user1" in res.data or b"User One" in res.data

    # TEST 4: Logout -> protected pages require login
    res = client.get('/logout', follow_redirects=True)
    assert res.status_code == 200
    assert b"Welcome Back to EAT SAFE" in res.data or b"Sign in" in res.data

    # Public Landing Page is accessible without login
    res_public = client.get('/', follow_redirects=False)
    assert res_public.status_code == 200

    # TEST 11: Directly open protected URL (/profile) while logged out -> redirect to Login
    res = client.get('/profile', follow_redirects=False)
    assert res.status_code == 302
    assert '/login' in res.location

def test_user_allergy_and_scan_isolation(client, app):
    with app.app_context():
        pass_hash = generate_password_hash("Pass1234!")
        user_a_id = create_user("User A", "usera", "usera@example.com", pass_hash)
        user_b_id = create_user("User B", "userb", "userb@example.com", pass_hash)
        
        update_user_allergies(user_a_id, [1])
        update_user_allergies(user_b_id, [2])

    # TEST 5 & 6: User A vs User B Allergy Profiles
    client.post('/login', data={'login_input': 'usera', 'password': 'Pass1234!'}, follow_redirects=True)
    res_a = client.get('/profile')
    assert res_a.status_code == 200
    client.get('/logout')

    client.post('/login', data={'login_input': 'userb', 'password': 'Pass1234!'}, follow_redirects=True)
    res_b = client.get('/profile')
    assert res_b.status_code == 200

    with app.app_context():
        user_a_allergies = get_user_allergy_ids(user_a_id)
        user_b_allergies = get_user_allergy_ids(user_b_id)
        assert user_a_allergies == {1}
        assert user_b_allergies == {2}

    # TEST 7 & 8: Scan History Isolation
    with app.app_context():
        scan_id_a = save_scan(user_a_id, "uploads/scan_a.png", "User A label text", 95.0)
        scan_id_b = save_scan(user_b_id, "uploads/scan_b.png", "User B label text", 90.0)

        history_a = get_scan_history(user_a_id)
        history_b = get_scan_history(user_b_id)
        
        assert len(history_a) == 1
        assert history_a[0]['scan_id'] == scan_id_a
        assert len(history_b) == 1
        assert history_b[0]['scan_id'] == scan_id_b

    # Verify User B cannot see User A's scan history item
    res_h_b = client.get('/history')
    assert f"Scan #{scan_id_b}".encode() in res_h_b.data
    assert f"Scan #{scan_id_a}".encode() not in res_h_b.data

    client.get('/logout')
    client.post('/login', data={'login_input': 'usera', 'password': 'Pass1234!'}, follow_redirects=True)
    res_h_a = client.get('/history')
    assert f"Scan #{scan_id_a}".encode() in res_h_a.data
    assert f"Scan #{scan_id_b}".encode() not in res_h_a.data

def test_change_password_and_delete_account(client, app):
    client.post('/register', data={
        'full_name': 'Test User',
        'username': 'testuser',
        'email': 'test@example.com',
        'password': 'OldPassword123!',
        'confirm_password': 'OldPassword123!'
    }, follow_redirects=True)
    
    # TEST 9: Change password
    res_cp = client.post('/settings/password', data={
        'current_password': 'OldPassword123!',
        'new_password': 'NewPassword123!',
        'confirm_new_password': 'NewPassword123!'
    }, follow_redirects=True)
    assert b"Password changed successfully" in res_cp.data or res_cp.status_code == 200

    client.get('/logout')
    res_bad = client.post('/login', data={'login_input': 'testuser', 'password': 'OldPassword123!'}, follow_redirects=True)
    assert b"Invalid username/email or password" in res_bad.data

    res_good = client.post('/login', data={'login_input': 'testuser', 'password': 'NewPassword123!'}, follow_redirects=True)
    assert res_good.status_code == 200

    # TEST 10: Delete account
    res_del = client.post('/settings/delete', data={'confirm_delete': 'DELETE'}, follow_redirects=True)
    assert b"permanently deleted" in res_del.data or b"Welcome Back" in res_del.data or res_del.status_code == 200

    client.get('/logout')
    res_after_del = client.post('/login', data={'login_input': 'testuser', 'password': 'NewPassword123!'}, follow_redirects=True)
    assert b"Invalid username/email or password" in res_after_del.data
