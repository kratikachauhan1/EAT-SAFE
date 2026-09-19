import io
import pytest
from werkzeug.security import generate_password_hash
from app import create_app
from app.database import init_db, get_db
from app.models import create_user, save_scan, update_user_allergies
from PIL import Image

@pytest.fixture
def app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key-security'
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

def test_health_check_endpoint(client):
    res = client.get('/health')
    assert res.status_code == 200
    data = res.get_json()
    assert data['status'] == 'healthy'
    assert data['database'] == 'connected'

def test_resource_authorization_isolation(client, app):
    """Verify User B cannot access User A's scan result by altering scan_id in URL."""
    with app.app_context():
        pwd_hash = generate_password_hash("Pass1234!")
        user_a = create_user("User A", "usera", "usera@example.com", pwd_hash)
        user_b = create_user("User B", "userb", "userb@example.com", pwd_hash)
        
        # User A saves scan
        scan_id_a = save_scan(user_a, "uploads/scan_a.png", "User A ingredients", 95.0)

    # Log in as User B
    client.post('/login', data={'login_input': 'userb', 'password': 'Pass1234!'}, follow_redirects=True)

    # User B attempts to view User A's scan result URL directly
    res = client.get(f'/result/{scan_id_a}')
    assert res.status_code == 403 or b"Scan result not found or access denied" in res.data

def test_invalid_upload_handling(client, app):
    # Register and log in
    client.post('/register', data={
        'full_name': 'Uploader User',
        'username': 'uploader',
        'email': 'uploader@example.com',
        'password': 'Password123!',
        'confirm_password': 'Password123!'
    }, follow_redirects=True)

    # 1. Non-image text file disguised as .png
    bad_file = (io.BytesIO(b"This is not a real image file content"), 'malicious.png')
    res = client.post('/scan', data={'label_image': bad_file}, follow_redirects=True)
    assert b"corrupted or not a valid image" in res.data or b"Unsupported" in res.data

    # 2. Unsupported extension
    exe_file = (io.BytesIO(b"MZ executable header"), 'script.exe')
    res = client.post('/scan', data={'label_image': exe_file}, follow_redirects=True)
    assert b"Unsupported file format" in res.data or b"corrupted" in res.data

def test_valid_image_upload(client, app):
    client.post('/register', data={
        'full_name': 'Valid User',
        'username': 'validuser',
        'email': 'valid@example.com',
        'password': 'Password123!',
        'confirm_password': 'Password123!'
    }, follow_redirects=True)

    # Create a real PIL Image in memory
    img = Image.new('RGB', (100, 100), color='white')
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='JPEG')
    img_byte_arr.seek(0)
    valid_file = (img_byte_arr, 'test_label.jpg')

    res = client.post('/scan', data={'label_image': valid_file}, follow_redirects=True)
    assert res.status_code == 200
    assert b"Analysis" in res.data or b"Result" in res.data or b"No monitored" in res.data
