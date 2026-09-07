import os
from flask import Flask
from app.database import init_db

def create_app():
    app = Flask(__name__, 
                template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates'),
                static_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static'))
    
    app.config['SECRET_KEY'] = 'allergen-detector-secret-key-2026'
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max upload

    # Initialize Database and Seed FSSAI Allergens
    init_db()

    # Register Blueprints
    from app.routes import bp as main_bp
    app.register_blueprint(main_bp)

    return app
