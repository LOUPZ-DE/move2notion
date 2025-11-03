# Planner → Notion Migration

Migration von Microsoft Planner Tasks in Notion - CSV-basiert (CLI) oder API-direkt (Web-GUI).

---

## Grundlagen

Das Planner-Tool unterstützt zwei Modi:
- **CSV-basiert (CLI)**: Liest **CSV-Dateien** (z.B. aus Excel, Google Sheets) und erstellt/aktualisiert **Notion-Datenbanken**
- **API-basiert (Web-GUI)**: Greift direkt auf Planner-Pläne per **Microsoft Graph API** zu - kein CSV-Export nötig!

Beide Modi bieten automatische Spalten-Erkennung, Personen-Mapping und Multi-Select-Konvertierung.

---

## Verwendung

### Neue Datenbank erstellen

```bash
python -m tools.planner_migration.cli \
  --csv "Aufgaben.csv" \
  --parent "NOTION_PAGE_ID" \
  --db-title "Meine Aufgaben"
```

### In bestehende Datenbank importieren

```bash
python -m tools.planner_migration.cli \
  --csv "Aufgaben.csv" \
  --database "NOTION_DATABASE_ID"
```

### Mit Personen-Mapping

```bash
python -m tools.planner_migration.cli \
  --csv "Aufgaben.csv" \
  --database "..." \
  --people-csv "Notion_Personenmapping_Template.csv"
```

### Mit Upsert (Update/Insert)

```bash
python -m tools.planner_migration.cli \
  --csv "Aufgaben.csv" \
  --database "..." \
  --upsert \
  --unique "Vorgangsnummer"
```

### Argumente

| Argument | Erforderlich | Beschreibung |
|----------|-------------|-------------|
| `--csv` | ✅ | CSV-Dateipath |
| `--database` | - | Ziel-Notion-DB-ID (existing) |
| `--parent` | - | Parent-Page-ID (für neue DB) |
| `--db-title` | - | Titel neue DB (mit --parent) |
| `--people-csv` | - | Personen-Mapping-CSV |
| `--upsert` | - | Update mode (statt insert) |
| `--unique` | - | Spalte für upsert |
| `--dry-run` | - | Test ohne Änderungen |
| `--verbose` | - | Detaillierte Ausgaben |

---

## Features

### ✅ CSV-Verarbeitung

- **Auto-Delimiter**: Erkennt `,`, `;`, `\t`
- **Deutsche Datumsformate**: `TT.MM.JJJJ` → ISO
- **Multi-Select**: `;`-getrennte Werte → Notion Select
- **Boolean**: `ja/nein`, `true/false`, `x` → Checkbox
- **Zahlen**: Auto-Erkennung und Konvertierung

### ✅ Personen-Mapping

Erstellen Sie `Notion_Personenmapping_Template.csv`:

```csv
Name_in_CSV,Notion_Email
"Max Mustermann","max@company.de"
"Anna Schmidt","anna@company.de"
```

Dann:
```bash
python -m tools.planner_migration.cli \
  --csv "..." \
  --database "..." \
  --people-csv "Notion_Personenmapping_Template.csv"
```

### ✅ Automatische Spalten-Erkennung

- Erstellt Notion-Properties basierend auf CSV-Spalten
- Erkennt Datentypen automatisch
- Erweitert bestehende Datenbanken mit neuen Spalten

### ✅ Checklisten-Generierung

Spalten mit `;`-Werten werden automatisch als **nummerierte Listen** eingefügt.

### ✅ Upsert-Modus

Mit `--upsert --unique "Spaltenname"`:
- Existierende Seiten werden aktualisiert
- Neue Seiten werden erstellt
- Ideal für regelmäßige Synchronisation

---

## Architektur

```
tools/planner_migration/
├── cli.py              # CLI + Orchestrierung
├── processor.py        # CSV-Verarbeitung
├── people_mapper.py    # Personen-Mapping
└── notion_mapper.py    # Notion-Property-Mapping
```

### Ablauf

```
CSV-Datei
    ↓ [Lesen]
Rows mit Metadata
    ↓ [Delimiter-Auto-Detect]
Parsed Rows
    ↓ [Spalten-Erkennung]
Notion-Properties Schema
    ↓ [Personen-Mapping]
Mapped Values
    ↓ [Notion-API]
Notion-Database ✅
```

---

## Beispiele

### Beispiel-CSV

```csv
Titel,Beschreibung,Zuständig,Status,Fällig
"Projekt A starten","Kickoff Meeting","Max Mustermann","In Progress","15.10.2025"
"Dokumentation schreiben","API Docs","Anna Schmidt","Not Started","31.10.2025"
"Code Review","PR #123","Max Mustermann;Anna Schmidt","In Review","12.10.2025"
```

### Personen-Mapping-CSV

```csv
Name_in_CSV,Notion_Email
"Max Mustermann","max.mustermann@firma.de"
"Anna Schmidt","anna.schmidt@firma.de"
```

### Import mit Mapping

```bash
python -m tools.planner_migration.cli \
  --csv "tasks.csv" \
  --parent "PAGE_ID" \
  --db-title "Aufgaben" \
  --people-csv "Notion_Personenmapping_Template.csv" \
  --verbose
```

---

## Konfiguration

### `.env`

```bash
# Notion
NOTION_TOKEN=secret_xxx
NOTION_DATABASE_ID=xxx

# Optional
NOTION_RATE_LIMIT=3.0
```

---

## Häufige Aufgaben

### Nur bestimmte Spalten importieren

Einfach die unwanted Spalten aus der CSV entfernen.

### Deutsche Datumsformate

Das Tool erkennt automatisch:
- `15.10.2025` → `2025-10-15`
- `15/10/2025` → `2025-10-15`

### Multi-Select separieren

Spalten-Werte mit `;` werden automatisch zu Notion Multi-Select:
```csv
"Tags"
"Python;API;Testing"
```

### Upsert für Updates

```bash
python -m tools.planner_migration.cli \
  --csv "tasks_updated.csv" \
  --database "EXISTING_DB_ID" \
  --upsert \
  --unique "Titel"
```

---

## Troubleshooting

### CSV wird nicht erkannt
- Stellen Sie sicher, dass der Delimiter korrekt ist
- Tool versucht automatisch: `,`, `;`, `\t`

### Personen-Mapping funktioniert nicht
- Prüfen Sie, dass `Notion_Email` gültig ist
- E-Mail muss im Notion Workspace registriert sein

### Spalten werden nicht erstellt
- Neue Spalten werden nur mit `--database` (existing DB) erstellt
- Mit `--parent` (neue DB) werden alle Spalten aus CSV erstellt

### Dry-Run zeigt falsche Daten
```bash
python -m tools.planner_migration.cli \
  --csv "..." \
  --database "..." \
  --dry-run \
  --verbose
```

---

## Performance

- **CSV-Größe**: Bis 10.000 Zeilen getestet
- **Rate-Limiting**: 3 Requests/Sekunde (automatisch)
- **Batch-Size**: 50 Pages pro Notion-Batch

---

## Bekannte Limitationen

- Nested CSV-Strukturen werden flachgedrückt
- Binary Data (Bilder) nicht direkt unterstützt
- Formeln/Rollups müssen manuell in Notion erstellt werden
