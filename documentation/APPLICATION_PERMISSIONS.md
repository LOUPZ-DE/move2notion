# Application Permissions (Client Credentials Flow)

Anleitung zur Einrichtung von Application Permissions für die automatisierte Migration ohne Benutzer-Login.

---

## Überblick

| Aspekt | Delegated Permissions | Application Permissions |
|--------|----------------------|------------------------|
| **Authentifizierung** | Benutzer meldet sich an | App authentifiziert sich selbst |
| **Zugriff** | Nur Daten des Benutzers | Alle Daten im Tenant |
| **Erforderlich** | Benutzer-Consent | Admin Consent |
| **Geeignet für** | Interaktive Nutzung | Automatisierung, CI/CD, Cronjobs |
| **User-Login** | Ja | Nein |

---

## Azure AD Setup

### 1. App Registration öffnen

1. [Azure Portal](https://portal.azure.com) → **App registrations**
2. Vorhandene App-Registrierung auswählen (oder neue erstellen)

### 2. Application Permissions hinzufügen

1. **API permissions** → **Add a permission** → **Microsoft Graph**
2. **Application permissions** auswählen (nicht Delegated!)
3. Folgende Permissions hinzufügen:

| Permission | Beschreibung | Benötigt für |
|-----------|--------------|--------------|
| `Notes.Read.All` | OneNote-Notebooks lesen | OneNote-Migration |
| `Sites.Read.All` | SharePoint-Sites lesen | Site-ID-Auflösung |
| `Tasks.Read.All` | Planner-Tasks lesen | Planner-Migration |
| `Group.Read.All` | Gruppen und Mitglieder lesen | Planner-Zuweisungen |
| `User.Read.All` | Benutzerprofile lesen | People-Mapping |

> **Teams-Migration im Application-Modus**: Aktuell **nicht unterstützt**. Microsoft hat den Application-Only-Zugriff auf `/teams/{}/channels/{}/messages` 2022 als „Protected API" mit Pay-per-API-Modell deklariert (Modell A = Evaluation 500 Requests/Monat, Modell B = Volume Billing via Azure Subscription). Im **Delegated**-Modus (User-Login) ist diese Bezahlpflicht nicht relevant — dort gilt nur die normale M365-User-Lizenz, daher läuft die Teams-Migration ausschließlich Delegated.

### 3. Admin Consent erteilen

1. **API permissions** → **Grant admin consent for [Tenant-Name]**
2. Button klicken und mit Admin-Konto bestätigen
3. Status aller Permissions muss auf **Granted** wechseln

> **Wichtig:** Nur ein Azure AD-Administrator kann Admin Consent erteilen.

### 4. Client Secret erstellen

1. **Certificates & secrets** → **New client secret**
2. Beschreibung und Ablaufdatum festlegen
3. **Value** kopieren (wird nur einmal angezeigt!)
4. In `.env` als `MS_CLIENT_SECRET` eintragen

---

## Konfiguration

### `.env`

```bash
# Application-Modus aktivieren
MS_AUTH_MODE=application

# WICHTIG: Spezifische Tenant-ID erforderlich (nicht "common" oder "consumers")
MS_TENANT_ID=ihre-tenant-id

# Client Secret aus Azure AD
MS_CLIENT_SECRET=ihr-client-secret

# Für Web-GUI: Admin-Passwort setzen
ADMIN_PASSWORD=sicheres-passwort
```

### CLI-Nutzung

Keine Änderung am CLI-Aufruf — der Auth-Modus wird automatisch aus `.env` gelesen:

```bash
# OneNote (kein Login-Prompt mehr)
python -m tools.onenote_migration.cli \
  --site-url "https://tenant.sharepoint.com/sites/Site" \
  --notebook "Notizbuch" \
  --database-id "NOTION_DATABASE_ID"

# Planner (kein Login-Prompt mehr)
python -m tools.planner_migration.cli \
  --plan-id "PLAN_ID" \
  --database "NOTION_DATABASE_ID"
```

### Web-GUI

Bei `MS_AUTH_MODE=application` wird der Microsoft-Login übersprungen. Stattdessen wird ein Passwort-Formular angezeigt (geschützt durch `ADMIN_PASSWORD`).

---

## Technische Details

### Scope-Verhalten

Client Credentials Flow nutzt immer den `.default`-Scope:
```
https://graph.microsoft.com/.default
```

Die in `MS_GRAPH_SCOPES` konfigurierten Scopes werden im Application-Modus **ignoriert**. Stattdessen gelten alle in Azure AD erteilten Application Permissions.

### OneNote-API-Einschränkung (seit März 2025)

Microsoft unterstützt seit dem 31. März 2025 **keine App-Only-Tokens mehr für OneNote-APIs**. Das bedeutet:

- **OneNote-Migration** (`tools/onenote_migration/`) funktioniert im Application-Modus **nicht**
- **Overview-Tool**: OneNote-Notebooks werden im Application-Modus übersprungen (nur Planner-Pläne werden angezeigt)
- **Planner-Migration** (`tools/planner_migration/`) funktioniert weiterhin uneingeschränkt

**Lösung:** Für OneNote-bezogene Funktionen den Delegated-Modus verwenden (`MS_AUTH_MODE=delegated`).

Referenz: [Microsoft Graph OneNote API — App-Only Token Deprecation](https://learn.microsoft.com/en-us/graph/auth-v2-user)

### Token-Caching

MSAL cached Client Credentials Tokens automatisch (ca. 1 Stunde gültig). Es wird kein lokaler Token-Cache benötigt.

### Tenant-ID Pflicht

Client Credentials Flow erfordert eine **spezifische Tenant-ID**. Die Werte `common` und `consumers` funktionieren nicht, da kein Benutzerkontext vorhanden ist, um den Tenant zu bestimmen.

---

## Sicherheitshinweise

1. **Breiter Zugriff**: Application Permissions gewähren Zugriff auf **alle** Daten im Tenant (nicht nur die eines Benutzers). Nur verwenden, wenn dies gewünscht ist.

2. **Client Secret schützen**: Das Secret niemals in Git committen. `.env` ist bereits in `.gitignore`.

3. **Admin-Passwort**: Bei Web-GUI-Nutzung ein starkes Passwort für `ADMIN_PASSWORD` verwenden.

4. **Principle of Least Privilege**: Nur die tatsächlich benötigten Permissions erteilen. Wenn nur OneNote migriert wird, `Tasks.Read.All` weglassen.

5. **Secret-Rotation**: Client Secrets haben ein Ablaufdatum. Rechtzeitig erneuern.

---

## Delegated-Modus: Gruppenmitgliedschaft

Im Delegated-Modus (`MS_AUTH_MODE=delegated`) sieht der angemeldete Benutzer nur Planner-Pläne und OneNote-Notebooks von Gruppen, in denen er **Mitglied** ist — auch wenn er Global Admin ist.

Um im Delegated-Modus alle Gruppen vollständig zu sehen, muss der Benutzer allen Microsoft 365-Gruppen als Mitglied hinzugefügt werden:

```powershell
# Voraussetzung: Install-Module Microsoft.Graph -Scope CurrentUser
Connect-MgGraph -Scopes "GroupMember.ReadWrite.All", "User.Read.All", "Group.Read.All"

$user = Get-MgUser -Filter "userPrincipalName eq 'it-admin@example.com'"
$groups = Get-MgGroup -Filter "groupTypes/any(c:c eq 'Unified')" -All

foreach ($group in $groups) {
    try {
        New-MgGroupMember -GroupId $group.Id -DirectoryObjectId $user.Id -ErrorAction Stop
        Write-Host "[+] $($group.DisplayName)"
    } catch {
        if ($_.Exception.Message -like '*already exist*') {
            Write-Host "[=] $($group.DisplayName) (bereits Mitglied)"
        }
    }
}
```

> Nach dem Hinzufügen kann es einige Minuten dauern, bis die Berechtigungen wirksam werden.

---

*Siehe auch: [Web-GUI Dokumentation](WEB_GUI.md) | [Overview Dokumentation](OVERVIEW.md) | [Hauptdokumentation](../README.md)*
