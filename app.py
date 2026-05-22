import os
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from waitress import serve

# Import Route Blueprints
from routes.health_routes import health_bp
from routes.task_routes import task_bp

# Load environment configuration
load_dotenv()

def create_app() -> Flask:
    app = Flask(__name__)
    
    # Configure CORS mapping
    cors_allowed_origins = "*"
    env = os.getenv("FLASK_ENV", "development")
    if env == "production":
        allowed_env = os.getenv("CORS_ALLOWED_ORIGINS")
        if allowed_env:
            cors_allowed_origins = [orig.strip() for orig in allowed_env.split(",") if orig.strip()]
    
    CORS(app, resources={r"/*": {"origins": cors_allowed_origins}})

    # Register blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(task_bp)

    # Standard JSON API Error Handlers
    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({
            "success": False,
            "error": "Bad Request",
            "message": str(error)
        }), 400

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            "success": False,
            "error": "Not Found",
            "message": "The requested API endpoint was not found."
        }), 404

    @app.errorhandler(500)
    def server_error(error):
        return jsonify({
            "success": False,
            "error": "Internal Server Error",
            "message": "An unexpected error occurred inside the AI backend."
        }), 500

    return app

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    env = os.getenv("FLASK_ENV", "development")
    
    print("=" * 60)
    print(f" TaskTriumph AI Task Backend Starting...")
    print(f" Serving Environment: {env}")
    print(f" Allowed CORS Origins: {os.getenv('CORS_ALLOWED_ORIGINS')}")
    print(f" Running on: http://localhost:{port}")
    print("=" * 60)
    
    if env == "production":
        # Production serve using Waitress WSGI
        serve(app, host="0.0.0.0", port=port)
    else:
        # Development serve with auto-reload
        app.run(host="0.0.0.0", port=port, debug=True)

