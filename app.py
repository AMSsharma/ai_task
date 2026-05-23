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
    def normalize_origin(origin: str) -> str:
        origin = origin.strip()
        return origin[:-1] if origin.endswith("/") else origin

    cors_allowed_origins = [
        normalize_origin("https://task-triumph-forge.vercel.app"),
        normalize_origin("http://localhost:8080"),
        normalize_origin("http://localhost:5173"),
        normalize_origin("http://localhost:3000"),
        normalize_origin("http://127.0.0.1:8080"),
        normalize_origin("http://127.0.0.1:5173"),
        normalize_origin("http://127.0.0.1:3000"),
    ]
    
    allowed_env = os.getenv("CORS_ALLOWED_ORIGINS")
    if allowed_env:
        if allowed_env.strip() == "*":
            cors_allowed_origins = "*"
        else:
            extra_origins = [normalize_origin(orig) for orig in allowed_env.split(",") if orig.strip()]
            cors_allowed_origins.extend(extra_origins)
                    
    # Remove duplicates from the list if it's a list
    if isinstance(cors_allowed_origins, list):
        cors_allowed_origins = list(set(cors_allowed_origins))
    
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

