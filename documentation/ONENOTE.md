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
| `--resume` | - | Überspringe unveränderte Seiten (basierend auf LastEditedUtc) |
| `--dry-run` | - | Test ohne Änderungen |
| `--verbose` | - | Detaillierte Ausgaben |
| `--resolve-links` | - | **NUR** Link-Resolution ohne Import (für nachträgliche Korrekturen) |
| `--state-path` | - | Pfad für State-Datei |

---

## Features

### ✅ Content-Parsing

- **Überschriften** (H1-H3) → Notion Heading-Blöcke
- **Absätze** → Notion Paragraph-Blöcke  
- **Listen** (ul, ol) → Bulleted/Numbered Items
- **Nested Lists** → Verschachtelte Listen bis zu 3 Ebenen! *(NEU)*
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

### ✅ OneNote-interne Links (automatisch)

OneNote-Seiten können Links zu anderen Seiten im selben Notizbuch enthalten. Diese werden **automatisch** erkannt und korrigiert.

> **Wichtig:** Beim normalen Import wird die Link-Resolution **automatisch** am Ende ausgeführt!  
> Das Flag `--resolve-links` ist **nur für nachträgliche Korrekturen** gedacht.

**Was passiert beim Import?**
1. Seiten werden nach Notion importiert
2. Interne Links werden erkannt (`onenote:...`, `page-id=...`)
3. **Automatisch:** Link-Resolution läuft am Ende des Imports
4. Links zu bereits importierten Seiten werden zu Notion-Links korrigiert

```bash
# Standard-Import (Link-Resolution läuft automatisch!)
python -m tools.onenote_migration.cli \
  --site-url "..." \
  --notebook "..." \
  --database-id "..."
```

**Wann `--resolve-links` verwenden?**

Nur in diesen Fällen:
- Nachträglicher Import weiterer Seiten (neue Verlinkungsziele)
- Manuelle Korrektur nach Fehlern

```bash
# NUR Link-Resolution (KEIN Import!)
python -m tools.onenote_migration.cli \
  --site-url "..." \
  --database-id "..." \
  --resolve-links
```

**Nicht auflösbare Links:**
- Links zu Seiten außerhalb des Imports bleiben markiert: `"(Verlinkung unvollständig)"`
- Können später manuell in Notion korrigiert werden

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
- `--resume` überspringt bereits importierte, unveränderte Seiten
- **Timestamp-Vergleich**: `OneNote.lastModifiedDateTime` vs. `Notion.LastEditedUtc`
- **Voraussetzung**: Notion-Datenbank muss Feld `LastEditedUtc` (Date) haben
- **Zeitfilter**: `--since 2025-01-01` für inkrementelle Imports (MS Graph Filter)

**Beispiel:**
```
Import 1: Seite "Meeting Notes" erstellt
Import 2 (--resume): 
    ⏭️ Seite: Meeting Notes (unverändert seit 2025-11-20)
Import 3 (--resume): Seite in OneNote geändert → alte archiviert, neue erstellt
```

**Wie es funktioniert:**
1. Prüft ob Seite bereits in Notion existiert (via `OneNotePageId`)
2. Vergleicht Timestamps: `OneNote.lastModifiedDateTime` ≤ `Notion.LastEditedUtc`
3. Wenn unverändert → Seite wird übersprungen (spart API-Calls!)

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

- **Nested Lists**: Max. 3 Ebenen (Notion-API-Limitation)
- **Embedded Videos**: Werden übersprungen (nur Links bleiben)
- **Page-Größe**: Max. 150 Blöcke pro Page (Notion-Limit)
- **Datei-Größe**: Max. 20 MB pro File-Upload (Notion-Limit)
- **Interne Links**: Nur zu Seiten im selben Import auflösbar

**Was funktioniert:**
- ✅ Bilder werden permanent in Notion hochgeladen
- ✅ Text-Formatierungen (bold, italic, underline, strikethrough)
- ✅ To-Do-Listen mit Checkbox-Status
- ✅ Tabellen als echte Notion-Tables
- ✅ Inline-Links
- ✅ **Nested Lists** bis zu 3 Ebenen Tiefe *(NEU)*
- ✅ **OneNote-interne Links** automatisch korrigiert *(NEU)*
