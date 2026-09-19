import os
import sys
import logging
from flask import Flask, render_template, jsonify
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

def create_app():
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates'),
        static_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static')
    )

    env = os.environ.get('FLASK_ENV', 'development')
    is_prod = env.lower() == 'production'

    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'allergen-detector-secret-key-2026')
    app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024))
    app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'uploads'))

    # Security Cookies Configuration
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = is_prod

    # Initialize Database Schema & Seed Allergens
    init_db()

    app.teardown_appcontext(close_db)

    # Health Check Endpoint
    @app.route('/health')
    def health_check():
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            return jsonify({
                "status": "healthy",
                "database": "connected",
                "environment": env
            }), 200
        except Exception as e:
            logger.error(f"Health check failed - Database unavailable: {e}")
            return jsonify({
                "status": "unhealthy",
                "database": "disconnected",
                "environment": env
            }), 503

    # Error Handlers
    @app.errorhandler(400)
    def bad_request(e):
        return render_template('error.html', error_code=400, error_title="Bad Request", error_message="The request could not be processed due to invalid syntax or parameters."), 400

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('error.html', error_code=403, error_title="Access Forbidden", error_message="You do not have permission to access or modify this resource."), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template('error.html', error_code=404, error_title="Page Not Found", error_message="The requested resource or page could not be found."), 404

    @app.errorhandler(413)
    def file_too_large(e):
        return render_template('error.html', error_code=413, error_title="File Too Large", error_message="The uploaded food label image exceeds the maximum allowed size limit (16 MB)."), 413

    @app.errorhandler(500)
    def server_error(e):
        logger.error(f"Internal Server Error: {e}")
        return render_template('error.html', error_code=500, error_title="Internal Server Error", error_message="An unexpected internal error occurred. Please try again later."), 500

    # Register Blueprints
    from app.routes import bp as main_bp
    app.register_blueprint(main_bp)

    logger.info(f"EATSAFE Application initialized successfully [Env: {env}]")
    return app
