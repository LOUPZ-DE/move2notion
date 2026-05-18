# Teams → Notion Migration

Migration von Microsoft Teams **Channels** und ihren Beiträgen (inkl. Replies, Reactions, @Mentions, Anhänge und Inline-Bilder) in Notion. Pro Channel wird **eine Notion-Page** als chronologischer Chat-Verlauf erzeugt.

---

## Grundlagen

Das Teams-Tool nutzt die Microsoft-Graph-API direkt. Pro Migration wird im Ziel-Workspace eine Notion-Datenbank befüllt, in der **jede Channel-Page eine Zeile** ist. Der Page-Body enthält den vollständigen Chat-Verlauf — pro Beitrag ein Toggle mit Header („**Absender** · _Datum_ · Vorschau") und nested Children (Body, Anhänge, Reactions, Replies).

**Verfügbare Interfaces:**
- **CLI** (`python -m tools.teams_migration.cli`)
- **Web-GUI** unter `/teams`
- **Overview-Integration** unter `/overview` — pro M365-Gruppe wird eine dritte Spalte „Teams Channels" mit „Migrieren →"-Buttons angezeigt

**Migrierte Inhalte:**
- Top-Level-Beiträge mit HTML-Body (Listen, Formatierungen, Links, Code)
- Replies/Threads (rekursiv als nested Toggles)
- Reactions (👍 ❤️ 😂 …) als kursive Zeile am Ende jeder Message
- @Mentions als Inline-Markup (blau, Email-Link sofern vorhanden)
- Inline-Bilder (`hostedContents`) → Notion File Upload + Image-Block
- Datei-Anhänge (SharePoint/OneDrive) als Bookmark-Block (kein Re-Upload)
- Absender-Name + ISO-Datum im Toggle-Header

---

## ⚠ Voraussetzung: User-Lizenz mit Teams

Der eingeloggte Benutzer braucht eine **gültige Microsoft-365-/Office-365-Lizenz mit Teams-Funktion**. Ohne zugewiesene Lizenz antwortet die `messages`-API mit:

```
403 Forbidden — Failed to get license information for the user.
Ensure user has a valid Office365 license assigned to them.
```

Typische Stolperfalle: **dedizierte Admin-Accounts** (z. B. `it-admin@…`) haben oft alle API-Berechtigungen, aber keine zugewiesene M365-Lizenz, weil sie nur fürs Verwalten gedacht sind. Sobald sie als User für eine User-bezogene API (wie Teams Channels) auftreten, prüft Microsoft die Lizenz und blockt.

**Lösungen:**

- **Variante A** — dem Admin-Account eine M365-Lizenz zuweisen (M365 Business Basic ~5 €/Monat, oder eine vorhandene E3/E5-Lizenz im Tenant).
- **Variante B (empfohlen für Tests)** — mit einem regulären User-Account einloggen, der bereits eine M365-Lizenz hat. Dieser sieht in `/me/joinedTeams` aber nur Teams, in denen er Mitglied ist.

### Pay-per-API gilt _nicht_ für Delegated-Modus

Microsofts „Protected APIs / Pay-per-API"-Anforderung (Modell A / Modell B) betrifft ausschließlich den **Application-Only**-Modus (Client Credentials Flow, App-Token ohne User). Da diese Suite mit Delegated-Login (User-OAuth) arbeitet, ist **keine** zusätzliche Tenant-Lizenz im Admin Center nötig — die Quote richtet sich nach Microsoft Graphs Standard-Rate-Limits.

---

## Berechtigungen / Scopes

Erforderlich (Delegated):

| Scope | Zweck |
|-------|-------|
| `Team.ReadBasic.All` | Teams auflisten |
| `Channel.ReadBasic.All` | Channels eines Teams auflisten |
| `ChannelMessage.Read.All` | Channel-Messages lesen (**Pay-per-API**) |

Konfiguration in `.env`:

```
MS_GRAPH_SCOPES=Notes.Read.All,Sites.Read.All,Tasks.Read,Group.Read.All,User.Read.All,ChannelMessage.Read.All,Channel.ReadBasic.All,Team.ReadBasic.All
```

> **Application-Modus**: Aktuell **nicht** unterstützt — Pay-per-API erfordert ein Delegated-Token.

---

## CLI-Nutzung

```bash
# Alle Channels eines Teams migrieren
python -m tools.teams_migration.cli \
  --team-id 11111111-2222-3333-4444-555555555555 \
  --database-id <notion-db-id>

# Nur bestimmte Channels
python -m tools.teams_migration.cli \
  --team-id <team-id> \
  --channel-id <channel-1> \
  --channel-id <channel-2> \
  --database-id <db-id>

# Team via Anzeigename suchen (exakter Match)
python -m tools.teams_migration.cli \
  --team-name "Projektteam Alpha" \
  --database-id <db-id>

# Nur Channels anzeigen (kein Import)
python -m tools.teams_migration.cli --team-id <id> --database-id <db-id> --dry-run

# Detaillierte Logs
python -m tools.teams_migration.cli --team-id <id> --database-id <db-id> --verbose
```

### CLI-Optionen

| Option | Beschreibung |
|--------|--------------|
| `--team-id` | Team-/M365-Group-ID (UUID). Mutually exclusive mit `--team-name`. |
| `--team-name` | Anzeigename (exakte Übereinstimmung). |
| `--database-id` | Notion-DB-ID oder Share-URL. **Erforderlich**. |
| `--channel-id` | Optional: Nur diese Channel-ID(s) migrieren. Mehrfach erlaubt. |
| `--state-path` | Pfad zur State-Datei (Default `~/.onenote2notion/state.json`). |
| `--dry-run` | Listet Channels auf, migriert nicht. |
| `--verbose`, `-v` | Detaillierte Ausgaben. |

**Beispielausgabe:**

```
[i] Team: Projektteam Alpha  (ID: 11111111-…)
[i] 4 Channel(s) zu migrieren (von insgesamt 4 im Team)
[➡] [1/4] Channel: Allgemein
    142 Top-Level-Beitraege (28 Replies)
    ✓ 142 Messages, 0 fehlgeschlagene Bloecke
[➡] [2/4] Channel: Architektur (privat)
    87 Top-Level-Beitraege (14 Replies)
    ✓ 87 Messages, 0 fehlgeschlagene Bloecke
…
=== Zusammenfassung ===
  Channels migriert:    4
  Messages insgesamt:   289
  Fehlgeschlagene Bl.:  0
```

---

## Web-GUI-Bedienung

1. Login (Delegated, OAuth) → Dashboard → Tile **„Teams Migration"** klicken (oder Navbar-Link „Teams").
2. **„Teams laden"** → Dropdown füllt sich mit allen Teams, in denen der angemeldete User Mitglied ist.
3. Team auswählen → **„Channels laden"** → Channel-Karten erscheinen mit Multi-Select-Checkboxen. Buttons „Alle" / „Keine" für Bulk-Auswahl.
4. **Notion Datenbank-ID** eingeben (oder per **„+ Neue DB"** eine neue Datenbank mit dem Teams-Schema erstellen lassen).
5. **„Migration starten"** → Live-Fortschritt via SSE, Cancel-Button stoppt zwischen Channels.

### Direkte Migration aus Overview

Im Overview-Dashboard (`/overview`) listet jede M365-Gruppe ihre Channels in einer dritten Spalte. Ein Klick auf **„Migrieren →"** führt zum Teams-Dashboard mit vorausgewähltem Team und Channel (`?team_id=…&channel_id=…`). Der Spaltenkopf-Link **„Alle →"** öffnet das Dashboard ohne Channel-Filter, sodass alle Channels des Teams ausgewählt werden können.

### API-Endpoints

| Endpoint | Methode | Beschreibung |
|----------|---------|--------------|
| `/api/teams/list` | GET | Alle Teams des Users (Delegated). |
| `/api/teams/<team_id>/channels` | GET | Channels eines Teams. |
| `/api/teams/migrate` | POST | Migration starten. Body: `{team_id, channel_ids[], database_id}`. |
| `/api/tasks/<id>/events` | GET | SSE-Stream für Live-Fortschritt. |
| `/api/tasks/<id>/cancel` | POST | Migration abbrechen. |

---

## Notion-Datenbank-Schema

Die Datenbank wird beim ersten Lauf automatisch erweitert (fehlende Properties werden via PATCH ergänzt).

| Property | Typ | Inhalt |
|----------|-----|--------|
| **Channel** | `title` | Channel-Anzeigename |
| **Team** | `rich_text` | Team-Anzeigename |
| **ChannelType** | `select` | `standard` / `private` / `shared` |
| **ChannelId** | `rich_text` | Lookup-Key für Idempotenz |
| **TeamId** | `rich_text` | Group-/Team-ID |
| **CreatedDateTime** | `date` | Channel-Erstellungsdatum |
| **LastSync** | `date` | Zeitpunkt der letzten Migration |
| **MessageCount** | `number` | Anzahl Top-Level-Beiträge |
| **WebUrl** | `url` | Link zum Channel in Teams |

---

## Block-Layout pro Message

Pro Top-Level-Beitrag wird **ein Toggle-Block** erstellt, dessen Header die Vorschau enthält:

```
▸ Maria Mustermann · 2024-03-15 13:42 · Hier ist der Sprint-Plan…
  ├─ Hier ist der Sprint-Plan für KW12, bitte bis Freitag…
  ├─ 📎 Sprint_KW12.pdf  (bookmark)
  ├─ 👍 3 (Tom, Lisa, Anna)  ❤️ 1 (Tom)
  ├─ ▸ Tom · 2024-03-15 14:01 · Sieht gut aus, Frage zu Aufgabe 3…
  │    └─ Sieht gut aus, Frage zu Aufgabe 3: ist die Akzeptanz-…
  └─ ▸ Lisa · 2024-03-15 14:30 · Ich habe die User-Stories bereits…
       └─ Ich habe die User-Stories bereits angelegt, siehe Link.
```

- Header-Format: `**Author** · _Datum_ · Vorschau` (max. 60 Zeichen).
- Replies werden chronologisch (oldest first) als verschachtelte Toggles unter dem Parent abgelegt.
- Reactions: kursive Zeile am Ende, gruppiert nach Reaction-Typ.
- @Mentions: Rich-Text mit blauer Farbe + `mailto:`-Link.
- Inline-Bilder (`hostedContents`): werden heruntergeladen und über die Notion-File-Upload-API als echte Image-Blocks eingebunden.
- Datei-Anhänge mit SharePoint-/OneDrive-URL: bleiben Bookmark-Blocks (kein Re-Upload).

---

## Idempotenz / Rebuild

Jeder Migrations-Lauf wirkt **destruktiv auf die Channel-Page**: alle bestehenden Blöcke werden vor dem Neuaufbau gelöscht (`delete_all_block_children`). Vorteile:
- Sauberer Endzustand auch nach nachträglichen Bearbeitungen/Löschungen in Teams.
- Keine Duplikate, keine Drift.

Trade-Off: Jeder Lauf lädt alle Inline-Bilder erneut hoch (ResourceHandler-Cache greift nur **innerhalb** eines Laufs). Für große Channels ist dies merklich; ein zukünftiges `--since`-Flag (inkrementell) ist im Future-Work dokumentiert.

Die Notion-Page-ID wird im StateManager unter dem Schlüssel `teams:{team_id}:{channel_id}` gespeichert, damit die Page bei Folgeläufen ohne Database-Query wiedergefunden wird.

---

## Bekannte Limitierungen

- **Notion-Page-Größenlimit ~100 MB** und Block-Tree-Tiefe: Channels mit >10k Messages oder vielen großen Inline-Bildern können an Grenzen stoßen. Lösung (Future): `--split-by month/quarter/year`.
- **`$expand=replies`-Truncation**: Bei sehr langen Reply-Threads kann Microsoft Replies inline abschneiden. Aktuell kein automatischer Fallback — wenn Lücken auftreten, ist `list_channel_message_replies` als Folgemethode vorgesehen.
- **Toggle-Children-Limit**: Notion erlaubt maximal 100 children per `create_page`-Call. Lange Body+Reply-Kombinationen werden auf 99 begrenzt + Warnhinweis-Block.
- **Application-Modus nicht unterstützt** — Microsoft empfiehlt Pay-per-API ausschließlich mit Delegated-Tokens.
- **1:1-/Group-Chats** (`/me/chats`) sind aktuell nicht abgedeckt; technisch sehr ähnlich.
- **Notion-User-Mentions**: @Mentions sind als Markup (blau + mailto-Link) abgebildet, nicht als echte Workspace-User-Mentions (würde ein E-Mail→Notion-User-Mapping erfordern).

---

## Fehlerbehandlung

| Fehler | Ursache | Lösung |
|--------|---------|--------|
| `403 Forbidden — Failed to get license information` | User hat keine M365-Lizenz mit Teams | Lizenz zuweisen ODER mit User-Account mit Lizenz einloggen |
| `403 Forbidden` ohne Lizenz-Hinweis | Scope nicht zugestimmt oder kein Team-Mitglied | `/login?reconsent=1` aufrufen; ggf. User dem Team hinzufügen |
| `400 — Query option 'Top' is not allowed` | sollte nicht mehr auftreten (Fix in 0.10.0) | – |
| `429 Too Many Requests` | Rate Limit | Retry erfolgt automatisch (`_make_request` mit Backoff) |
| Notion `validation_error` zu rich_text | >2000 Zeichen | Builder splittet bereits; ggf. Block manuell prüfen |

---

## Microsoft Graph Endpoints

| Endpoint | Beschreibung | Voraussetzung |
|----------|--------------|---------------|
| `GET /me/joinedTeams` | Teams des Users | M365-Lizenz beim eingeloggten User |
| `GET /teams/{id}` | Team-Details | M365-Lizenz |
| `GET /teams/{id}/channels` | Channels eines Teams | M365-Lizenz |
| `GET /teams/{id}/channels/{cid}/messages?$expand=replies` | Top-Level-Messages mit Replies | M365-Lizenz mit Teams |
| `GET /teams/{id}/channels/{cid}/messages/{mid}/replies` | Replies-Fallback | M365-Lizenz mit Teams |
| `GET /teams/{id}/channels/{cid}/messages/{mid}/hostedContents/{hid}/$value` | Inline-Bild-Bytes | M365-Lizenz mit Teams |

Pagination: alle Endpoints unterstützen `@odata.nextLink`. Für `messages` wird zusätzlich der HTTP-Header `Prefer: include-unknown-enum-members` gesetzt, um etwaige neue Enum-Werte von Microsoft tolerant zu behandeln.
