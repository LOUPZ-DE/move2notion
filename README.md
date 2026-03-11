# 🧠 Microsoft-zu-Notion Migration Suite

**Automatisierte Migration von Microsoft-Daten nach Notion**

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC_BY--NC_4.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)
[![Changelog](https://img.shields.io/badge/Changelog-v0.9.5-orange.svg)](CHANGELOG.md)

---

## 🚀 Was ist das?

Diese Suite migriert **Daten aus Microsoft 365** (Planner, OneNote) in **strukturierte Notion-Datenbanken**.

- ✅ **Automatisiert**: Keine manuellen Copy-Paste-Arbeiten
- ✅ **Modular**: Einfach neue Quellen hinzufügen
- ✅ **Idempotent**: Sichere Resume-Funktionalität
- ✅ **Rich-Content**: Bilder, Tabellen, To-Dos werden korrekt importiert

---

## 📦 Installation

```bash
# Repository klonen
git clone <repository-url>
cd ms_notion_migration

# Umgebung
python3 -m venv .venv
source .venv/bin/activate

# Dependencies
pip install -r requirements.txt

# Konfiguration
cp .env.example .env
# .env mit Ihren Zugangsdaten füllen
```

### `.env` Datei

```bash
# Microsoft
MS_CLIENT_ID=your-client-id
MS_TENANT_ID=common
MS_GRAPH_SCOPES=Notes.Read.All,Sites.Read.All

# Notion
NOTION_TOKEN=secret_your_token
NOTION_DATABASE_ID=default-database-id

# Optional
ON2N_STATE=~/.onenote2notion/state.json
```

---

## 🛠️ Verfügbare Tools

### 🌐 **Web-GUI** (NEU!)

Moderne Weboberfläche für alle Migrations-Tools mit grafischer Benutzerführung.

```bash
# Web-Server starten
cd web
python app.py
# → http://localhost:8080
```

**Features:**
- 🔐 **Microsoft OAuth-Authentifizierung**
- 🔍 **Overview-Dashboard** mit Gruppen, Notebooks und Planner-Plänen
- 📓 **OneNote-Migration** mit grafischer Notebook-Auswahl
- 📋 **Planner-Migration** mit Status-Anzeige
- 📊 **Live-Fortschrittsanzeige** während der Migration
- 🎨 **Responsive UI** für Desktop und Mobile

📖 [Vollständige Anleitung](web/README.md) | [Quick Start](web/QUICKSTART.md)

#### 🐳 Docker

```bash
# Image bauen
docker build -t move2notion .

# Container starten (.env muss existieren)
docker run -d --name move2notion \
  --env-file .env \
  -p 8080:8080 \
  move2notion

# → http://localhost:8080
```

---

### 1. **Overview** (CLI + Web)

Alle Microsoft 365-Gruppen im Tenant mit ihren OneNote-Notebooks und Planner-Boards auflisten.

```bash
# Alle Gruppen mit Notebooks und Plans
python -m tools.overview.cli

# Nur Gruppen (schneller bei großen Tenants)
python -m tools.overview.cli --groups-only

# Maschinenlesbare Ausgabe
python -m tools.overview.cli --json
```

**Features:**
- Teams-Gruppen mit IDs auflisten
- OneNote-Notebooks pro Gruppe entdecken
- Planner-Pläne pro Gruppe entdecken
- JSON-Export für Weiterverarbeitung

📖 [Details](documentation/OVERVIEW.md)

### 2. **Planner → Notion** (CLI)

API-basierte Aufgabenmigration mit Personen-Mapping.

```bash
python -m tools.planner_migration.cli \
  --csv "tasks.csv" \
  --database "NOTION_DATABASE_ID"
```

**Features:**
- CSV-Delimiter-Erkennung
- Deutsche Datumsformate
- Personen-Mapping
- Multi-Select Konvertierung
- Upsert-Modus

📖 [Details](documentation/PLANNER.md)

### 3. **OneNote → Notion** (CLI)

Rich-Content-Migration aus SharePoint OneNote.

```bash
python -m tools.onenote_migration.cli \
  --site-url "https://tenant.sharepoint.com/sites/Site" \
  --notebook "Notizbuch" \
  --database-id "NOTION_DATABASE_ID" \
  --resume
```

**Features:**
- **HTML-Parsing**: Überschriften, Listen, Code, Tabellen
- **Text-Formatierungen**: Bold, Italic, Underline, Strikethrough (HTML + CSS)
- **To-Do-Erkennung**: Automatische Checkbox-Erkennung
- **Bild/Datei-Upload**: Permanente Notion-Assets (File Upload API)
- **Idempotente Synchronisation**: Resume-Modus mit Checksummen
- **Smart Updates**: Alte Seite archivieren statt Blöcke einzeln löschen (95% schneller)
- **Zeitfilter**: `--since 2025-01-01` für inkrementelle Imports

📖 [Details](documentation/ONENOTE.md)

---

## 🖥️ CLI vs. Web-GUI

| Feature | CLI | Web-GUI |
|---------|-----|---------|
| **Authentifizierung** | Device Code Flow | OAuth Code Flow |
| **Notebook-Auswahl** | Manuell (ID angeben) | Grafische Auswahl |
| **Fortschritt** | Terminal-Output | Live-Dashboard |
| **Benutzerfreundlichkeit** | Fortgeschritten | Einsteigerfreundlich |
| **Automatisierung** | ✅ Skriptbar | ❌ Interaktiv |
| **Mehrbenutzer** | ❌ | ❌ (Single-User) |

**Empfehlung:**
- **Web-GUI** für gelegentliche, interaktive Migrationen
- **CLI** für Automatisierung und Batch-Verarbeitung

### Application Permissions (Server-zu-Server)

Für automatisierte Pipelines ohne User-Login:

```bash
# .env
MS_AUTH_MODE=application
MS_CLIENT_SECRET=ihr-client-secret

# Für Web-GUI zusätzlich:
ADMIN_PASSWORD=sicheres-passwort
```

Erfordert Azure AD Application Permissions mit Admin Consent.

Siehe [Application Permissions](documentation/APPLICATION_PERMISSIONS.md) für Details.

---

## 🏗️ Architektur

```
ms_notion_migration/
├── core/                    # Gemeinsame Abstraktionen
│   ├── auth.py             # MSAL + Notion (CLI + Web + Application)
│   ├── notion_client.py    # Notion API mit Retry & Rate Limiting
│   ├── ms_graph_client.py  # Microsoft Graph (OneNote, Planner, Groups)
│   ├── state_manager.py    # Idempotenz via Checksummen
│   └── utils.py            # Hilfsfunktionen
│
├── tools/                   # Migrationstools (CLI)
│   ├── overview/            # M365-Gruppen/Notebooks/Plans Discovery
│   ├── planner_migration/   # Planner → Notion
│   └── onenote_migration/   # OneNote → Notion (HTML-Parser, Bilder)
│
├── web/                     # Flask Web-GUI
│   ├── app.py              # Flask-Anwendung (Port 8080)
│   ├── task_manager.py     # Background-Tasks mit SSE-Fortschritt
│   ├── templates/          # HTML-Templates
│   ├── static/             # CSS & JavaScript
│   ├── README.md           # Web-GUI Dokumentation
│   └── QUICKSTART.md       # 5-Minuten-Setup
│
└── documentation/           # Dokumentation
    ├── OVERVIEW.md
    ├── PLANNER.md
    ├── ONENOTE.md
    ├── WEB_GUI.md
    └── APPLICATION_PERMISSIONS.md
```

---

## 🧪 Für Entwickler

```bash
# Tests
pytest tests/

# Code-Stil
black core/ tools/
ruff check core/ tools/

# Type-Check
mypy core/ tools/
```

### Neues Tool hinzufügen

1. Modul in `tools/` erstellen
2. CLI mit `argparse` implementieren
3. Core-Abstraktionen (`auth`, `notion_client`, `ms_graph_client`) nutzen
4. Dokumentation in `docs/` erstellen

---

## 📄 Lizenz

Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0) © 2025 LOUPZ GmbH & Co. KG

**Sie dürfen:**
- ✅ Das Material teilen und weiterverbreiten
- ✅ Das Material remixen, verändern und darauf aufbauen

**Unter folgenden Bedingungen:**
- **Attribution** — Namensnennung erforderlich
- **NonCommercial** — Keine kommerzielle Nutzung erlaubt (kein Wiederverkauf)

Siehe [LICENSE](LICENSE) für Details.

---

## 🤔 Häufige Fragen

**F: Wie funktioniert Resume?**
A: Der Tool speichert Checksummen in `~/.onenote2notion/state.json`. Mit `--resume` werden unveränderte Seiten übersprungen.

**F: Was ist mit Bildern?**
A: Bilder werden heruntergeladen und direkt zu Notion hochgeladen.

**F: Kann ich Fehler beheben und erneut ausführen?**
A: Ja! Mit `--resume` (oder ohne, um zu überschreiben).

**F: Welche Properties braucht die Notion-Datenbank?**
A: Fehlende Properties werden **automatisch ergänzt** (`ensure_database_schema`). In der Web-GUI kann man auch direkt eine neue Datenbank mit passendem Schema erstellen ("+ Neue DB"). Die erwarteten Properties:

- **Planner:** Aufgabenname (title), LPH/Aufgabentyp (select), Status (status), Priorität (select), Fachdisziplin (multi_select), Tags (multi_select), verantwortlich (people), Fälligkeitsdatum (date)
- **OneNote:** Name (title), Section (select), SectionGroup (select), Notebook (rich_text), OneNotePageId (rich_text), SourceURL (url), LastEditedUtc (date)

---

*Für Details: siehe [documentation/](documentation/) oder Issue öffnen.*
