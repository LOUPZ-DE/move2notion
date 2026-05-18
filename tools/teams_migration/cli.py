#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI-Interface fuer Teams-Channel-Migration.

Beispiele:

    # Alle Channels eines Teams migrieren:
    python -m tools.teams_migration.cli \
        --team-id 11111111-2222-3333-4444-555555555555 \
        --database-id <notion-db-id>

    # Nur einen bestimmten Channel:
    python -m tools.teams_migration.cli \
        --team-id <id> \
        --channel-id <channel-id> \
        --database-id <db-id>

    # Team via Anzeigename suchen (delegated, exakte Uebereinstimmung):
    python -m tools.teams_migration.cli \
        --team-name "Projektteam Alpha" \
        --database-id <db-id>
"""
from __future__ import annotations

import argparse
import sys
import warnings
from typing import List, Optional

# Unterdruecke urllib3 NotOpenSSLWarning
warnings.filterwarnings("ignore", category=Warning, module="urllib3")

from core.auth import auth_manager, AuthConfig
from core.notion_client import NotionClient
from core.ms_graph_client import MSGraphClient, MSGraphAPIError
from core.state_manager import StateManager

from .content_mapper import TeamsContentMapper
from .teams_api_mapper import (
    map_channel_raw,
    map_message_raw,
    Channel,
)


# ----------------------------------------------------------------------
# Hilfsfunktionen


def _vlog(verbose: bool, msg: str):
    if verbose:
        print(msg)


def _resolve_team(
    ms_client: MSGraphClient, team_id: Optional[str], team_name: Optional[str]
) -> dict:
    """Team-Objekt anhand ID oder Name aufloesen."""
    if team_id:
        try:
            team = ms_client.get_team(team_id)
            return team
        except MSGraphAPIError as e:
            print(f"[✘] Team {team_id} konnte nicht abgerufen werden: {e}")
            sys.exit(2)

    teams = ms_client.list_joined_teams()
    if not teams:
        print("[✘] Keine Teams fuer diesen Account gefunden")
        sys.exit(2)

    if team_name:
        match = next(
            (t for t in teams if (t.get("displayName") or "").lower() == team_name.lower()),
            None,
        )
        if match:
            return match
        print(f"[✘] Team '{team_name}' nicht gefunden. Verfuegbare Teams:")
        for t in teams:
            print(f"    {t.get('displayName')}  ({t.get('id')})")
        sys.exit(2)

    # Interaktive Auswahl, falls keine ID/Name uebergeben
    print("Verfuegbare Teams:")
    for idx, t in enumerate(teams, 1):
        print(f"  {idx:2}. {t.get('displayName')}  ({t.get('id')})")
    raw = input("Team-Nummer: ").strip()
    try:
        return teams[int(raw) - 1]
    except (ValueError, IndexError):
        print("[✘] Ungueltige Auswahl")
        sys.exit(2)


def _filter_channels(
    all_channels: List[Channel], channel_id: Optional[str], channel_filter: Optional[List[str]]
) -> List[Channel]:
    if channel_id:
        match = [c for c in all_channels if c.id == channel_id]
        if not match:
            print(f"[✘] Channel {channel_id} nicht im Team gefunden")
            sys.exit(2)
        return match
    if channel_filter:
        ids = set(channel_filter)
        return [c for c in all_channels if c.id in ids]
    return all_channels


# ----------------------------------------------------------------------
# CLI Hauptklasse


class TeamsMigrationCLI:
    """Kapselt den Migrations-Hauptloop, damit Web-GUI und CLI denselben Pfad nutzen."""

    def __init__(
        self,
        notion_client: NotionClient,
        ms_graph_client: MSGraphClient,
        state_manager: Optional[StateManager] = None,
        verbose: bool = False,
        progress_callback=None,
    ):
        self.notion = notion_client
        self.ms_graph = ms_graph_client
        self.state = state_manager
        self.verbose = verbose
        self.progress = progress_callback or (lambda msg: print(msg) if verbose else None)

    def run(
        self,
        team_id: str,
        team_display_name: str,
        database_id: str,
        channel_ids: Optional[List[str]] = None,
        cancel_check=None,
    ) -> dict:
        """Migrationslauf ausfuehren.

        Args:
            team_id: Team-/Group-ID.
            team_display_name: Anzeige-Name des Teams.
            database_id: Notion-DB-ID (oder URL).
            channel_ids: Optional einzuschliessende Channel-IDs (None = alle).
            cancel_check: Callable, das True zurueckgibt, wenn abgebrochen werden soll.

        Returns:
            Dict mit `channels_migrated`, `total_messages`, `failed_blocks`.
        """
        cancel_check = cancel_check or (lambda: False)
        mapper = TeamsContentMapper(
            self.notion, self.ms_graph, team_id, team_display_name,
            state_manager=self.state, progress_callback=self.progress,
        )

        # Schema sicherstellen (legt fehlende Properties an)
        mapper.ensure_database_schema(database_id)

        # Channels laden
        try:
            raw_channels = self.ms_graph.list_team_channels(team_id)
        except MSGraphAPIError as e:
            self.progress(f"[✘] Channels konnten nicht geladen werden: {e}")
            raise

        all_channels = [map_channel_raw(c) for c in raw_channels]
        channels = _filter_channels(all_channels, None, channel_ids)
        self.progress(
            f"[i] {len(channels)} Channel(s) zu migrieren "
            f"(von insgesamt {len(all_channels)} im Team)"
        )

        total_messages = 0
        total_failed = 0
        for idx, channel in enumerate(channels, 1):
            if cancel_check():
                self.progress("[!] Migration abgebrochen")
                break

            self.progress(f"[➡] [{idx}/{len(channels)}] Channel: {channel.display_name}")
            try:
                raw_messages = self.ms_graph.list_channel_messages(team_id, channel.id)
            except MSGraphAPIError as e:
                msg = str(e)
                if "403" in msg or "license" in msg.lower():
                    self.progress(
                        "[✘] 403/Forbidden — Tenant-Admin muss die Teams Graph API "
                        "Pay-per-API-Lizenz im Microsoft 365 Admin Center aktivieren."
                    )
                self.progress(f"[✘] Messages fuer '{channel.display_name}' fehlgeschlagen: {e}")
                continue

            messages = [map_message_raw(m) for m in raw_messages]

            # Optional: Replies-Truncation-Fallback (Microsoft schneidet $expand=replies bei langen Threads ab)
            for msg in messages:
                # Heuristik: wenn 0 Replies geliefert, aber Body Hinweise enthaelt — sehr konservativ:
                # nur bei verdacht (>0 Replies vorhanden, aber genau 0 zurueckgegeben) erneut laden.
                # Microsoft's $expand=replies liefert in der Praxis bis zu ~1000; selten Trunc.
                pass

            self.progress(
                f"    {len(messages)} Top-Level-Beitraege "
                f"({sum(len(m.replies) for m in messages)} Replies)"
            )

            try:
                result = mapper.migrate_channel(channel, messages, database_id)
            except Exception as e:
                self.progress(f"[✘] Migration fuer '{channel.display_name}' fehlgeschlagen: {e}")
                continue

            total_messages += result.get("message_count", 0)
            total_failed += result.get("failed_blocks", 0)
            self.progress(
                f"    ✓ {result['message_count']} Messages, "
                f"{result['failed_blocks']} fehlgeschlagene Bloecke"
            )

        return {
            "channels_migrated": len(channels),
            "total_messages": total_messages,
            "failed_blocks": total_failed,
        }


# ----------------------------------------------------------------------
# argparse main


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m tools.teams_migration.cli",
        description="Migration von Microsoft Teams Channels nach Notion",
    )
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--team-id", help="Team-/Group-ID (UUID)")
    target.add_argument("--team-name", help="Anzeigename des Teams (exakte Uebereinstimmung)")
    parser.add_argument("--database-id", required=True, help="Notion Datenbank-ID oder Share-URL")
    parser.add_argument(
        "--channel-id",
        action="append",
        help="Optional: Nur diese Channel-ID(s) migrieren. Mehrfach erlaubt.",
    )
    parser.add_argument("--state-path", help="Pfad zur State-Datei (default ~/.onenote2notion/state.json)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Detaillierte Ausgaben")
    parser.add_argument("--dry-run", action="store_true", help="Nur Channel-Liste anzeigen, nicht migrieren")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    # Auth initialisieren (delegated/CLI). Bei MS_AUTH_MODE=application laeuft das
    # ueber MicrosoftAppAuthenticator; Teams-Migration ist dort allerdings derzeit
    # nicht supported (Pay-per-API erfordert Delegated).
    auth_manager.initialize(mode="cli")
    if auth_manager.auth_mode == "application":
        print("[!] Teams-Migration im Application-Modus ist nicht unterstuetzt. "
              "Bitte MS_AUTH_MODE=delegated setzen.")
        return 2

    notion = NotionClient()
    ms_client = MSGraphClient()

    team_obj = _resolve_team(ms_client, args.team_id, args.team_name)
    team_id = team_obj.get("id")
    team_name = team_obj.get("displayName") or "(Team)"
    print(f"[i] Team: {team_name}  (ID: {team_id})")

    if args.dry_run:
        channels = ms_client.list_team_channels(team_id)
        print(f"[i] {len(channels)} Channel(s):")
        for c in channels:
            print(f"    - {c.get('displayName'):40s} {c.get('membershipType','standard'):8s} {c.get('id')}")
        return 0

    state = StateManager(args.state_path) if args.state_path else StateManager()
    state.load_state()

    cli = TeamsMigrationCLI(
        notion_client=notion,
        ms_graph_client=ms_client,
        state_manager=state,
        verbose=args.verbose,
    )
    summary = cli.run(
        team_id=team_id,
        team_display_name=team_name,
        database_id=args.database_id,
        channel_ids=args.channel_id,
    )

    print("\n=== Zusammenfassung ===")
    print(f"  Channels migriert:    {summary['channels_migrated']}")
    print(f"  Messages insgesamt:   {summary['total_messages']}")
    print(f"  Fehlgeschlagene Bl.:  {summary['failed_blocks']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
