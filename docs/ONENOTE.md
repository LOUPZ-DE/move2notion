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

### ✅ To-Do-Erkennung

Automatische Erkennung von Checkboxen in mehreren Formaten:
- `<input type="checkbox" />`
- Unicode: `☑`, `☐`, `✅`, `◻`
- Markdown: `[x]`, `[ ]`
- Data-Attribute: `data-tag="to-do"`

### ✅ Asset-Handling

- **Bilder**: Download + Upload zu Notion
- **Dateien**: Download + Notion-File-Block
- **Caching**: Bereits geladene Assets werden gecacht
- **Content-Type-Sniffing**: Automatische Typ-Bestimmung

### ✅ Idempotenz

- **Resume-Modus**: `--resume` überspringt unveränderte Seiten
- **Checksum-Vergleich**: Basiert auf HTML-Content
- **State-Datei**: `~/.onenote2notion/state.json`
- **Zeitfilter**: `--since 2025-01-01` für inkrementelle Imports

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

- OneNote-Bilder werden als externe Urls gespeichert (Notion-API-Limit)
- Embedded Objects (Videos, etc.) werden übersprungen
- Nested Lists werden flachgedrückt
