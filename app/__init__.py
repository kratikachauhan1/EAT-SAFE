import os
import sys
import logging
from datetime import timedelta
from flask import Flask, render_template, jsonify, request
from flask_wtf.csrf import CSRFProtect, CSRFError
from dotenv import load_dotenv
from app.database import init_db, close_db, get_db

# Load environment variables from .env file
load_dotenv()

# Configure Application Logger
logger = logging.getLogger('eatsafe')
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s in %(module)s: %(message)s'))
if not logger.handlers:
    logger.addHandler(handler)

from werkzeug.middleware.proxy_fix import ProxyFix

csrf = CSRFProtect()

def get_git_revision():
    # 1. Check environment variable from Render / Docker ARG
    commit = os.environ.get('RENDER_GIT_COMMIT', os.environ.get('COMMIT_SHA', os.environ.get('BUILD_COMMIT', '')))
    if commit:
        return commit[:7]
    # 2. Try git command if repo exists locally
    try:
        import subprocess
        git_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.git')
        if os.path.exists(git_dir):
            return subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], stderr=subprocess.DEVNULL).decode('utf-8').strip()
    except Exception:
        pass
    # 3. Fallback commit hash
    return '9f90082'

def create_app(config_overrides=None):
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates'),
        static_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static')
    )

    # Wrap WSGI app with ProxyFix so Flask recognizes HTTPS scheme, client IP, host, and port behind reverse proxies
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)

    # Production vs Development environment detection (Render/Dockerfile sets ENVIRONMENT=production)
    env = os.environ.get('ENVIRONMENT', os.environ.get('FLASK_ENV', os.environ.get('APP_ENV', 'development'))).lower()
    if config_overrides and 'ENVIRONMENT' in config_overrides:
        env = config_overrides['ENVIRONMENT'].lower()
    is_prod = (env == 'production')
    build_commit = get_git_revision()

    app.config['BUILD_COMMIT'] = build_commit
    app.config['ENVIRONMENT'] = env

    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'eatsafe-production-secret-key-2026-secure')
    app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024))
    app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'uploads'))
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

    if config_overrides:
        app.config.update(config_overrides)

    # Mobile Device & Reverse Proxy Session Cookies Configuration
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_REFRESH_EACH_REQUEST'] = True
    
    # Allow SESSION_COOKIE_SECURE override from env, or default to False to prevent mobile session drop on HTTP/mixed deployments
    session_secure_env = os.environ.get('SESSION_COOKIE_SECURE', '').lower()
    if session_secure_env == 'true':
        app.config['SESSION_COOKIE_SECURE'] = True
    elif session_secure_env == 'false':
        app.config['SESSION_COOKIE_SECURE'] = False
    else:
        app.config['SESSION_COOKIE_SECURE'] = False

    # CSRF Configuration for Testing vs Production
    if 'WTF_CSRF_ENABLED' not in app.config:
        app.config['WTF_CSRF_ENABLED'] = not app.config.get('TESTING', False)

    # Initialize CSRF Protection
    csrf.init_app(app)

    # Automatic Static Asset Versioning (Cache-Busting for CSS/JS)
    @app.url_defaults
    def add_static_version(endpoint, values):
        if endpoint == 'static':
            filename = values.get('filename')
            if filename and 'v' not in values:
                file_path = os.path.join(app.static_folder, filename)
                if os.path.exists(file_path):
                    mtime = int(os.path.getmtime(file_path))
                    values['v'] = f"{build_commit}-{mtime}"
                else:
                    values['v'] = build_commit

    # HTTP Cache Control headers for static assets & dynamic HTML security
    @app.after_request
    def set_cache_headers(response):
        if request.endpoint == 'static':
            if 'v' in request.args:
                response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
            else:
                response.headers['Cache-Control'] = 'no-cache, must-revalidate'
        else:
            # Prevent caching of dynamic user HTML & API routes by CDNs, proxies, or shared browser history
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response

    # Initialize Database Schema & Seed Allergens
    init_db()

    app.teardown_appcontext(close_db)

    # Deployment Version Verification Endpoint
    @app.route('/version')
    def version_check():
        return jsonify({
            "app": "EAT SAFE",
            "application": "EAT SAFE",
            "environment": env,
            "version": "3b9d835088e3bd8efc6ecf7b3b32dd748927a5ef",
            "commit": build_commit,
            "status": "ok"
        }), 200

    # Production Diagnostic Debug Endpoint
    @app.route('/__deployment_debug')
    def deployment_debug():
        return jsonify({
            "application": "EAT SAFE",
            "environment": env,
            "git_commit": build_commit,
            "build_version": f"2.0.0-{build_commit}",
            "python_version": sys.version,
            "application_module": app.__module__,
            "template_directory": app.template_folder,
            "static_directory": app.static_folder,
            "status": "ok"
        }), 200

    # Health & Readiness Monitoring Endpoints
    @app.route('/health')
    @app.route('/ready')
    def health_check():
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            return jsonify({
                "status": "healthy",
                "database": "connected",
                "environment": env,
                "version": build_commit
            }), 200
        except Exception as e:
            logger.error(f"Health check failed - Database unavailable: {e}")
            return jsonify({
                "status": "unhealthy",
                "database": "disconnected",
                "environment": env,
                "version": build_commit
            }), 503

    # Global Security & HTTP Error Handlers
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        logger.warning(f"CSRF validation failed: {e.description}")
        if request.is_json:
            return jsonify({'status': 'error', 'message': 'CSRF token missing or invalid.'}), 400
        from flask import flash, redirect, url_for
        flash('Security token expired or session mismatch. Please try signing in again.', 'warning')
        return redirect(url_for('main.login'))

    @app.errorhandler(400)
    def bad_request(e):
        return render_template('error.html', error_code=400, error_title="Bad Request", error_message="The request could not be processed due to invalid parameters or syntax."), 400

    @app.errorhandler(401)
    def unauthorized(e):
        return render_template('error.html', error_code=401, error_title="Authentication Required", error_message="Please log in to access this page or resource."), 401

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('error.html', error_code=403, error_title="Access Forbidden", error_message="You do not have permission to view or modify this resource."), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template('error.html', error_code=404, error_title="Page Not Found", error_message="The requested page or resource could not be found."), 404

    @app.errorhandler(413)
    def file_too_large(e):
        return render_template('error.html', error_code=413, error_title="File Too Large", error_message="The uploaded food label image exceeds the maximum allowed size limit (16 MB)."), 413

    @app.errorhandler(429)
    def rate_limit_exceeded(e):
        return render_template('error.html', error_code=429, error_title="Too Many Requests", error_message="You have sent too many requests. Please wait a few minutes before trying again."), 429

    @app.errorhandler(500)
    def server_error(e):
        logger.error(f"Internal Server Error: {e}")
        return render_template('error.html', error_code=500, error_title="Internal Server Error", error_message="An unexpected internal server error occurred. Please try again later."), 500

    # Register Application Blueprints
    from app.routes import bp as main_bp
    app.register_blueprint(main_bp)

    logger.info(f"EATSAFE Production Application initialized successfully [Env: {env}]")
    return app

