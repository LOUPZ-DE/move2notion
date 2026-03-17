# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden hier dokumentiert.

Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/)
und das Projekt folgt [Semantic Versioning](https://semver.org/lang/de/).

## [0.9.8] - 2026-03-16

### Hinzugefuegt
- **Stopp-Button fuer laufende Migrationen**: OneNote- und Planner-Migrationen koennen jetzt ueber die Web-GUI abgebrochen werden
  - Roter "Migration stoppen"-Button erscheint waehrend der Migration neben dem Start-Button
  - Kooperativer Abbruch: Die aktuelle Seite/der aktuelle Task wird noch fertig importiert (kein halbfertiger Import)
  - Phase-Badge wechselt auf orange "Abgebrochen", Summary zeigt importierte + ausstehende Eintraege
  - Neuer API-Endpoint `POST /api/tasks/<id>/cancel`
  - Neuer TaskStatus `CANCELLED` im Task-Manager

### Behoben
- **Bilder bei Multi-Token-Pool nicht sichtbar**: file_upload-IDs sind an den erstellenden Token gebunden — bei Round-Robin verwendeten Upload und `append_blocks` unterschiedliche Tokens (`404 object_not_found`). Neuer Token-Pin-Mechanismus (`pin_token`/`unpin_token`) stellt sicher, dass alle Notion-Operationen einer Seite denselben Token verwenden.
- **Microsoft Graph API 429 Rate-Limiting**: Alle Graph-API-Aufrufe haben jetzt automatisches Retry bei 429- und 5xx-Fehlern (max. 8 Versuche mit exponentiellem Backoff 2–16s). Betrifft JSON-Requests (`_make_request`), Seiteninhalt (`get_page_content`), Ressourcen (`get_resource_content`) und Bild-Downloads (`resource_handler`, `html_parser`). Zuvor fuehrten Rate-Limits zum Verlust ganzer Seiten und Bilder.
- **Docker: Neustart bei parallelen Migrationen**: Gunicorn-Timeout von 300s auf 900s und Threads von 4 auf 24 erhoeht — bei 3+ parallelen Migrationen mit 429-Retries waren alle 4 Threads blockiert, wodurch der Heartbeat ausblieb und gunicorn den Prozess neu startete. Unterstuetzt jetzt bis zu 10 parallele Migrationen

## [0.9.7] - 2026-03-13

### Hinzugefuegt
- **Planner-Migration: Checkbox "archivieren"**: Wird bei Status "erledigt" automatisch auf `true` gesetzt, bei allen anderen Status auf `false` — nur wenn das Feld in der Notion-Datenbank bereits existiert (kein automatisches Anlegen)

### Verbessert
- **Dynamisches Rate-Limiting**: Batch-Sleep passt sich automatisch an Token-Anzahl und laufende Migrationen an
  - Formel: `0.12s / Tokens * aktive_Worker` — kein manuelles Tuning noetig
  - 2 Tokens, 1 Migration: 0.06s Sleep (doppelter Durchsatz)
  - 2 Tokens, 2 parallele Migrationen: 0.12s Sleep (faires Budget-Sharing)
  - Worker-Tracking via `register_worker()`/`unregister_worker()` im Token-Pool

### Entfernt
- **`NOTION_RATE_LIMIT` Umgebungsvariable**: Hatte keine Wirkung (toter Code). Rate-Limiting wird jetzt vollstaendig ueber den Token-Pool gesteuert
  - `setup_rate_limiting()` aus `core/utils.py` entfernt
  - `NOTION_RATE_LIMIT=3.0` aus `.env.example` entfernt

## [0.9.6] - 2026-03-12

### Behoben
- **Planner-Migration: Lange Texte fuehren nicht mehr zu API-Fehlern**: Rich-Text-Inhalte >2000 Zeichen (Beschreibungen, Checklisten, Referenzen) werden automatisch in mehrere Notion-konforme Chunks gesplittet
  - Notion API Limit: max. 2000 Zeichen pro `rich_text`-Element
  - Betrifft: Beschreibungen, strukturierte/CSV-Checklisten, Referenz-Titel und -Links
  - Gleiches Muster wie bereits in der OneNote-Migration implementiert
- **Gruppen-Uebersicht: Fehlerhafte Details werden nicht mehr gecacht**: Token-Fehler und andere temporaere Fehler beim Laden von Notebooks/Plaenen werden nicht im sessionStorage gespeichert
  - "Neu laden"-Button bei fehlerhaften Gruppen statt dauerhaft gesperrtem "Geladen"
  - Benutzerfreundliche Meldung bei abgelaufener Sitzung statt roher Fehlermeldung
- **Docker: Sporadische "No token available"-Fehler behoben**: Gunicorn von 2 auf 1 Worker reduziert — mehrere Worker-Prozesse hatten jeweils eigenen Token-Cache, wodurch Requests zufaellig an Worker ohne Token gingen

### Hinzugefuegt
- **Planner-Migration: Checkbox "beauftragt"**: Wird automatisch im Datenbankschema angelegt und bei jedem Import auf `true` gesetzt
- **Multi-Token-Support (Round-Robin)**: Mehrere Notion API Tokens fuer hoeheren Durchsatz bei parallelen Migrationen
  - Kommaseparierte Tokens in `NOTION_TOKEN` Umgebungsvariable: `NOTION_TOKEN=secret_abc,secret_def`
  - Thread-sicherer Round-Robin verteilt Requests gleichmaessig auf alle Tokens
  - Linear skalierbar: 2 Tokens = ~6 req/s statt 3 req/s (Notion Rate Limit pro Integration)
  - Volle Rueckwaertskompatibilitaet: Ein einzelner Token funktioniert wie bisher
  - Logging bei Mehrfach-Tokens: `[i] Notion Token-Pool: N Tokens konfiguriert (Round-Robin)`

## [0.9.5] - 2026-03-11

### Hinzugefuegt
- **Hierarchische Nummerierung fuer OneNote-Unterseiten**: Seiten mit Unterebenen erhalten automatisch Nummern-Prefixe im Titel (z.B. `1. Obere Ebene`, `1.1. Untere Ebene`, `1.1.1. Untere untere Ebene`)
  - Erhaelt die OneNote-Seitenhierarchie (Level 0/1/2) in der flachen Notion-Datenbank
  - Nur Seiten mit Unterseiten werden nummeriert, alleinstehende Seiten bleiben unveraendert
  - Zero-Padding bei >9 Eintraegen (z.B. `01.`, `02.`, ..., `12.`)
  - Basiert auf `pagelevel=true` Parameter der Microsoft Graph API
  - Funktioniert in CLI und Web-GUI
- **Auto-Schema fuer Notion-Datenbanken**: `ensure_database_schema()` prueft und ergaenzt fehlende Properties automatisch vor der Migration
  - OneNote: Name, Section, SectionGroup, Notebook, OneNotePageId, SourceURL, LastEditedUtc
  - Planner: Aufgabenname, LPH/Aufgabentyp, Status, Prioritaet, Fachdisziplin, Tags, verantwortlich, Faelligkeitsdatum
  - Beruecksichtigt Section/Bereich- und SectionGroup/Unterbereich-Aliase bei OneNote
- **Datenbank-Erstellung in der Web-GUI**: Neuer "+ Neue DB"-Button neben dem Datenbank-ID-Feld
  - Ausklappbares Panel mit Datenbank-Name und Eltern-Seiten-ID
  - Erstellt Notion-Datenbank mit korrektem Schema (OneNote oder Planner)
  - DB-ID wird automatisch ins Formular eingetragen
  - Neuer API-Endpoint `POST /api/notion/create-database`
- **Inline-Schema-Referenz**: "Schema anzeigen"-Link unter dem DB-ID-Feld zeigt die erwarteten Properties als animiertes Panel mit Property-Chips
- **PWA-Unterstuetzung**: Web-GUI ist als App installierbar (Chrome/Edge/Safari)
  - Web App Manifest mit App-Name "Move2Notion", Theme-Color, Icons
  - App-Icon (M→N auf Indigo-Gradient) in SVG + PNG (192px, 512px)
  - Favicon (16px, 32px) und Apple Touch Icon (180px)
  - Minimaler Service Worker fuer Installierbarkeit
- **Overview Suchfilter**: Live-Filterfeld durchsucht Gruppen nach Name, Mail und Beschreibung
  - Zaehler zeigt "X von Y Gruppen" bei aktivem Filter
  - X-Button zum Zuruecksetzen
- **Overview Export**: JSON- und CSV-Export der geladenen Uebersicht
  - Clientseitiger Download ohne Server-Roundtrip
  - CSV mit BOM fuer korrekte Umlaute in Excel
  - Dateiname mit Datum: `m365-overview-YYYY-MM-DD.json/csv`
- **FAQ erweitert**: Neuer Eintrag "Welche Properties braucht die Notion-Datenbank?" in README.md

### Verbessert
- `ContentMapper` hat jetzt `BASE_PROPERTIES` als Klassenkonstante (statt hartcodiert)

## [0.9.4] - 2026-03-11

### Hinzugefügt
- **Farbübernahme aus OneNote**: CSS-Textfarben und Hintergrundfarben werden auf Notion-Annotationen gemappt
  - Unterstützt benannte Farben (`red`, `green`), Hex (`#FF0000`), `rgb()`-Werte
  - Mapping auf Notions 9 Farben: red, green, blue, orange, yellow, purple, pink, brown, gray (+ `*_background`)
  - Schwarz/Weiß/sehr helle Farben werden ignoriert (Standard-Textfarbe in Notion)
- **Bisection-Retry bei Notion-Blockfehlern**: Schlägt ein Batch von 50 Blöcken fehl, wird er halbiert und erneut versucht — so wird nur der fehlerhafte Block übersprungen statt des gesamten Batches
- **Link-Validierung**: Ungültige URLs (`file:///`, `mailto:`, Netzwerkpfade) werden vor dem Senden an Notion entfernt und als `[Link: ...]` im Text erhalten
  - Zweistufig: Erkennung im HTML-Parser (`html_parser.py`) und als Safety-Net in `_validate_blocks()` (`content_mapper.py`)
- **Post-Import-Verifikation**: Nach jeder importierten Seite wird die tatsächliche Blockanzahl in Notion geprüft und mit der erwarteten verglichen
- **Section-Property flexibles Matching**: Unterstützt sowohl "Section" als auch "Bereich" als Property-Name in der Notion-Datenbank, inkl. `multi_select`-Typ
- **SectionGroup-Property flexibles Matching**: Unterstützt sowohl "SectionGroup" als auch "Unterbereich" als Property-Name in der Notion-Datenbank

### Verbessert
- **Kompakteres Migrations-UI**: Phase-Badge sitzt nun inline neben dem Start-Button statt in separatem Block
  - "Migration"-Überschrift entfernt
  - Progressbar und Statustext direkt im Formular-Card eingebettet (mit Trennlinie)
  - Log-Output als eigenständiger Bereich unter der Karte
  - Phase-Badge wechselt Farbe: blau (pulsierend) → grün (Erfolg) / rot (Fehler)
- `append_blocks` gibt jetzt `_failed_blocks` und `_total_blocks` im Result zurück
- MS Graph `get_page_content` und `get_resource_content` nutzen `_get_headers()` statt `auth.microsoft.headers` (Web-kompatibel)
- `resource_handler.py` nutzt `_get_headers()` für Web-Session-Kompatibilität
- Reduziertes Debug-Logging bei Section-/Page-Auflistung
- `NotionClient` wird in Web-Migrationen mit `auth_manager_instance` initialisiert

### Behoben
- Fehlende Bilder bei OneNote-Import wenn ein ungültiger Link (`file:///`) im selben Batch war — der gesamte Batch (inkl. Bilder) wurde verworfen
- Progressbar hatte `min-width: 48px` gefehlt (Prozentanzeige bei 0% abgeschnitten)
- `main` CSS-Selektor zu `main.container` korrigiert

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
