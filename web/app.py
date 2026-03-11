"""
Flask Web-GUI für Microsoft-Notion Migration Tools.
"""
import os
import secrets
import json
import threading
import queue
from flask import Flask, render_template, session, redirect, url_for, request, jsonify, Response
from dotenv import load_dotenv

# Lade .env-Datei
load_dotenv()

# Importiere Core-Module
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.auth import AuthManager, AuthConfig
from web.task_manager import task_manager, TaskStatus, emit_progress, emit_complete

def print_banner(port: int):
    """Startup-Banner mit ASCII-Art ausgeben."""
    VERSION = "0.9.3"
    C = "\033[36m"    # Cyan
    B = "\033[1;34m"  # Bold Blue
    W = "\033[1;37m"  # Bold White
    G = "\033[32m"    # Green
    D = "\033[2m"     # Dim
    R = "\033[0m"     # Reset

    banner = f"""
{C}  ___  ___                 ___  {B}  _   _       _   _             {R}
{C} |  \\/  |                |__ \\ {B} | \\ | |     | | (_)            {R}
{C} | .  . | _____   _____    ) |{B} |  \\| | ___ | |_ _  ___  _ __  {R}
{C} | |\\/| |/ _ \\ \\ / / _ \\  / / {B} | . ` |/ _ \\| __| |/ _ \\| '_ \\ {R}
{C} | |  | | (_) \\ V /  __/ / /_ {B} | |\\  | (_) | |_| | (_) | | | |{R}
{C} \\_|  |_/\\___/ \\_/ \\___||____|{B} \\_| \\_/\\___/ \\__|_|\\___/|_| |_|{R}

{W}  Microsoft-zu-Notion Migration Suite{R}
{D}  v{VERSION} — LOUPZ GmbH & Co. KG{R}

{G}  ✓ Server läuft auf http://localhost:{port}{R}
{D}  Strg+C zum Beenden{R}
"""
    print(banner)


# Banner beim Start ausgeben (funktioniert mit python app.py und gunicorn)
print_banner(int(os.getenv("FLASK_PORT", 8080)))

# Flask-App initialisieren
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))

# Globaler Auth-Manager für Web
web_auth_manager = AuthManager()


def is_application_mode() -> bool:
    """Prüfen ob Application-Modus aktiv ist."""
    return os.getenv("MS_AUTH_MODE", "delegated").lower().strip() == "application"


def _friendly_graph_error(error_msg: str) -> str:
    """Graph-API-Fehler in benutzerfreundliche Meldung umwandeln."""
    if "403" in error_msg:
        return "Kein Zugriff (kein Mitglied dieser Gruppe)"
    if "404" in error_msg:
        return "Nicht gefunden"
    return error_msg


def verify_admin_password(password: str) -> bool:
    """Admin-Passwort prüfen."""
    admin_pw = os.getenv("ADMIN_PASSWORD", "")
    if not admin_pw:
        return False
    return password == admin_pw


def init_auth():
    """Authentifizierung initialisieren."""
    if not web_auth_manager.mode:
        web_auth_manager.initialize(mode="web")
        # Bei Application-Modus: ADMIN_PASSWORD muss gesetzt sein
        if is_application_mode() and not os.getenv("ADMIN_PASSWORD"):
            raise RuntimeError(
                "ADMIN_PASSWORD must be set in .env when MS_AUTH_MODE=application. "
                "This password protects the Web-GUI since Microsoft login is skipped."
            )


@app.before_request
def before_request():
    """Vor jedem Request: Auth initialisieren."""
    init_auth()


@app.context_processor
def inject_auth_mode():
    """Auth-Modus für Templates verfügbar machen."""
    return {"auth_mode": os.getenv("MS_AUTH_MODE", "delegated").lower().strip()}


# ===== Authentifizierungs-Routes =====

