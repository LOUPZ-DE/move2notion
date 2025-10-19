# Quick Start: Web-GUI

Schnellanleitung zum Starten der Web-GUI in 5 Minuten.

## Schritt 1: Azure AD konfigurieren

1. Öffnen Sie [Azure Portal](https://portal.azure.com)
2. Navigieren Sie zu: **Azure Active Directory** → **App registrations** → **Ihre App**

### Client Secret erstellen:
```
1. Certificates & secrets → New client secret
2. Beschreibung: "Web GUI"
3. Gültigkeit: 24 Monate
4. Add → Secret-Wert kopieren ⚠️ (wird nur einmal angezeigt!)
```

### Redirect URI hinzufügen:
```
1. Authentication → Add a platform → Web
2. Redirect URI: http://localhost:8080/callback
3. Access tokens ✓
4. ID tokens ✓
5. Save
```

**Hinweis:** Port 8080 wird verwendet, da Port 5000 auf macOS von AirPlay Receiver belegt ist.

## Schritt 2: Dependencies installieren

```bash
pip install -r requirements.txt
```

## Schritt 3: .env konfigurieren

Fügen Sie diese Zeilen zu Ihrer `.env` hinzu:

```bash
# Client Secret aus Azure AD (Schritt 1)
MS_CLIENT_SECRET=ihr-client-secret

# Flask Secret Key (neuer Wert generieren)
FLASK_SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')

# Redirect URI (muss mit Azure AD übereinstimmen)
FLASK_REDIRECT_URI=http://localhost:8080/callback

# Port & Debug
FLASK_PORT=8080
FLASK_DEBUG=False
```

**Flask Secret Key generieren:**
```bash
python -c 'import secrets; print(secrets.token_hex(32))'
```

## Schritt 4: Server starten

```bash
# Option 1: Im web-Verzeichnis
cd web
python app.py

# Option 2: Als Python-Modul
python -m web.app
```

## Schritt 5: Web-GUI öffnen

Öffnen Sie im Browser: **http://localhost:8080**

1. Klicken Sie auf "Mit Microsoft anmelden"
2. Melden Sie sich mit Ihrem Microsoft-Konto an
3. Nach erfolgreicher Anmeldung → Dashboard

## Fertig! 🎉

Sie können jetzt OneNote und Planner zu Notion migrieren.

---

## Troubleshooting

### "MS_CLIENT_SECRET is required"
→ Haben Sie den Client Secret in `.env` gesetzt?

### "Token acquisition failed"
→ Prüfen Sie:
- Client Secret korrekt?
- Redirect URI in Azure AD registriert?
- Redirect URI exakt identisch (inkl. `http://`)?

### "Module 'flask' not found"
→ Dependencies installieren:
```bash
pip install -r requirements.txt
```

### Port bereits belegt
→ Ändern Sie den Port in `.env`:
```bash
FLASK_PORT=8080
```

---

Ausführliche Dokumentation: siehe `web/README.md`
