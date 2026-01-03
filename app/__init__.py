from flask import Flask
from config import Config
from app.extensions import db, migrate, cors, socketio, jwt, bcrypt, login_manager
from app.models.user import User
from app.extensions_firebase import init_firebase

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    cors.init_app(app)
    socketio.init_app(app)
    jwt.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)

    # Init Firebase Admin
    init_firebase(app.config["FIREBASE_SERVICE_ACCOUNT"])

    login_manager.login_view = "web_auth.login"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # ==== LOAD CHATBOT ENGINE (Unsloth + LoRA) ====
    from app.services.llm_unsloth import UnslothEngine

    engine = UnslothEngine(
        base_model_name=app.config["BASE_MODEL_NAME"],
        lora_path=app.config["LORA_PATH"],
        max_seq_length=2048,
    )
    engine.load()
    app.extensions["llm_engine"] = engine

    # Register blueprints
    from app.routes.auth_routes import auth_bp
    from app.routes.article_routes import article_bp
    from app.routes.screening_routes import screening_bp
    from app.routes.consultation_routes import consultation_bp
    # (opsional) chatbot routes
    from app.routes.chatbot_routes import chatbot_bp

    from app.web.auth_routes import web_auth_bp
    from app.web.admin_routes import admin_bp
    from app.web.doctor_routes import doctor_bp
    from app.web.doctor_articles import doctor_article_bp
    from app.web.doctor_consultation import doctor_consult_bp

    from app.web.firebase_session_routes import web_session_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(article_bp)
    app.register_blueprint(screening_bp)
    app.register_blueprint(consultation_bp)
    app.register_blueprint(chatbot_bp)

    app.register_blueprint(web_auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(doctor_bp)
    app.register_blueprint(doctor_article_bp)
    app.register_blueprint(doctor_consult_bp)

    # Firebase session endpoints for web
    app.register_blueprint(web_session_bp)

    from app import socket_events

    @app.route("/")
    def index():
        return "Health App Backend is Running!"

    return app