@app.route("/")
def index():
    """Hauptseite / Dashboard."""
    if "authenticated" not in session:
        return redirect(url_for("login"))
    return render_template("dashboard.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Login-Seite."""
    if "authenticated" in session:
        return redirect(url_for("index"))

    if is_application_mode():
        # Application-Modus: Passwort-Formular statt MS OAuth
        if request.method == "POST":
            password = request.form.get("password", "")
            if verify_admin_password(password):
                session["authenticated"] = True
                return redirect(url_for("index"))
            else:
                return render_template("login_password.html", error="Falsches Passwort")
        return render_template("login_password.html")

    # Delegated-Modus: MS OAuth Flow (bestehend)
    if "session_id" not in session:
        session["session_id"] = secrets.token_urlsafe(32)

    auth_url = web_auth_manager.microsoft.get_auth_url(session["session_id"])
    return render_template("login.html", auth_url=auth_url)


@app.route("/callback")
def callback():
    """OAuth-Callback von Microsoft."""
    if is_application_mode():
        return redirect(url_for("login"))

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
    if not is_application_mode():
        session_id = session.get("session_id")
        if session_id and hasattr(web_auth_manager.microsoft, 'clear_session'):
            web_auth_manager.microsoft.clear_session(session_id)
    session.clear()
    return redirect(url_for("login"))


# ===== Task-SSE Routes =====

@app.route("/api/tasks/<task_id>/events")
def task_events(task_id):
    """SSE-Endpoint: Streamt Progress-Events einer Migration."""
    if "authenticated" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    task = task_manager.get_task(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    def generate():
        while True:
            try:
                event = task.event_queue.get(timeout=30)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") == "complete":
                    break
            except queue.Empty:
                yield ": keepalive\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )


@app.route("/api/tasks/<task_id>/status")
def task_status(task_id):
    """Status-Fallback fuer Reconnect nach Browser-Navigation."""
    if "authenticated" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    task = task_manager.get_task(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    return jsonify({
        "task_id": task.task_id,
        "task_type": task.task_type,
        "status": task.status.value,
        "progress": task.progress,
        "phase": task.phase,
        "message": task.message,
        "success_count": task.success_count,
        "error_count": task.error_count,
        "total_items": task.total_items,
    })


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
        client = MSGraphClient(web_auth_manager, session_id=session.get("session_id"))

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
    """OneNote-Migration als Background-Task starten."""
    if "authenticated" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    data = request.json
    site_id = data.get("site_id")
    notebook_ids = data.get("notebook_ids", [])
    database_id = data.get("database_id")

    if not site_id:
        return jsonify({"error": "site_id required"}), 400
    if not notebook_ids:
        return jsonify({"error": "notebook_ids required"}), 400
    if not database_id:
        return jsonify({"error": "database_id required"}), 400

    # Session-ID vor Thread-Start erfassen (Flask Session ist request-local)
    session_id = session.get("session_id")

    task = task_manager.create_task("onenote")
    thread = threading.Thread(
        target=_run_onenote_migration,
        args=(task, site_id, notebook_ids, database_id, session_id),
        daemon=True
    )
    task.thread = thread
    task.status = TaskStatus.RUNNING
    thread.start()

    return jsonify({"task_id": task.task_id, "status": "started"})


def _run_onenote_migration(task, site_id, notebook_ids, database_id, session_id):
    """OneNote-Migration im Background-Thread."""
    try:
        from core.ms_graph_client import MSGraphClient
        from core.notion_client import NotionClient
        from tools.onenote_migration.content_mapper import ContentMapper

        ms_client = MSGraphClient(web_auth_manager, session_id=session_id)
        notion_client = NotionClient()
        content_mapper = ContentMapper(notion_client, ms_client, site_id)

        # Phase 1: Notebooks laden
        emit_progress(task, 2, "Lade Notebook-Informationen...", phase="Notebooks laden")
        all_notebooks = ms_client.list_site_notebooks(site_id)
        selected = [nb for nb in all_notebooks if nb.get("id") in notebook_ids]

        if not selected:
            emit_progress(task, 0, "Keine passenden Notebooks gefunden", log_type="error")
            emit_complete(task, success=False)
            return

        emit_progress(task, 5, f"{len(selected)} Notebook(s) ausgewaehlt", log_type="success")

        # Phase 2: Sections und Pages zaehlen
        emit_progress(task, 6, "Lade Sections...", phase="Sections laden")
        all_sections = []  # (notebook, section, pages)

        for nb_idx, notebook in enumerate(selected):
            nb_name = notebook.get("displayName", "Unbekannt")
            try:
                sections = ms_client.get_notebook_sections(site_id, notebook["id"])
            except Exception as e:
                emit_progress(task, 0, f"Sections fuer '{nb_name}' fehlgeschlagen: {e}", log_type="error")
                sections = []

            for section in sections:
                sec_name = section.get("displayName", "Unbekannt")
                try:
                    pages = ms_client.list_pages_for_section(site_id, section["id"])
                except Exception as e:
                    emit_progress(task, 0, f"Seiten fuer '{sec_name}' fehlgeschlagen: {e}", log_type="error")
                    pages = []
                all_sections.append((notebook, section, pages))

            progress = 6 + int((nb_idx + 1) / len(selected) * 9)
            emit_progress(task, progress,
                f"Notebook '{nb_name}': {len(sections)} Section(s)")

        total_pages = sum(len(pages) for _, _, pages in all_sections)
        task.total_items = total_pages
        emit_progress(task, 15,
            f"{total_pages} Seiten in {len(all_sections)} Section(s) gefunden",
            log_type="success", phase="Seiten importieren")

        if total_pages == 0:
            emit_progress(task, 100, "Keine Seiten zum Importieren", log_type="warning")
            emit_complete(task, success=True)
            return

        # Phase 3: Seiten importieren
        processed = 0
        for notebook, section, pages in all_sections:
            nb_name = notebook.get("displayName", "")
            sec_name = section.get("displayName", "")
            sec_group = section.get("_groupName", "")

            if pages:
                label = f"{sec_group}/{sec_name}" if sec_group else sec_name
                emit_progress(task, task.progress, f"Section: {label} ({len(pages)} Seiten)")

            for page in pages:
                page_title = page.get("title") or "Untitled"
                try:
                    notion_page_id = content_mapper.map_page_to_notion(
                        onenote_page=page,
                        database_id=database_id,
                        section_name=sec_name,
                        notebook_name=nb_name,
                        section_group=sec_group
                    )
                    processed += 1
                    progress = 15 + int(processed / total_pages * 80)

                    if notion_page_id:
                        task.success_count += 1
                        emit_progress(task, progress,
                            f"[{processed}/{total_pages}] Importiert: {page_title}",
                            log_type="success")
                    else:
                        task.error_count += 1
                        task.errors.append({"task": page_title, "error": "Import fehlgeschlagen"})
                        emit_progress(task, progress,
                            f"[{processed}/{total_pages}] Fehler: {page_title}",
                            log_type="error")

                except Exception as e:
                    processed += 1
                    task.error_count += 1
                    task.errors.append({"task": page_title, "error": str(e)})
                    progress = 15 + int(processed / total_pages * 80)
                    emit_progress(task, progress,
                        f"[{processed}/{total_pages}] Fehler bei '{page_title}': {e}",
                        log_type="error")

        # Abschluss
        summary = f"Migration abgeschlossen: {task.success_count} importiert, {task.error_count} Fehler"
        emit_progress(task, 98, summary, log_type="success", phase="Abgeschlossen")
        emit_complete(task, success=task.error_count == 0 or task.success_count > 0)

    except Exception as e:
        emit_progress(task, task.progress, f"Fataler Fehler: {e}", log_type="error")
        emit_complete(task, success=False)


# ===== Planner-Migration Routes =====

@app.route("/planner")
def planner_dashboard():
    """Planner-Migration Dashboard."""
    if "authenticated" not in session:
        return redirect(url_for("login"))
    return render_template("planner_dashboard.html")


@app.route("/api/planner/migrate", methods=["POST"])
def start_planner_migration():
    """Planner-Migration als Background-Task starten."""
    if "authenticated" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    data = request.json
    plan_id = data.get("plan_id")
    database_id = data.get("database_id")

    if not plan_id:
        return jsonify({"error": "plan_id required"}), 400
    if not database_id:
        return jsonify({"error": "database_id required"}), 400

    # Session-ID vor Thread-Start erfassen (Flask Session ist request-local)
    session_id = session.get("session_id")

    task = task_manager.create_task("planner")
    thread = threading.Thread(
        target=_run_planner_migration,
        args=(task, plan_id, database_id, session_id),
        daemon=True
    )
    task.thread = thread
    task.status = TaskStatus.RUNNING
    thread.start()

    return jsonify({"task_id": task.task_id, "status": "started"})


def _run_planner_migration(task, plan_id, database_id, session_id):
    """Planner-Migration im Background-Thread."""
    try:
        from core.ms_graph_client import MSGraphClient
        from core.notion_client import NotionClient
        from tools.planner_migration.planner_api_mapper import create_planner_api_mapper
        from tools.planner_migration.notion_mapper import create_notion_mapper

        ms_client = MSGraphClient(web_auth_manager, session_id=session_id)

        # 1. Plan-Details abrufen
        emit_progress(task, 2, "Lade Plan-Details...", phase="Plan-Details laden")
        plan = ms_client.get_planner_plan(plan_id)
        plan_title = plan.get("title", "Unbekannter Plan")
        group_id = plan.get("owner")
        emit_progress(task, 5, f"Plan: {plan_title}", log_type="success")

        # 1b. Category-Descriptions
        try:
            plan_details = ms_client.get_planner_plan_details(plan_id)
            category_descriptions = plan_details.get("categoryDescriptions", {})
        except Exception:
            category_descriptions = {}

        # 2. Buckets abrufen
        emit_progress(task, 7, "Lade Buckets...", phase="Buckets laden")
        buckets = ms_client.list_planner_buckets(plan_id)
        emit_progress(task, 10, f"{len(buckets)} Buckets gefunden", log_type="success")

        # 3. Tasks abrufen
        emit_progress(task, 12, "Lade Tasks...", phase="Tasks laden")
        tasks = ms_client.list_planner_tasks(plan_id)
        emit_progress(task, 15, f"{len(tasks)} Tasks gefunden", log_type="success")

        # 4. Task-Details abrufen
        emit_progress(task, 16, "Lade Task-Details...", phase="Task-Details laden")
        tasks_details = {}
        for i, t in enumerate(tasks):
            t_id = t.get("id")
            t_name = t.get("title", "Unbekannt")
            if t_id:
                try:
                    details = ms_client.get_task_details(t_id)
                    tasks_details[t_id] = details
                except Exception:
                    pass
            progress = 16 + int((i + 1) / max(len(tasks), 1) * 24)
            emit_progress(task, progress, f"[{i+1}/{len(tasks)}] Details fuer '{t_name}'")

        emit_progress(task, 40, f"Details fuer {len(tasks_details)} Tasks geladen", log_type="success")

        # 5. Gruppenmitglieder abrufen
        emit_progress(task, 42, "Lade Gruppenmitglieder...", phase="Gruppenmitglieder")
        group_members = []
        if group_id:
            try:
                group_members = ms_client.get_group_members(group_id)
            except Exception:
                pass
        emit_progress(task, 45, f"{len(group_members)} Mitglieder gefunden", log_type="success")

        # 6. Daten konvertieren
        emit_progress(task, 47, "Konvertiere Daten...", phase="Daten konvertieren")
        api_mapper = create_planner_api_mapper()
        api_mapper.set_buckets(buckets)
        api_mapper.set_users(group_members)
        api_mapper.set_category_descriptions(category_descriptions)
        rows = api_mapper.map_tasks_to_rows(tasks, tasks_details)

        if not rows:
            emit_progress(task, 0, "Keine Tasks im Plan gefunden", log_type="error")
            emit_complete(task, success=False)
            return

        task.total_items = len(rows)
        emit_progress(task, 55, f"{len(rows)} Tasks konvertiert", log_type="success")

        # 7. Notion-Client und Mapper erstellen
        emit_progress(task, 57, "Bereite Datenbank vor...", phase="DB vorbereiten")
        notion_client = NotionClient()
        notion_mapper = create_notion_mapper(notion_client)

        # 8. Datenbank vorbereiten
        notion_mapper.prepare_database_for_import(database_id, rows)
        emit_progress(task, 60, "Datenbank vorbereitet", log_type="success")

        # 9. Daten importieren
        emit_progress(task, 60, f"Importiere {len(rows)} Eintraege...", phase="Import")

        for i, row in enumerate(rows):
            row_name = row.get("Name", "Unbekannt")
            try:
                properties = notion_mapper.build_properties_for_row(row, None)
                children = notion_mapper.build_children_blocks(row)
                notion_client.create_page(database_id, properties, children)
                task.success_count += 1
                progress = 60 + int((i + 1) / len(rows) * 38)
                emit_progress(task, progress,
                    f"[{i+1}/{len(rows)}] Erstellt: {row_name}",
                    log_type="success")
            except Exception as e:
                task.error_count += 1
                task.errors.append({"task": row_name, "error": str(e)})
                progress = 60 + int((i + 1) / len(rows) * 38)
                emit_progress(task, progress,
                    f"[{i+1}/{len(rows)}] Fehler bei '{row_name}': {e}",
                    log_type="error")

        # 10. Abschluss
        summary = f"Migration abgeschlossen: {task.success_count} erstellt, {task.error_count} Fehler"
        emit_progress(task, 98, summary, log_type="success", phase="Abgeschlossen")
        emit_complete(task, success=task.error_count == 0 or task.success_count > 0)

    except Exception as e:
        emit_progress(task, task.progress, f"Fataler Fehler: {e}", log_type="error")
        emit_complete(task, success=False)


# ===== Overview Routes =====

@app.route("/overview")
def overview_dashboard():
    """Overview Dashboard: Microsoft 365-Gruppen anzeigen."""
    if "authenticated" not in session:
        return redirect(url_for("login"))
    return render_template("overview_dashboard.html")


@app.route("/api/overview/groups", methods=["GET"])
def get_overview_groups():
    """Liste aller Microsoft 365-Gruppen abrufen."""
    if "authenticated" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    try:
        from core.ms_graph_client import MSGraphClient
        client = MSGraphClient(web_auth_manager, session_id=session.get("session_id"))
        groups = client.list_groups()

        return jsonify({
            "auth_mode": "application" if is_application_mode() else "delegated",
            "groups": [
                {
                    "id": g.get("id", ""),
                    "displayName": g.get("displayName", ""),
                    "description": g.get("description", ""),
                    "mail": g.get("mail", ""),
                }
                for g in groups
            ]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/overview/groups/<group_id>/details", methods=["GET"])
def get_group_details(group_id):
    """Notebooks und Planner-Pläne einer Gruppe abrufen."""
    if "authenticated" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    try:
        from core.ms_graph_client import MSGraphClient
        client = MSGraphClient(web_auth_manager, session_id=session.get("session_id"))

        notebooks = []
        notebooks_error = None
        if is_application_mode():
            notebooks_error = "Nicht verfuegbar im Application-Modus (Delegated Auth erforderlich)"
        else:
            try:
                raw_notebooks = client.list_group_notebooks(group_id)
                notebooks = [
                    {"id": nb.get("id", ""), "displayName": nb.get("displayName", "")}
                    for nb in raw_notebooks
                ]
            except Exception as e:
                notebooks_error = _friendly_graph_error(str(e))

        # SharePoint-Site-URL der Gruppe abrufen
        site_url = None
        try:
            site_url = client.get_group_site_url(group_id)
        except Exception:
            pass

        plans = []
        plans_error = None
        try:
            raw_plans = client.list_group_planner_plans(group_id)
            plans = [
                {"id": p.get("id", ""), "title": p.get("title", "")}
                for p in raw_plans
            ]
        except Exception as e:
            plans_error = _friendly_graph_error(str(e))

        return jsonify({
            "group_id": group_id,
            "site_url": site_url,
            "notebooks": notebooks,
            "notebooks_error": notebooks_error,
            "plans": plans,
            "plans_error": plans_error,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
