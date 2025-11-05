# Planner → Notion Migration

Migration von Microsoft Planner Tasks in Notion - CSV-basiert (CLI) oder API-direkt (Web-GUI).

---

## Grundlagen

Das Planner-Tool greift **direkt per API** auf Microsoft Planner zu - kein CSV-Export nötig!

**Verfügbare Interfaces:**
- **CLI** (Kommandozeile): Für automatisierte/Batch-Migration
- **Web-GUI**: Interaktive Oberfläche mit OAuth-Login

**Features:**
- Automatische Spalten-Erkennung und Personen-Mapping
- Checklisten als To-Do-Blöcke mit ✅/☐ Status
- Tags aus Planner-Categories
- Automatisches "Verspätet"-Feld

---

## Verwendung

### CLI (Kommandozeile)

```bash
# Plan direkt aus Planner importieren (Personen als Text)
python -m tools.planner_migration.cli \
  --plan-id "PLAN_ID" \
  --database "NOTION_DATABASE_ID"

# Mit Personen-Mapping (optional - für @-Mentions in Notion)
python -m tools.planner_migration.cli \
  --plan-id "PLAN_ID" \
  --database "NOTION_DATABASE_ID" \
  --people-map "Notion_Personenmapping_Template.csv"

# Mit detaillierten Ausgaben
python -m tools.planner_migration.cli \
  --plan-id "PLAN_ID" \
  --database "NOTION_DATABASE_ID" \
  --verbose
```

**Plan ID finden:**

Microsoft Planner nutzt zwei verschiedene URL-Formate:

**Neues Format** (planner.cloud.microsoft):
```
https://planner.cloud.microsoft/webui/plan/k354O9ND3EaLWprSgZrplpgAEMa6/view/board?tid=...
```
→ Plan ID steht im Pfad: `k354O9ND3EaLWprSgZrplpgAEMa6` (zwischen `/plan/` und `/view/`)

**Altes Format** (tasks.office.com):
```
https://tasks.office.com/.../taskboard?groupId=xxx&planId=abc123def456
```
→ Plan ID als Query-Parameter: `planId=abc123def456`

### Web-GUI

1. Starten Sie die Web-GUI: `cd web && python app.py`
2. Öffnen Sie `http://localhost:8080`
3. Login mit Microsoft
4. Navigate zu "Planner Migration"
5. Plan ID + Database ID eingeben → "Migration starten"

![Planner Migration Web-Interface](Move2Notion_screen_planner.png)

*Web-Oberfläche für die Planner-Migration mit interaktiven Formularen*

### Argumente (CLI)

| Argument | Erforderlich | Beschreibung |
|----------|-------------|-------------|
| `--plan-id` | ✅ | Planner Plan ID |
| `--database` | ✅ | Ziel-Notion-DB-ID |
| `--people-map` | ❌ (Optional) | Personen-Mapping-CSV (für @-Mentions) |
| `--verbose` | ❌ (Optional) | Detaillierte Ausgaben |

---

## Features

### ✅ API-Integration

- **Direkter Zugriff**: Keine CSV-Exporte nötig
- **Live-Daten**: Immer aktuelle Daten aus Planner
- **Vollständige Daten**: Alle Felder inkl. Checklisten, Beschreibung, Tags
- **Automatische Konvertierung**: Planner-Daten → Notion-Format

### ✅ Personen-Mapping (Optional)

**Wichtig:** Personen-Mapping ist **optional**!

#### Ohne CSV (Standard - Automatisches E-Mail-Mapping)
- MS Graph liefert E-Mails, die automatisch zu Notion-Benutzern gemappt werden
- Feld: **"Zugewiesen an"** (People Property)
- ✅ @-Mentions funktionieren automatisch
- ✅ Notifications in Notion
- ✅ Keine manuelle CSV-Pflege nötig
- ℹ️ Funktioniert nur für Benutzer, die im Notion Workspace mit derselben E-Mail registriert sind

#### Mit CSV (nur für Edge Cases)
- Manuelles Mapping für Sonderfälle (z.B. verschiedene E-Mail-Adressen)
- Überschreibt automatisches E-Mail-Mapping
- Nützlich wenn Planner- und Notion-E-Mails unterschiedlich sind

Erstellen Sie `Notion_Personenmapping_Template.csv`:

```csv
Name_in_CSV,Notion_Email
"Max Mustermann","max@company.de"
"Anna Schmidt","anna@company.de"
```

Dann:
```bash
python -m tools.planner_migration.cli \
  --plan-id "..." \
  --database "..." \
  --people-map "Notion_Personenmapping_Template.csv"
```

### ✅ Automatische Spalten-Erkennung

- Erstellt Notion-Properties für Planner-Felder
- Erweitert bestehende Datenbanken mit fehlenden Properties
- Fügt Select-Optionen automatisch hinzu

### ✅ Checklisten als To-Do-Blöcke

- Planner-Checklisten → Echte Notion To-Do-Blöcke
- ✅/☐ Status korrekt übernommen
- Interaktive Checkboxen in Notion

### ✅ Tags aus Planner-Categories

- Planner-Labels → Notion Multi-Select Tags
- Automatisches Mapping über Category-Descriptions

### ✅ Verspätet-Feld (automatisch)

- Berechnet aus Fälligkeitsdatum + Completion-Status
- Notion-Checkbox wird automatisch gesetzt

