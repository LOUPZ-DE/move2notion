# 🔍 Overview-Tool Dokumentation

Auflistung aller Microsoft 365-Gruppen mit ihren OneNote-Notebooks, Planner-Plänen **und Teams-Channels**.

---

## 📋 Übersicht

Das Overview-Tool dient der **Discovery** von Ressourcen im Microsoft 365 Tenant. Es zeigt alle Teams-Gruppen und deren zugehörige OneNote-Notebooks, Planner-Boards **sowie Teams-Channels** mit Titel und ID an — als Grundlage für gezielte Migrationen.

### Verfügbar als

- **CLI**: `python -m tools.overview.cli`
- **Web-GUI**: Dashboard unter `/overview`

---

## 🚀 CLI-Nutzung

### Alle Gruppen mit Details

```bash
python -m tools.overview.cli
```

Listet alle Microsoft 365-Gruppen auf und ruft pro Gruppe die OneNote-Notebooks und Planner-Pläne ab.

### Mit Fortschrittsanzeige

```bash
python -m tools.overview.cli --verbose
```

Zeigt den Fortschritt pro Gruppe (`[1/25] Gruppenname: 2 Notebooks, 3 Plans`).

### Nur Gruppen (schnell)

```bash
python -m tools.overview.cli --groups-only
```

Listet nur die Gruppen auf, ohne die Detail-Abrufe für Notebooks und Plans. Nützlich bei großen Tenants mit vielen Gruppen.

### JSON-Ausgabe

```bash
python -m tools.overview.cli --json
```

Maschinenlesbare Ausgabe für Weiterverarbeitung, z.B.:

```bash
# Alle Plan-IDs extrahieren
python -m tools.overview.cli --json | python -c "
import json, sys
data = json.load(sys.stdin)
for g in data:
    for p in g.get('plans', []):
        print(f\"{g['name']}: {p['name']} ({p['id']})\")"
```

### CLI-Optionen

| Option | Beschreibung |
|--------|-------------|
| `--verbose`, `-v` | Detaillierte Ausgaben mit Fortschritt |
| `--groups-only` | Nur Gruppen auflisten (ohne Notebooks/Plans) |
| `--json` | Ausgabe als JSON |

### Beispielausgabe

```
Microsoft 365 Overview
==================================================
[OK] 12 Gruppen gefunden

======================================================================
                    MICROSOFT 365 GRUPPEN
======================================================================

──────────────────────────────────────────────────────────────────────
  Projektteam Alpha
  Mail: projektteam-alpha@tenant.onmicrosoft.com
  ID: a1b2c3d4-...

  OneNote Notebooks (2):
    - Projektnotizen
      ID: 1!abc123...
    - Meeting-Protokolle
      ID: 1!def456...

  Planner-Plaene (1):
    - Sprint Board
      ID: xYz789...

  Teams-Channels (3):
    - Allgemein  (standard)
      ID: 19:abc...
    - Architektur (privat)  (private)
      ID: 19:def...
    - Externer Austausch  (shared)
      ID: 19:ghi...

======================================================================
  Zusammenfassung: 12 Gruppen, 8 Notebooks, 5 Planner-Plaene, 27 Teams-Channels
======================================================================
```

---

## 🌐 Web-GUI

### Zugang

Nach dem Login im Web-GUI:
1. **Navbar** → "Overview" klicken
2. Oder direkt: `http://localhost:8080/overview`

### Bedienung

1. **"Gruppen laden"** klicken — ruft alle Microsoft 365-Gruppen ab
2. Pro Gruppe **"Details laden"** klicken — lädt Notebooks, Plans und **Teams-Channels** (oder **"Alle Details laden"** für Batch-Abruf)
3. **"Migrieren →"** Buttons bei Notebooks, Plans **und Channels** — öffnet die jeweilige Migration mit vorausgefüllten IDs. Im Spaltenkopf der Channels-Liste gibt es zusätzlich **"Alle →"**, das alle Channels eines Teams auf einmal in der Teams-Migration vorauswählt.
4. **IDs kopieren** — Text in den ID-Feldern ist direkt selektierbar (`user-select: all`)

### Lazy-Loading

