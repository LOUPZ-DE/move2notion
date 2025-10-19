"""
Flask Web-GUI für Microsoft-Notion Migration Tools.
"""
import os
import secrets
from flask import Flask, render_template, session, redirect, url_for, request, jsonify
from dotenv import load_dotenv

# Lade .env-Datei
load_dotenv()

# Importiere Core-Module
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.auth import AuthManager, AuthConfig

# Flask-App initialisieren
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))

# Globaler Auth-Manager für Web
web_auth_manager = AuthManager()


def init_auth():
    """Authentifizierung initialisieren."""
    if not web_auth_manager.mode:
        web_auth_manager.initialize(mode="web")


@app.before_request
def before_request():
    """Vor jedem Request: Auth initialisieren."""
    init_auth()


# ===== Authentifizierungs-Routes =====

@app.route("/")
def index():
    """Hauptseite / Dashboard."""
    if "authenticated" not in session:
        return redirect(url_for("login"))
    return render_template("dashboard.html")


@app.route("/login")
def login():
    """Login-Seite."""
    if "authenticated" in session:
        return redirect(url_for("index"))
    
    # Session-ID generieren falls nicht vorhanden
    if "session_id" not in session:
        session["session_id"] = secrets.token_urlsafe(32)
    
    # Generiere Auth-URL
    auth_url = web_auth_manager.microsoft.get_auth_url(session["session_id"])
    
    return render_template("login.html", auth_url=auth_url)


@app.route("/callback")
def callback():
    """OAuth-Callback von Microsoft."""
    code = request.args.get("code")
    error = request.args.get("error")
    
    if error:
        return render_template("error.html", error=f"Authentication failed: {error}")
    
    if not code:
        return redirect(url_for("login"))
    
    # Session-ID abrufen
    session_id = session.get("session_id")
    if not session_id:
        return redirect(url_for("login"))
    
    try:
        # Token erwerben
        web_auth_manager.microsoft.acquire_token_by_auth_code(code, session_id)
        session["authenticated"] = True
        return redirect(url_for("index"))
    except Exception as e:
        return render_template("error.html", error=f"Token acquisition failed: {str(e)}")


@app.route("/logout")
def logout():
    """Logout."""
    session_id = session.get("session_id")
    if session_id:
        web_auth_manager.microsoft.clear_session(session_id)
    session.clear()
    return redirect(url_for("login"))


# ===== OneNote-Migration Routes =====

@app.route("/onenote")
def onenote_dashboard():
    """OneNote-Migration Dashboard."""
    if "authenticated" not in session:
        return redirect(url_for("login"))
    return render_template("onenote_dashboard.html")


@app.route("/api/onenote/notebooks", methods=["GET"])
def get_notebooks():
    """Liste aller OneNote-Notebooks abrufen."""
    if "authenticated" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    try:
        from core.ms_graph_client import MSGraphClient
        
        # Site-URL aus Request-Parameter
        site_url = request.args.get("site_url")
        if not site_url:
            return jsonify({"error": "site_url parameter required"}), 400
        
        # MS Graph Client erstellen
        client = MSGraphClient(web_auth_manager)
        
        # Site-ID auflösen
        site_id = client.resolve_site_id_from_url(site_url)
        
        # Notebooks abrufen
        notebooks = client.list_site_notebooks(site_id)
        
        return jsonify({
            "site_id": site_id,
            "notebooks": notebooks
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/onenote/migrate", methods=["POST"])
def start_onenote_migration():
    """OneNote-Migration starten."""
    if "authenticated" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    # TODO: Implementierung der Migration in Background-Thread
    data = request.json
    return jsonify({
        "status": "started",
        "message": "Migration wird gestartet...",
        "data": data
    })


# ===== Planner-Migration Routes =====

@app.route("/planner")
def planner_dashboard():
    """Planner-Migration Dashboard."""
    if "authenticated" not in session:
        return redirect(url_for("login"))
    return render_template("planner_dashboard.html")


@app.route("/api/planner/migrate", methods=["POST"])
def start_planner_migration():
    """Planner-Migration starten."""
    if "authenticated" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    # TODO: Implementierung der Migration in Background-Thread
    data = request.json
    return jsonify({
        "status": "started",
        "message": "Migration wird gestartet...",
        "data": data
    })


# ===== Fehlerbehandlung =====

@app.errorhandler(404)
def not_found(error):
    """404-Fehlerseite."""
    return render_template("error.html", error="Seite nicht gefunden"), 404


@app.errorhandler(500)
def internal_error(error):
    """500-Fehlerseite."""
    return render_template("error.html", error="Interner Serverfehler"), 500


if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", 8080))
    debug = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
