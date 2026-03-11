# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden hier dokumentiert.

Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/)
und das Projekt folgt [Semantic Versioning](https://semver.org/lang/de/).

## [0.9.3] - 2026-03-11

### Hinzugefügt
- **Docker-Support**: Dockerfile mit gunicorn, Healthcheck und optimiertem Layer-Caching
- `.dockerignore` für schlanke Images
- **Startup-Banner**: Farbige ASCII-Art beim Serverstart (funktioniert mit Flask und gunicorn)
- **Landingpage aktualisiert**: Neue Features (Overview, Docker, SSE, Auth-Modi), Doku-Links ergänzt, Python/Docker Install-Tabs

## [0.9.2] - 2026-03-10

### Hinzugefügt
- **Live-Migrations-Fortschritt (SSE)**: Planner- und OneNote-Migrationen laufen als Background-Thread mit Echtzeit-Fortschrittsanzeige via Server-Sent Events
  - Animierter Progressbar mit Streifen-Animation während der Migration
  - Phase-Label zeigt aktuelle Phase (z.B. "Tasks laden", "Import", "Abgeschlossen")
  - Terminal-artiges Live-Log mit farbcodierten Einträgen
  - Summary-Box am Ende mit Erfolg/Fehler-Zähler und Fehler-Details
- **OneNote Web-Migration implementiert**: Vollständige OneNote-Migration über die Web-GUI (war zuvor nur ein Stub)
  - Nutzt bestehende `ContentMapper`-Klasse direkt
  - Notebooks → Sections → Pages mit Fortschritt pro Seite
- Neues Modul `web/task_manager.py`: Task-Infrastruktur mit `MigrationTask`, `TaskManager` und thread-safe Event-Queue
- SSE-Endpoint `GET /api/tasks/<id>/events` für Progress-Streaming
- Status-Fallback `GET /api/tasks/<id>/status` für Reconnect nach Browser-Navigation
- `SSEMigrationClient` JavaScript-Klasse für EventSource-basierte Fortschrittsanzeige

### Verbessert
- Planner-Migration läuft nun asynchron im Background-Thread (kein HTTP-Timeout mehr bei großen Plänen)
- Progress-Bar mit CSS-Streifen-Animation, stoppt bei 100% mit solidem Grün
- Disabled-State für Submit-Buttons während laufender Migration
- **Notion-ID-Eingabe**: Akzeptiert nun auch vollständige Notion-Share-URLs — die Datenbank-ID wird automatisch extrahiert (on paste/blur)

## [0.9.1] - 2026-03-10

### Hinzugefügt
- **Overview → Migration Verknüpfung**: "Migrieren →" Buttons bei Planner-Plänen und OneNote-Notebooks
  - Planner: Plan-ID wird im Planner-Dashboard vorausgefüllt
  - OneNote: SharePoint-Site-URL und Notebook-Name werden vorausgefüllt, Notebook automatisch vorselektiert
- **"Alle Details laden"** Button im Overview für Batch-Abruf aller Gruppen mit Fortschrittsanzeige
- **Session-Persistenz**: Overview-State (Gruppen + Details) überlebt Seitenwechsel via sessionStorage
- **Zusammenfassung**: Anzeige "X mit Zugriff, Y ohne Zugriff" nach Batch-Load
- MS Graph Client: Neue Methode `get_group_site_url()` für SharePoint-URL-Auflösung
- Dokumentation: PowerShell-Skript zur Gruppenmitgliedschaft für Delegated-Modus

### Verbessert
- 403-Fehler im Overview werden als dezenter Hinweis statt rotem Fehler dargestellt
- Gruppen ohne Zugriff visuell abgesetzt (halbtransparent)
- Web-GUI: `MSGraphClient` unterstützt jetzt korrekt den Delegated Web-Modus (session_id)

### Behoben
- `Tasks.Read.All` aus Delegated-Scopes entfernt (nur als Application Permission verfügbar, verursachte `AADSTS650053`)
- `MicrosoftWebAuthenticator` hat kein `.headers`-Property — `MSGraphClient` nutzt jetzt `_get_headers()` mit Session-Fallback

## [0.9.0] - 2026-03-10

### Hinzugefügt
- **Overview-Tool**: Neues CLI-Tool und Web-Dashboard zur Auflistung aller Microsoft 365-Gruppen mit OneNote-Notebooks und Planner-Plänen
  - CLI: `python -m tools.overview.cli` mit `--verbose`, `--groups-only`, `--json` Optionen
  - Web: Neues `/overview`-Dashboard mit Lazy-Loading der Gruppen-Details
  - API: `GET /api/overview/groups` und `GET /api/overview/groups/<id>/details`
- MS Graph Client: Drei neue Methoden (`list_groups`, `list_group_planner_plans`, `list_group_notebooks`)
- Overview-Card auf dem Web-Dashboard und Navbar-Link

## [0.8.5] - 2026-03-10

### Hinzugefügt
- Application Auth Mode (Client Credentials Flow) für Server-zu-Server-Szenarien
- Admin-Passwort-Schutz für Web-GUI im Application Mode
- Fallback-Parser für Text in `<div>`, `<section>` und anderen Block-Elementen ohne `<p>`-Wrapper
- Text-Extraktion für Inhalte rund um verschachtelte Bilder in Formatierungs-Tags

### Behoben
- Listen-Einträge mit Bildern verlieren nicht mehr ihren Textinhalt
- Seiten mit mehr als 150 Blöcken werden nun vollständig migriert (künstliches Limit entfernt)
- Rich-Text länger als 2000 Zeichen wird in Teile aufgesplittet statt stillschweigend abgeschnitten
- Tabellen mit `<tbody>`-Struktur werden korrekt geparst
- Fehlgeschlagene Block-Batches in der Notion API verhindern nicht mehr das Senden der restlichen Batches

## [0.8.0] - 2026-02-15

### Hinzugefügt
- Notion API Retry-Logik mit Exponential Backoff und Rate-Limit-Handling
- Planner-Property-Schema an produktive Notion-Datenbank angepasst
- Bucket-Name-Normalisierung ("Leistungsphase 01" zu "LPH 1")
- Automatische Fachdisziplin-zu-Tags-Filterung für Sonderwerte
- Referenzen als strukturierte Notion-Link-Blöcke

### Geändert
- Status-Werte auf Notion Status-Property abgestimmt (erledigt, in Arbeit, Aufgabenpool)
- Prioritäts-Mapping verfeinert (Dringend, Hoch, Mittel, Niedrig)
- People-Feld in "verantwortlich" umbenannt mit direktem E-Mail-zu-Notion-User-Mapping

## [0.7.0] - 2026-01-20

### Hinzugefügt
- Auto-Mapping von Planner-Nutzern zu Notion-Nutzern via E-Mail (CSV jetzt optional)
- Robustheitsverbesserungen und Bugfixes bei der OneNote-Migration und dem Bildimport

### Geändert
- Lizenz auf CC BY-NC 4.0 umgestellt (vorher MIT)

## [0.6.0] - 2025-12-15

### Hinzugefügt
- GitHub Pages Landingpage für move2notion.de
- Planner-API-Direktintegration für Web-GUI
- Erweiterter Planner-API-Mapper mit Tags, Überfällig-Feld und strukturierten Checklisten

### Geändert
- CSV-Modus entfernt, Planner-CLI auf API-only umgestellt

### Behoben
- Separater Plan-Details-API-Aufruf für categoryDescriptions
- Umgang mit leeren displayNames und ISO-Datumskonvertierung
- User.Read.All via Delegated Permissions für Planner-Nutzerdaten

## [0.5.0] - 2025-11-20

### Hinzugefügt
- Flask Web-GUI mit OAuth Code Flow auf Port 8080
- Interaktive Dashboards für OneNote- und Planner-Migration
- Web-GUI-Dokumentation und Quickstart-Anleitung

## [0.4.0] - 2025-10-25

### Hinzugefügt
- OneNote Text-Formatierungen (Bold, Italic, Underline, Strikethrough, Code)
- Performance-Verbesserungen bei der OneNote-Migration
- LastEditedUtc-Property zur Änderungsverfolgung
- Vollständige OneNote-Migration mit Bild-Upload via Notion File Upload API
- Inline-Bildverarbeitung während des HTML-Parsens
- Workaround: Paragraphen-Aufspaltung bei Bildern

### Behoben
- Doppelte Bild-Uploads eliminiert
- Section- und Notebook-Properties werden korrekt gesetzt

## [0.3.0] - 2025-10-01

### Hinzugefügt
- Vollständige OneNote-Migration mit allen Features (Sections, Seiten, Inhalte)
- Automatisches Laden der .env-Datei
- Idempotente Zustandsverwaltung mit Checksummen

### Behoben
- Fail-Safe Block-Validierung vor Notion-API-Aufrufen
- 2000-Zeichen-Grenze pro rich_text Element durchgesetzt
- Lange Paragraphen werden in mehrere Blöcke aufgeteilt

## [0.2.0] - 2025-09-15

### Hinzugefügt
- Token-Caching für Microsoft Graph Authentifizierung
- urllib3 NotOpenSSLWarning unterdrückt

### Behoben
- StateManager-Fehler und Text-Länge-Limits
- Extension-Whitelist für Notion Upload
- Filterung für mailto- und tel-Links
- OneNote-URL-Endpoint korrigiert

## [0.1.0] - 2025-09-01

### Hinzugefügt
- Erstveröffentlichung: Microsoft-zu-Notion Migration Suite
- Planner-Migration (CSV-basiert)
- OneNote-Migration (Basis)
- Core-Module: auth, notion_client, ms_graph_client, state_manager
- UUID-Format-Normalisierung für Notion IDs
