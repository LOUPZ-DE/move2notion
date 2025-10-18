# OneNote → Notion Migration

Rich-Content-Migration aus SharePoint OneNote nach Notion.

---

## Grundlagen

Das OneNote-Tool verbindet sich mit **Microsoft Graph API**, lädt OneNote-Seiten, parst das HTML-Content und erstellt damit strukturierte Notion-Pages mit echten Blöcken (Text, Listen, Bilder, Tabellen, To-Dos).

---

## Verwendung

### Einfacher Import

```bash
python -m tools.onenote_migration.cli \
  --site-url "https://tenant.sharepoint.com/sites/SiteName" \
  --notebook "Mein Notizbuch" \
  --database-id "YOUR_NOTION_DATABASE_ID"
```

### Mit allen Optionen

```bash
python -m tools.onenote_migration.cli \
  --site-url "https://tenant.sharepoint.com/sites/Site" \
  --notebook "Notizbuch" \
  --section "Abschnitt" \
  --database-id "DB_ID" \
  --since 2025-01-01 \
  --resume \
  --verbose
```

### Argumente

| Argument | Erforderlich | Beschreibung |
|----------|-------------|-------------|
| `--site-url` | ✅ | SharePoint-Site-URL |
| `--notebook` | - | Notebook-Name (fuzzy match) |
| `--notebook-id` | - | Notebook-ID (exact) |
| `--section` | - | Section-Name (optional) |
| `--database-id` | ✅ | Notion-Datenbank-ID |
| `--since YYYY-MM-DD` | - | Nur geänderte seit Datum |
| `--resume` | - | Überspringe unveränderte |
| `--dry-run` | - | Test ohne Änderungen |
| `--verbose` | - | Detaillierte Ausgaben |

---

## Features

### ✅ Content-Parsing

- **Überschriften** (H1-H3) → Notion Heading-Blöcke
- **Absätze** → Notion Paragraph-Blöcke  
- **Listen** (ul, ol) → Bulleted/Numbered Items
- **Code-Blöcke** → Notion Code-Blöcke
- **Zitate** → Notion Quote-Blöcke
- **Tabellen** → Notion Table-Blöcke
- **Links** → Rich-Text mit URLs

### ✅ Text-Formatierungen

Das Tool erkennt automatisch **alle Text-Formatierungen** aus OneNote:

- **Bold** (fett) - HTML-Tags (`<strong>`, `<b>`) + CSS (`font-weight:bold`)
- **Italic** (kursiv) - HTML-Tags (`<em>`, `<i>`) + CSS (`font-style:italic`)
- **Underline** (unterstrichen) - HTML-Tag (`<u>`) + CSS (`text-decoration:underline`)
- **Strikethrough** (durchgestrichen) - HTML-Tags (`<strike>`, `<s>`, `<del>`) + CSS (`text-decoration:line-through`)
- **Code** (inline) - HTML-Tag (`<code>`)
- **Kombinierte Formatierungen** (z.B. fett + kursiv)

OneNote verwendet häufig CSS-Styles statt HTML-Tags - beides wird unterstützt!

### ✅ To-Do-Erkennung

Automatische Erkennung von Checkboxen in mehreren Formaten:
- `<input type="checkbox" />`
- Unicode: `☑`, `☐`, `✅`, `◻`
- Markdown: `[x]`, `[ ]`
- Data-Attribute: `data-tag="to-do"`

### ✅ Asset-Handling (Bilder & Dateien)

Das Tool **übernimmt automatisch Bilder und Dateien** aus OneNote-Seiten:

- **Bilder**: Werden heruntergeladen und mit **Notion File Upload API** hochgeladen
- **Inline-Bilder**: Werden direkt im Text-Flow platziert (wie in OneNote)
- **Dateien**: Dokumente, PDFs, etc. werden als File-Blöcke eingefügt
- **Caching**: Bereits geladene Assets werden gecacht (gleiche URL = 1x Upload)
- **Content-Type-Sniffing**: Automatische Typ-Bestimmung (PNG, JPG, PDF, DOCX, etc.)
- **Error-Handling**: Upload-Fehler unterbrechen nicht den Import

**Beispiel:**
```
OneNote-Seite mit 3 Bildern
    ↓
Bilder werden von Microsoft Graph heruntergeladen
    ↓
Mit Notion File Upload API hochgeladen
    ↓
Notion-Page enthält 3 inline Bild-Blöcke ✅
```

**Hinweis:** Bilder werden als **permanente Notion-Assets** gespeichert, nicht als externe URLs!