Das Web-GUI lädt Details nicht automatisch für alle Gruppen, um bei großen Tenants schnell zu bleiben. Stattdessen werden Details pro Gruppe erst auf Klick abgerufen. Dies verhindert:
- Lange Ladezeiten bei vielen Gruppen
- Microsoft Graph API Rate-Limiting

### API-Endpoints

| Endpoint | Methode | Beschreibung |
|----------|---------|--------------|
| `/api/overview/groups` | GET | Alle Microsoft 365-Gruppen |
| `/api/overview/groups/<id>/details` | GET | Notebooks + Plans + Teams-Channels einer Gruppe |
| `/api/planner/migrate` | POST | Planner-Migration starten (Background-Thread) |
| `/api/onenote/migrate` | POST | OneNote-Migration starten (Background-Thread) |
| `/api/teams/migrate` | POST | Teams-Migration starten (Background-Thread) |
| `/api/teams/list` | GET | Teams (für Teams-Dashboard) |
| `/api/teams/<team_id>/channels` | GET | Channels eines Teams |
| `/api/tasks/<id>/events` | GET | SSE-Stream für Live-Fortschritt |
| `/api/tasks/<id>/status` | GET | Task-Status (Fallback für Reconnect) |

**Response-Beispiel** (`/api/overview/groups`):

```json
{
  "groups": [
    {
      "id": "a1b2c3d4-...",
      "displayName": "Projektteam Alpha",
      "description": "Hauptprojektgruppe",
      "mail": "projektteam-alpha@tenant.onmicrosoft.com"
    }
  ]
}
```

**Response-Beispiel** (`/api/overview/groups/<id>/details`):

```json
{
  "group_id": "a1b2c3d4-...",
  "notebooks": [
    {"id": "1!abc123...", "displayName": "Projektnotizen"}
  ],
  "notebooks_error": null,
  "plans": [
    {"id": "xYz789...", "title": "Sprint Board"}
  ],
  "plans_error": null,
  "teams_channels": [
    {"id": "19:abc...", "displayName": "Allgemein", "membershipType": "standard"},
    {"id": "19:def...", "displayName": "Architektur", "membershipType": "private"}
  ],
  "teams_channels_error": null
}
```

> Das Feld `teams_channels` ist nur befüllt, wenn die Gruppe als Teams-Team provisioniert ist (Property `resourceProvisioningOptions` enthält `"Team"`). Andernfalls bleibt die Liste leer.

---

## 🔑 Berechtigungen

Das Overview-Tool nutzt ausschließlich bereits konfigurierte Scopes:

| Scope | Zweck |
|-------|-------|
| `Group.Read.All` | Gruppen auflisten |
| `Notes.Read.All` | Notebooks pro Gruppe abrufen |
| `Tasks.Read.All` | Planner-Pläne pro Gruppe abrufen |
| `Channel.ReadBasic.All` | Teams-Channels listen (Discovery, gratis) |
| `Team.ReadBasic.All` | Team-Provisioning prüfen |
| `ChannelMessage.Read.All` | _Erst beim Migrieren_ — Pay-per-API |

Channel-**Discovery** (Listing) ist gratis. Erst das eigentliche Lesen der `messages`-Endpoints in der Teams-Migration löst Microsofts Pay-per-API-Abrechnung aus.

### Einschränkungen nach Auth-Modus

| | Application-Modus | Delegated-Modus |
|---|---|---|
| **Gruppen auflisten** | Alle Gruppen im Tenant | Alle Gruppen im Tenant |
| **Planner-Pläne** | Alle Pläne aller Gruppen | Nur Pläne eigener Gruppen* |
| **OneNote-Notebooks** | Nicht verfügbar (Microsoft-Einschränkung seit 03/2025) | Nur Notebooks eigener Gruppen* |

\* *Im Delegated-Modus zeigt Microsoft Graph nur Daten von Gruppen, in denen der angemeldete Benutzer **Mitglied** ist — unabhängig von Admin-Rollen.*

#### Application-Modus: OneNote blockiert

Microsoft hat seit März 2025 die OneNote-API für App-Only-Tokens (Client Credentials Flow) gesperrt. OneNote-Notebooks werden im Application-Modus **nicht** abgerufen, stattdessen wird ein Hinweis angezeigt.