---

## Architektur

```
tools/planner_migration/
├── cli.py                  # CLI + Orchestrierung
├── planner_api_mapper.py   # API-zu-Notion-Konvertierung
├── people_mapper.py        # Personen-Mapping
└── notion_mapper.py        # Notion-Property-Mapping
```

### Ablauf

```
Planner Plan ID
    ↓ [MS Graph API]
Tasks, Buckets, Details, Members
    ↓ [planner_api_mapper.py]
Rows mit Metadata
    ↓ [Spalten-Konvertierung]
Notion-Properties Schema
    ↓ [Personen-Mapping]
Mapped Values
    ↓ [Notion-API]
Notion-Database ✅
```

---

## Beispiele

### CLI-Import

```bash
# Einfacher Import
python -m tools.planner_migration.cli \
  --plan-id "abc123..." \
  --database "def456..."

# Mit Personen-Mapping
python -m tools.planner_migration.cli \
  --plan-id "abc123..." \
  --database "def456..." \
  --people-map "mapping.csv"
```

### Personen-Mapping-CSV

```csv
Name_in_CSV,Notion_Email
"Max Mustermann","max.mustermann@firma.de"
"Anna Schmidt","anna.schmidt@firma.de"
```

### Web-GUI Import

1. Browser: `http://localhost:8080`
2. Login mit Microsoft
3. Planner Migration → Plan ID + Database ID eingeben
4. "Migration starten"

---

## Konfiguration

### `.env`

```bash
# Microsoft Graph API
MS_CLIENT_ID=your-client-id
MS_TENANT_ID=common
MS_GRAPH_SCOPES=Notes.Read.All,Sites.Read.All,Tasks.Read,Group.Read.All,User.Read.All

# Web-GUI (optional)
MS_CLIENT_SECRET=your-client-secret
FLASK_SECRET_KEY=your-secret-key
FLASK_REDIRECT_URI=http://localhost:8080/callback

# Notion
NOTION_TOKEN=secret_xxx
NOTION_DATABASE_ID=xxx
```

### Azure AD Permissions

Erforderliche Scopes:
- `Tasks.Read` - Planner-Tasks lesen
- `Group.Read.All` - Gruppenmitglieder abrufen
- `User.Read.All` - Benutzer-E-Mails für Auto-Mapping (Delegated Permission erforderlich!)
- `Notes.Read.All` - Optional (für OneNote)
- `Sites.Read.All` - Optional (für SharePoint)

**Wichtig:** `User.Read.All` muss als **Delegated Permission** konfiguriert sein, nicht als Application Permission! Planner API funktioniert nur mit User Context (Device Code Flow).

---

## Häufige Aufgaben

### Plan ID herausfinden

Öffne Planner-Plan in Microsoft Planner und kopiere die Plan ID aus der URL:

**Neues Format** (planner.cloud.microsoft):
```
https://planner.cloud.microsoft/webui/plan/PLAN_ID/view/board?tid=...
                                       └──────┬──────┘
                                           Plan ID
```

**Altes Format** (tasks.office.com):
```
https://tasks.office.com/.../taskboard?groupId=xxx&planId=PLAN_ID
                                                           └──┬──┘
                                                           Plan ID
```

### Personen-Mapping erstellen

Erstelle `mapping.csv`:
```csv
Name_in_CSV,Notion_Email
"Max Mustermann","max@firma.de"
```

Dann:
```bash
python -m tools.planner_migration.cli \
  --plan-id "..." \
  --database "..." \
  --people-map "mapping.csv"
```

### Tags werden nicht übernommen

Prüfen Sie, ob Planner-Plan **Labels** verwendet:
- Planner → Plan öffnen → "Kategorien"
- Falls keine Labels: Tags-Feld bleibt leer

---

## Troubleshooting

### "Unauthorized" Fehler
- Prüfen Sie Azure AD Permissions (Tasks.Read, Group.Read.All)
- Token eventuell abgelaufen → neu authentifizieren

### Personen werden nicht als @-Mentions angezeigt
- **Standard-Verhalten:** Ohne `--people-map` werden Namen als Text eingetragen
- **Für @-Mentions:** CSV-Mapping verwenden (`--people-map mapping.csv`)
- Prüfen Sie, dass `Notion_Email` in der CSV gültig ist
- E-Mail muss im Notion Workspace registriert sein

### Checklisten werden nicht übernommen
- Task-Details werden separat abgerufen
- Bei Fehler: Checklist-Feld bleibt leer
- Prüfen Sie mit `--verbose` für Details

### Tags werden nicht angezeigt
- Planner-Plan muss Categories/Labels verwenden
- Ohne Categories: Tags-Feld bleibt leer

---

## Performance

- **Plan-Größe**: Bis 500 Tasks getestet
- **API-Calls**: ~3 pro Task (Task + Details + Batch)
- **Notion-Rate-Limiting**: Automatisch (3 req/s)

---

## Bekannte Limitationen

- Planner-Anhänge (Dateien) werden nur als Links übernommen
- Wiederkehrende Tasks nicht unterstützt (Planner-API hat keine Recurrence)
- Formeln/Rollups müssen manuell in Notion erstellt werden
- Token-Gültigkeit: 60-75 Minuten (Auto-Refresh via MSAL)