### ✅ Idempotenz & Updates

**Create vs. Update:**
- **Neue Seiten**: Werden in Notion erstellt
- **Bestehende Seiten**: Werden erkannt via `OneNotePageId`-Property
- **Update-Verhalten**: Alte Seite wird archiviert, neue wird erstellt
  - **Warum?** Schneller als einzelne Blöcke zu löschen (2 statt 40+ API-Calls)
  - **Vorteil:** Alte Version bleibt im Archiv als Backup

**Resume-Modus:**
- `--resume` überspringt unveränderte Seiten
- **Checksum-Vergleich**: Basiert auf HTML-Content-Hash
- **State-Datei**: `~/.onenote2notion/state.json`
- **Zeitfilter**: `--since 2025-01-01` für inkrementelle Imports

**Beispiel:**
```
Import 1: Seite "Meeting Notes" erstellt
Import 2: Seite unverändert → übersprungen (--resume)
Import 3: Seite geändert → alte archiviert, neue erstellt
```

---

## Architektur

```
tools/onenote_migration/
├── cli.py              # CLI + Orchestrierung
├── html_parser.py      # OneNote-HTML → Notion-Blöcke
├── resource_handler.py # Asset-Download & Upload
└── content_mapper.py   # Page → Notion-Integration
```

### Ablauf

```
SharePoint-Site
    ↓ [Site-URL-Auflösung]
Site-ID
    ↓ [Notebook-Suche]
Notebook
    ↓ [Section-Laden]
Sections
    ↓ [Page-Laden]
OneNote-Pages (HTML)
    ↓ [HTML-Parsing]
Notion-Blöcke (Text, Bilder, etc.)
    ↓ [Notion-API]
Notion-Page ✅
```

---

## Konfiguration

### `.env`

```bash
# Microsoft
MS_CLIENT_ID=xxx
MS_TENANT_ID=common
MS_GRAPH_SCOPES=Notes.Read.All,Sites.Read.All

# Notion
NOTION_TOKEN=secret_xxx
NOTION_DATABASE_ID=xxx

# Optional
ON2N_STATE=~/.onenote2notion/state.json
```

---

## Häufige Aufgaben

### Nur bestimmte Section migrieren

```bash
python -m tools.onenote_migration.cli \
  --site-url "..." \
  --notebook "Notizbuch" \
  --section "Team Meetings" \
  --database-id "..."
```

### Nur seit heute Änderungen

```bash
python -m tools.onenote_migration.cli \
  --site-url "..." \
  --notebook "Notizbuch" \
  --since 2025-10-18 \
  --resume
```

### Dry-Run testen

```bash
python -m tools.onenote_migration.cli \
  --site-url "..." \
  --notebook "Notizbuch" \
  --database-id "..." \
  --dry-run
```

---

## Troubleshooting

### Auth-Fehler
- Device Code Flow wird gestartet
- Folgen Sie dem Link und geben Sie den Code ein
- Stellen Sie sicher, dass `MS_CLIENT_ID` und `MS_TENANT_ID` gesetzt sind

### "Notebook nicht gefunden"
```bash
# Verfügbare Notebooks auflisten (wird angezeigt bei Fehler)
python -m tools.onenote_migration.cli \
  --site-url "..." \
  --notebook "NonExistent" \
  --database-id "..."
```

### Bilder werden nicht hochgeladen
- Stellen Sie sicher, dass `NOTION_TOKEN` gültig ist
- Notion-Integration muss `file_uploads`-Berechtigungen haben

### Resume funktioniert nicht
```bash
# State-Datei löschen für vollständigen Reimport
rm ~/.onenote2notion/state.json
```

---

## Performance

- **Page-Limit**: 150 Blöcke pro Page (Notion-Limit)
- **Rate-Limiting**: 3 Requests/Sekunde (automatisch)
- **Batch-Größe**: 50 Blöcke pro Request

---

## Bekannte Limitationen

- **Nested Lists**: Werden flach dargestellt (Notion-API-Limitation)
- **Embedded Videos**: Werden übersprungen (nur Links bleiben)
- **Page-Größe**: Max. 150 Blöcke pro Page (Notion-Limit)
- **Datei-Größe**: Max. 20 MB pro File-Upload (Notion-Limit)

**Was funktioniert:**
- ✅ Bilder werden permanent in Notion hochgeladen
- ✅ Text-Formatierungen (bold, italic, underline, strikethrough)
- ✅ To-Do-Listen mit Checkbox-Status
- ✅ Tabellen als echte Notion-Tables
- ✅ Inline-Links