#### Delegated-Modus: Gruppenmitgliedschaft erforderlich

Auch Global Admins sehen im Delegated-Modus nur Planner-Pläne und OneNote-Notebooks von Gruppen, in denen sie Mitglied sind. Um **alle** Gruppen im Delegated-Modus zu sehen, muss der Benutzer allen Gruppen hinzugefügt werden.

**PowerShell-Lösung** (Microsoft Graph PowerShell SDK):

```powershell
# Voraussetzung: Install-Module Microsoft.Graph -Scope CurrentUser
Connect-MgGraph -Scopes "GroupMember.ReadWrite.All", "User.Read.All", "Group.Read.All"

# Benutzer und Gruppen abrufen
$user = Get-MgUser -Filter "userPrincipalName eq 'it-admin@loupz.de'"
$groups = Get-MgGroup -Filter "groupTypes/any(c:c eq 'Unified')" -All

# Benutzer zu allen M365-Gruppen hinzufuegen
$added = 0
foreach ($group in $groups) {
    try {
        New-MgGroupMember -GroupId $group.Id -DirectoryObjectId $user.Id -ErrorAction Stop
        Write-Host "[+] $($group.DisplayName)" -ForegroundColor Green
        $added++
    } catch {
        if ($_.Exception.Message -like '*already exist*') {
            Write-Host "[=] $($group.DisplayName) (bereits Mitglied)" -ForegroundColor Gray
        } else {
            Write-Host "[-] $($group.DisplayName): $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
}
Write-Host "`n$added Gruppen hinzugefuegt (von $($groups.Count) gesamt)"
```

> **Hinweis:** Nach dem Hinzufügen kann es einige Minuten dauern, bis die Berechtigungen wirksam werden.

#### Empfehlung

- **Vollständige Planner-Übersicht**: Application-Modus verwenden
- **Vollständige OneNote-Übersicht**: Delegated-Modus + Gruppenmitgliedschaft (siehe PowerShell oben)
- **Beides**: Delegated-Modus + Gruppenmitgliedschaft (OneNote funktioniert, Planner funktioniert)

---

## 🔧 Technische Details

### Microsoft Graph Endpoints

| Endpoint | Beschreibung |
|----------|-------------|
| `GET /groups?$filter=groupTypes/any(c:c eq 'Unified')` | Microsoft 365-Gruppen (filtert Security Groups etc. heraus) |
| `GET /groups/{id}/onenote/notebooks` | OneNote-Notebooks einer Gruppe |
| `GET /groups/{id}/planner/plans` | Planner-Pläne einer Gruppe |
| `GET /groups/{id}?$select=resourceProvisioningOptions` | Prüft, ob die Gruppe als Team provisioniert ist |
| `GET /teams/{id}/channels` | Teams-Channels einer Gruppe (sofern Team provisioniert) |

### Fehlerbehandlung

- Wenn Notebooks oder Plans für eine Gruppe nicht abrufbar sind (z.B. fehlende Berechtigungen), wird der Fehler pro Gruppe angezeigt — andere Gruppen werden weiterhin verarbeitet.
- Im CLI wird bei `--verbose` eine Warnung pro fehlgeschlagener Gruppe angezeigt.
- Im Web-GUI werden Fehler inline in der jeweiligen Gruppen-Card dargestellt.

---

## 🗺️ Geplante Erweiterungen

- [x] Klickbare IDs im Web-GUI → "Migrieren →" Button leitet zur Planner-Migration mit vorausgefüllter Plan-ID weiter
- [x] "Alle Details laden"-Button für Batch-Abruf mit Fortschrittsanzeige
- [x] Session-Persistenz: Geladene Daten bleiben bei Seitenwechsel erhalten (sessionStorage)
- [x] Live-Migrations-Fortschritt via SSE (Server-Sent Events) für Planner und OneNote
- [x] OneNote Web-Migration vollständig implementiert (nicht mehr Stub)
- [x] Suchfilter für Gruppen (Live-Filter nach Name, Mail, Beschreibung)
- [x] Export der Übersicht als CSV/JSON im Web-GUI (clientseitiger Download)
