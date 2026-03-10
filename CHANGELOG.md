# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden hier dokumentiert.

Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/)
und das Projekt folgt [Semantic Versioning](https://semver.org/lang/de/).

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
