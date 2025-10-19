# Flask Web-GUI für MS → Notion Migration

Eine webbasierte Benutzeroberfläche zur Migration von Microsoft OneNote und Planner zu Notion.

## Features

- 🔐 **Microsoft OAuth-Authentifizierung** (Authorization Code Flow)
- 📓 **OneNote-Migration** mit grafischer Notebook-Auswahl
- 📋 **Planner-Migration** mit Status-Anzeige
- 📊 **Live-Fortschrittsanzeige** während der Migration
- 🎨 **Moderne, responsive UI** mit einfachem Design

## Voraussetzungen

### 1. Azure AD App Registration konfigurieren

**Wichtig:** Die bestehende Azure AD App muss für Web-Authentifizierung erweitert werden.

1. Gehen Sie zu [Azure Portal](https://portal.azure.com) → Azure Active Directory → App registrations
2. Wählen Sie Ihre bestehende App aus (die bereits für CLI-Zugriff konfiguriert ist)

#### Web-Platform hinzufügen:
3. Navigieren Sie zu **Authentication** → **Add a platform** → **Web**
4. Fügen Sie die Redirect URI hinzu: `http://localhost:5000/callback`
5. Aktivieren Sie **Access tokens** und **ID tokens**

#### Client Secret erstellen:
6. Navigieren Sie zu **Certificates & secrets** → **Client secrets** → **New client secret**
7. Geben Sie eine Beschreibung ein (z.B. "Web GUI Secret")
8. Wählen Sie eine Gültigkeitsdauer (empfohlen: 24 Monate)
9. Klicken Sie auf **Add** und **kopieren Sie den Secret-Wert sofort** (wird nur einmal angezeigt!)

#### API-Berechtigungen prüfen:
10. Navigieren Sie zu **API permissions**
11. Stellen Sie sicher, dass folgende Microsoft Graph Permissions vorhanden sind:
    - `Notes.Read.All` (Delegated)
    - `Sites.Read.All` (Delegated)

## Installation

### 1. Dependencies installieren

```bash
# Im Projektverzeichnis
pip install -r requirements.txt
```

### 2. Umgebungsvariablen konfigurieren

Kopieren Sie `.env.example` zu `.env` und füllen Sie die Web-spezifischen Variablen aus:

```bash
# Microsoft Graph API Konfiguration
MS_CLIENT_ID=ihre-client-id
MS_TENANT_ID=common  # oder Ihre Tenant-ID
MS_GRAPH_SCOPES=Notes.Read.All,Sites.Read.All

# WEB-SPEZIFISCH: Client Secret aus Azure AD
MS_CLIENT_SECRET=ihr-client-secret-aus-azure

# Notion API Konfiguration
NOTION_TOKEN=secret_ihre_notion_integration_token

# WEB-SPEZIFISCH: Flask-Konfiguration
FLASK_SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')
FLASK_REDIRECT_URI=http://localhost:5000/callback
FLASK_PORT=5000
FLASK_DEBUG=False  # True nur für Entwicklung
```

**Flask Secret Key generieren:**
```bash
python -c 'import secrets; print(secrets.token_hex(32))'
```

## Verwendung

### Web-Server starten

```bash
# Im Projektverzeichnis
cd web
python app.py
```

Oder:

```bash
# Im Projektverzeichnis
python -m web.app
```

Der Server läuft standardmäßig auf: `http://localhost:5000`

### Workflow

1. **Login:**
   - Öffnen Sie `http://localhost:5000`
   - Sie werden zu Microsoft weitergeleitet
   - Melden Sie sich mit Ihrem Microsoft-Konto an
   - Nach erfolgreicher Authentifizierung werden Sie zurück zum Dashboard weitergeleitet

2. **OneNote-Migration:**
   - Klicken Sie auf "OneNote Migration"
   - Geben Sie die SharePoint Site URL ein
   - Wählen Sie die zu migrierenden Notebooks aus
   - Geben Sie die Notion-Ziel-Seiten-ID ein
   - Starten Sie die Migration

3. **Planner-Migration:**
   - Klicken Sie auf "Planner Migration"
   - Geben Sie die Planner Plan ID ein
   - Geben Sie die Notion-Datenbank-ID ein
   - (Optional) Laden Sie eine CSV-Datei für Personen-Mapping hoch
   - Starten Sie die Migration

## Architektur

```
web/
├── app.py                  # Flask-Hauptanwendung
├── templates/              # HTML-Templates (Jinja2)
│   ├── base.html
│   ├── login.html
│   ├── dashboard.html
│   ├── error.html
│   ├── onenote_dashboard.html
│   └── planner_dashboard.html
└── static/                 # Statische Dateien
    ├── style.css          # CSS-Styling
    └── main.js            # JavaScript-Utilities
```

### Authentifizierungs-Flow

1. Benutzer ruft `/login` auf
2. Flask generiert Microsoft OAuth URL mit `state` Parameter
3. Benutzer wird zu Microsoft weitergeleitet
4. Nach erfolgreicher Anmeldung: Redirect zu `/callback?code=...`
5. Flask tauscht `code` gegen Access Token
6. Token wird in Flask-Session gespeichert
7. Token-Refresh erfolgt automatisch durch MSAL

### API-Endpoints

- `GET /` - Dashboard (erfordert Authentifizierung)
- `GET /login` - Microsoft Login initiieren
- `GET /callback` - OAuth-Callback
- `GET /logout` - Logout
- `GET /onenote` - OneNote-Migration Dashboard
- `GET /api/onenote/notebooks?site_url=...` - Notebooks abrufen
- `POST /api/onenote/migrate` - Migration starten
- `GET /planner` - Planner-Migration Dashboard
- `POST /api/planner/migrate` - Migration starten

## Sicherheitshinweise

⚠️ **Wichtig für Produktionsumgebungen:**

1. **HTTPS verwenden:**
   ```bash
   # Redirect URI in Azure AD und .env anpassen
   FLASK_REDIRECT_URI=https://ihre-domain.com/callback
   ```

2. **Starkes Secret Key verwenden:**
   ```bash
   # Niemals den gleichen Key in Entwicklung und Produktion
   FLASK_SECRET_KEY=$(openssl rand -hex 32)
   ```

3. **Debug-Modus deaktivieren:**
   ```bash
   FLASK_DEBUG=False
   ```

4. **Reverse Proxy verwenden:**
   - Nginx oder Apache vor Flask
   - Rate Limiting implementieren
   - SSL/TLS-Terminierung

5. **Environment-Variablen schützen:**
   - `.env` niemals in Git committen
   - Produktions-Secrets in sicherer Umgebung speichern (z.B. Azure Key Vault)

## Troubleshooting

### Fehler: "MS_CLIENT_SECRET is required"
**Lösung:** Stellen Sie sicher, dass `MS_CLIENT_SECRET` in `.env` gesetzt ist und Sie einen Client Secret in Azure AD erstellt haben.

### Fehler: "REDIRECT_URI is required"
**Lösung:** Setzen Sie `FLASK_REDIRECT_URI` in `.env` und stellen Sie sicher, dass diese URI in Azure AD registriert ist.

### Fehler: "Token acquisition failed"
**Lösung:** 
- Prüfen Sie, ob der Client Secret korrekt ist
- Prüfen Sie, ob die Redirect URI exakt übereinstimmt (inkl. Protokoll und Port)
- Prüfen Sie die Azure AD Logs für detaillierte Fehler

### Sessions funktionieren nicht
**Lösung:**
- Stellen Sie sicher, dass `FLASK_SECRET_KEY` gesetzt ist
- Prüfen Sie, ob Cookies im Browser aktiviert sind
- Für Produktion: Session-Backend verwenden (z.B. Redis)

### Import-Fehler: "flask" konnte nicht aufgelöst werden
**Lösung:**
```bash
pip install -r requirements.txt
```

## Entwicklung

### Development-Server starten

```bash
# Mit Debug-Modus
export FLASK_DEBUG=True
python web/app.py
```

### Code-Struktur erweitern

Die Web-GUI nutzt die bestehenden Core-Module:
- `core/auth.py` - Authentifizierung (CLI + Web)
- `core/ms_graph_client.py` - Microsoft Graph API
- `core/notion_client.py` - Notion API
- `tools/onenote_migration/` - OneNote-Migrations-Logik
- `tools/planner_migration/` - Planner-Migrations-Logik

Neue Features können durch Erweiterung der Endpoints in `app.py` hinzugefügt werden.

## Bekannte Einschränkungen

- **Single-User:** Die aktuelle Implementierung ist für Single-User-Nutzung konzipiert
- **In-Memory-Sessions:** Sessions werden im Speicher gehalten (nicht persistent)
- **Keine Background-Jobs:** Lange Migrationen blockieren derzeit den Request
  - **Empfehlung für Produktion:** Celery oder RQ für Background-Tasks verwenden

## Roadmap

Mögliche zukünftige Erweiterungen:
- [ ] Multi-User-Support mit User-Management
- [ ] Persistente Session-Storage (Redis)
- [ ] Background-Workers für lange Migrationen (Celery/RQ)
- [ ] WebSocket-Support für Echtzeit-Updates
- [ ] Migration-Historie und Logging-Dashboard
- [ ] Automatische Token-Refresh-Benachrichtigungen
- [ ] Export von Migrations-Berichten (PDF/CSV)

## Support

Bei Problemen oder Fragen:
1. Prüfen Sie die [Troubleshooting](#troubleshooting)-Sektion
2. Prüfen Sie die Azure AD Logs
3. Aktivieren Sie Debug-Logging mit `FLASK_DEBUG=True`
4. Öffnen Sie ein GitHub Issue mit detaillierten Fehlerinformationen

## Lizenz

Siehe Hauptprojekt-README.
