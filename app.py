import os
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from waitress import serve
from werkzeug.middleware.proxy_fix import ProxyFix

# Import Route Blueprints
from routes.health_routes import health_bp
from routes.task_routes import task_bp

# Load environment configuration
load_dotenv()


def create_app() -> Flask:
    app = Flask(__name__)

    # Fix proxy headers for Render / Vercel / Reverse Proxies
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    # -------------------------------
    # Normalize Origins
    # -------------------------------
    def normalize_origin(origin: str) -> str:
        origin = origin.strip()
        return origin[:-1] if origin.endswith("/") else origin

    # -------------------------------
    # Configure Allowed Origins
    # -------------------------------
    allowed_env = os.getenv("CORS_ALLOWED_ORIGINS")

    if allowed_env:
        if allowed_env.strip() == "*":
            cors_allowed_origins = "*"
        else:
            cors_allowed_origins = list({
                normalize_origin(origin)
                for origin in allowed_env.split(",")
                if origin.strip()
            })
    else:
        cors_allowed_origins = [
            "https://task-triumph-forge.vercel.app",
            "http://localhost:8080",
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:8080",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
        ]

    # -------------------------------
    # CORS Configuration
    # -------------------------------
    CORS(
        app,
        resources={
            r"/*": {
                "origins": cors_allowed_origins,
                "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                "allow_headers": "*",
                "expose_headers": "*",
                "supports_credentials": True,
            }
        }
    )

    # -------------------------------
    # Register Blueprints
    # -------------------------------
    app.register_blueprint(health_bp)
    app.register_blueprint(task_bp)

    # -------------------------------
    # Health Route
    # -------------------------------
    @app.route("/")
    def root():
        return jsonify({
            "success": True,
            "message": "TaskTriumph Backend Running"
        })

    # -------------------------------
    # Error Handlers
    # -------------------------------
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


# Create Flask App
app = create_app()

# -------------------------------
# Run Server
# -------------------------------
if __name__ == "__main__":

    port = int(os.getenv("PORT", 5000))
    env = os.getenv("FLASK_ENV", "development")

    print("=" * 60)
    print(" TaskTriumph AI Backend Starting...")
    print(f" Environment: {env}")
    print(f" Port: {port}")
    print(f" CORS Origins: {os.getenv('CORS_ALLOWED_ORIGINS', 'DEFAULT')}")
    print("=" * 60)

    if env == "production":
        serve(app, host="0.0.0.0", port=port)
    else:
        app.run(
            host="0.0.0.0",
            port=port,
            debug=True
        )
