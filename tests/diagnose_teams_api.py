#!/usr/bin/env python3
"""
Diagnose-Skript: Prueft Microsoft Graph Teams-API-Zugriff vor der Migration.

Ablauf:
    1. `list_joined_teams()` → ein Team auswaehlen (per CLI-Arg oder erstes).
    2. `list_team_channels(team_id)` → alle Channels.
    3. `list_channel_messages(team_id, channel_id, $top=5, $expand=replies)`
       fuer den ersten Channel als Smoke-Test.

Validiert insbesondere die **User-M365-Lizenz** fuer Teams-Messages — bei 403
gibt das Skript einen Hinweis aus, der zwischen User-Lizenz, fehlendem Consent
und Membership-Problemen unterscheidet.

Braucht nur Microsoft-Login (Delegated). Keine Notion-Calls.

Usage:
    # Erstes verfuegbares Team verwenden
    .venv/bin/python3 tests/diagnose_teams_api.py

    # Bestimmtes Team
    .venv/bin/python3 tests/diagnose_teams_api.py --team-id <uuid>
    .venv/bin/python3 tests/diagnose_teams_api.py --team-name "Projektteam Alpha"

    # JSON statt formatierter Ausgabe
    .venv/bin/python3 tests/diagnose_teams_api.py --json
"""
import argparse
import json as json_lib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.auth import auth_manager
from core.ms_graph_client import MSGraphClient, MSGraphAPIError


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Diagnose-Skript fuer Microsoft Teams Graph API"
    )
    grp = p.add_mutually_exclusive_group()
    grp.add_argument("--team-id", help="Team-ID (UUID)")
    grp.add_argument("--team-name", help="Team-Anzeigename (exakt)")
    p.add_argument("--channel-id", help="Optional: Bestimmten Channel testen")
    p.add_argument("--top", type=int, default=5, help="Anzahl Messages im Smoke-Test (default 5)")
    p.add_argument("--json", action="store_true", help="JSON-Ausgabe")
    return p.parse_args()


def select_team(client: MSGraphClient, args) -> dict:
    teams = client.list_joined_teams()
    if not teams:
        print("[✘] Keine Teams gefunden — User ist in keinem Team Mitglied.")
        sys.exit(2)

    if args.team_id:
        match = next((t for t in teams if t.get("id") == args.team_id), None)
        if not match:
            print(f"[✘] Team {args.team_id} nicht in /me/joinedTeams.")
            sys.exit(2)
        return match
    if args.team_name:
        match = next(
            (t for t in teams if (t.get("displayName") or "").lower() == args.team_name.lower()),
            None,
        )
        if not match:
            print(f"[✘] Team '{args.team_name}' nicht gefunden.")
            sys.exit(2)
        return match
    return teams[0]


def main() -> int:
    args = parse_args()

    auth_manager.initialize(mode="cli")
    client = MSGraphClient()

    summary = {
        "auth_mode": auth_manager.auth_mode,
        "license_ok": False,
        "team": None,
        "channels": [],
        "smoke_test": None,
    }

    # 1. Teams listen
    print("[1/3] Liste Teams (/me/joinedTeams)...")
    team = select_team(client, args)
    summary["team"] = {
        "id": team.get("id"),
        "displayName": team.get("displayName"),
    }
    print(f"      → {team.get('displayName')}  (ID: {team.get('id')})")

    # 2. Channels listen
    print("[2/3] Liste Channels...")
    try:
        raw_channels = client.list_team_channels(team["id"])
    except MSGraphAPIError as e:
        print(f"[✘] Channels konnten nicht geladen werden: {e}")
        if args.json:
            print(json_lib.dumps(summary, indent=2, ensure_ascii=False))
        return 2

    channels = [
        {
            "id": c.get("id"),
            "displayName": c.get("displayName"),
            "membershipType": c.get("membershipType", "standard"),
        }
        for c in raw_channels
    ]
    summary["channels"] = channels
    print(f"      → {len(channels)} Channel(s):")
    for c in channels:
        print(f"        - {c['displayName']:40s} {c['membershipType']:8s} {c['id']}")

    # 3. Messages-Smoke-Test
    smoke_channel_id = args.channel_id
    if not smoke_channel_id and channels:
        smoke_channel_id = channels[0]["id"]
    if not smoke_channel_id:
        print("[!] Kein Channel verfuegbar — Smoke-Test uebersprungen")
        return 0

    print(f"[3/3] Smoke-Test: Lade {args.top} Messages aus Channel {smoke_channel_id}...")
    print("      (validiert User-M365-Lizenz + Consent)")

    try:
        # Direkter Aufruf, damit wir Top steuern koennen
        endpoint = (
            f"/teams/{team['id']}/channels/{smoke_channel_id}/messages"
            f"?$top={args.top}&$expand=replies"
        )
        result = client._make_request(
            "GET", endpoint,
            extra_headers=client._TEAMS_MESSAGES_HEADERS,
        )
        msgs = result.get("value", []) or []
        summary["license_ok"] = True
        summary["smoke_test"] = {
            "channel_id": smoke_channel_id,
            "messages_loaded": len(msgs),
            "first_message_keys": list(msgs[0].keys()) if msgs else [],
        }
        print(f"      ✓ {len(msgs)} Message(s) geladen — User-Lizenz und Consent OK")
        if msgs:
            first = msgs[0]
            sender = (first.get("from") or {}).get("user") or {}
            print(f"      → Beispiel-Beitrag von '{sender.get('displayName', '?')}': "
                  f"{(first.get('body') or {}).get('content', '')[:80]!r}")
    except MSGraphAPIError as e:
        msg = str(e)
        low = msg.lower()
        if "license information for the user" in low or "office365 license" in low:
            print("[✘] 403 — Eingeloggter User hat keine M365-Lizenz mit Teams.")
            print()
            print("      Loesung A: Account im M365 Admin Center eine Lizenz zuweisen")
            print("                 (z. B. Microsoft 365 Business Basic).")
            print("      Loesung B: Mit einem normalen User-Account einloggen, der")
            print("                 bereits eine Lizenz hat.")
        elif "403" in msg and "channelmessage" in low:
            print("[✘] 403 — 'ChannelMessage.Read.All' wurde nicht consented.")
            print("      Loesung: 'rm ~/.ms_notion_migration_token_cache.bin'"
                  " und Diagnose erneut starten (Consent-Screen erscheint).")
        elif "403" in msg:
            print(f"[✘] 403/Forbidden — User evtl. kein Mitglied dieses Channels?")
            print(f"      Original-Fehler: {e}")
        else:
            print(f"[✘] Smoke-Test fehlgeschlagen: {e}")
        summary["license_ok"] = False
        if args.json:
            print(json_lib.dumps(summary, indent=2, ensure_ascii=False))
        return 1

    if args.json:
        print(json_lib.dumps(summary, indent=2, ensure_ascii=False))

    print()
    print("=== Ergebnis ===")
    print(f"  Auth-Modus:           {summary['auth_mode']}")
    print(f"  Teams:                OK")
    print(f"  Channels:             OK ({len(channels)})")
    print(f"  User-Lizenz/Consent:  {'OK' if summary['license_ok'] else 'FEHLT'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
