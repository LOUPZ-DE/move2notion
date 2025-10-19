# 🧠 Microsoft-zu-Notion Migration Suite

**Automatisierte Migration von Microsoft-Daten nach Notion**

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

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
- 📓 **OneNote-Migration** mit grafischer Notebook-Auswahl
- 📋 **Planner-Migration** mit Status-Anzeige
- 📊 **Live-Fortschrittsanzeige** während der Migration
- 🎨 **Responsive UI** für Desktop und Mobile

📖 [Vollständige Anleitung](web/README.md) | [Quick Start](web/QUICKSTART.md)

---

### 1. **Planner → Notion** (CLI)

CSV-basierte Aufgabenmigration mit Personen-Mapping.

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

📖 [Details](docs/PLANNER.md)

### 2. **OneNote → Notion** (CLI)

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

📖 [Details](docs/ONENOTE.md)

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

---

## 🏗️ Architektur

```
ms_notion_migration/
├── core/                    # Gemeinsame Abstraktionen
│   ├── auth.py             # MSAL + Notion (CLI + Web)
│   ├── notion_client.py    # Notion API
│   ├── ms_graph_client.py  # Microsoft Graph
│   └── state_manager.py    # Idempotenz
│
├── tools/                  # Migrationstools (CLI)
│   ├── planner_migration/
│   └── onenote_migration/
│
├── web/                    # Flask Web-GUI
│   ├── app.py             # Flask-Anwendung
│   ├── templates/         # HTML-Templates
│   ├── static/            # CSS & JavaScript
│   ├── README.md          # Web-GUI Dokumentation
│   └── QUICKSTART.md      # 5-Minuten-Setup
│
└── docs/                   # Dokumentation
    ├── PLANNER.md
    ├── ONENOTE.md
    └── WEB_GUI.md
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

MIT License © 2025

---

## 🤔 Häufige Fragen

**F: Wie funktioniert Resume?**
A: Der Tool speichert Checksummen in `~/.onenote2notion/state.json`. Mit `--resume` werden unveränderte Seiten übersprungen.

**F: Was ist mit Bildern?**
A: Bilder werden heruntergeladen und direkt zu Notion hochgeladen.

**F: Kann ich Fehler beheben und erneut ausführen?**
A: Ja! Mit `--resume` (oder ohne, um zu überschreiben).

---

*Für Details: siehe [docs/](docs/) oder Issue öffnen.*
