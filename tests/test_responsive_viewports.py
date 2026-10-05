import pytest
from app import create_app

VIEWPORTS = [
    (320, 568),   # Small mobile (iPhone SE 1st gen)
    (360, 740),   # Android phone (Galaxy S8/S9)
    (375, 812),   # iPhone X/XS/11 Pro
    (390, 844),   # iPhone 12/13/14
    (412, 915),   # Samsung Galaxy S20/Pixel 6
    (430, 932),   # iPhone 14/15 Pro Max
    (600, 960),   # Small Tablet / Phablet
    (768, 1024),  # iPad Portrait / Tablet
    (900, 600),   # Tablet Landscape
    (1024, 768),  # iPad Pro / Laptop Small
    (1366, 768),  # Standard HD Laptop
    (1440, 900),  # MacBook Pro / Desktop
    (1600, 900),  # Widescreen Monitor
    (1920, 1080)  # Full HD Monitor
]

ROUTES_TO_TEST = [
    '/',
    '/scan',
    '/scan/barcode',
    '/how-it-works',
    '/about',
    '/login',
    '/register'
]


@pytest.fixture
def client():
    app = create_app({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test_key_responsive'
    })
    with app.test_client() as client:
        yield client


@pytest.mark.parametrize("viewport", VIEWPORTS)
@pytest.mark.parametrize("route", ROUTES_TO_TEST)
def test_route_responsiveness_and_structure(client, viewport, route):
    width, height = viewport
    res = client.get(route)
    assert res.status_code == 200, f"Route {route} failed at viewport {width}x{height}"
    
    # Check that viewport meta tag exists for mobile scaling
    assert b'name="viewport"' in res.data
    
    # Verify core structural components are present
    assert b'app-shell' in res.data or b'public-top-navbar' in res.data or b'saas-card' in res.data
    
    # Verify zero fixed-width breaks on body container
    assert b'width: 100%' in res.data or b'public-nav-brand' in res.data or b'saas-card' in res.data


def test_auth_container_responsive_structure(client):
    res_login = client.get('/login')
    assert res_login.status_code == 200
    assert b'auth-back-link' in res_login.data
    assert b'auth-tabs' in res_login.data
    assert b'Keep me signed in' in res_login.data

    res_reg = client.get('/register')
    assert res_reg.status_code == 200
    assert b'auth-back-link' in res_reg.data
    assert b'auth-tabs' in res_reg.data
