from flask import Flask
from routes.route import main
from models.db import db
from routes.route import limiter
import os
from dotenv import load_dotenv

load_dotenv()

def create_app():
    app = Flask(__name__)
    
    # Environment detection
    flask_env = os.getenv("FLASK_ENV", "production")
    
    # Security configurations
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
    if not app.config["SECRET_KEY"]:
        raise ValueError("SECRET_KEY environment variable must be set")
    
    # Database configuration
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable must be set")
    
    # Neon DB uses postgres:// but SQLAlchemy needs postgresql://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["RATELIMIT_ENABLED"] = flask_env != "testing"
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
    if not database_url.startswith("sqlite"):
        app.config["SQLALCHEMY_ENGINE_OPTIONS"].update({
            "pool_recycle": 300,
            "pool_size": 2,
            "max_overflow": 0,
        })
    
    # Session configuration
    app.config["SESSION_PERMANENT"] = False
    app.config["SESSION_COOKIE_SECURE"] = flask_env == "production"
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    
    # Initialize extensions
    db.init_app(app)
    limiter.init_app(app)

    # Create tables (only in development)
    with app.app_context():
        if flask_env == "development":
            db.create_all()
            print("✓ Database tables created/verified")
        else:
            # In production, use migrations instead
            print("✓ Database connection established")
    
    # Register blueprints
    app.register_blueprint(main)
    
    return app

if __name__ == '__main__':
    app = create_app()
    debug_mode = os.getenv("FLASK_ENV") == "development"
    app.run(debug=debug_mode, host='0.0.0.0', port=int(os.getenv("PORT", 5000)))