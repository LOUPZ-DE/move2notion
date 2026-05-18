#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Notion-Content-Mapper fuer Teams-Channel-Migration.

Verantwortlich fuer:
- Notion-Datenbank-Schema (Properties anlegen/erweitern).
- Find-or-Create einer Notion-Page pro Channel.
- Rebuild des Page-Bodys: alle Bloecke loeschen, dann chronologischer
  Chat-Verlauf aus Toggle-Bloecken neu schreiben.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.notion_client import NotionClient
from core.ms_graph_client import MSGraphClient
from core.state_manager import StateManager, generate_channel_key

from .teams_api_mapper import Channel, Message, sort_messages_chronologically
from .message_block_builder import build_message_toggle
from .teams_resource_handler import TeamsResourceHandler


class TeamsContentMapper:
    """Orchestriert die Migration eines Channels in eine Notion-Page.

    Datenbank-Schema (BASE_PROPERTIES) wird beim ersten Lauf automatisch
    angelegt; fehlende Properties werden via PATCH ergaenzt.
    """

    BASE_PROPERTIES: Dict[str, Any] = {
        "Channel": {"title": {}},
        "Team": {"rich_text": {}},
        "ChannelType": {"select": {"options": [
            {"name": "standard"},
            {"name": "private"},
            {"name": "shared"},
        ]}},
        "ChannelId": {"rich_text": {}},
        "TeamId": {"rich_text": {}},
        "CreatedDateTime": {"date": {}},
        "LastSync": {"date": {}},
        "MessageCount": {"number": {"format": "number"}},
        "WebUrl": {"url": {}},
    }

    def __init__(
        self,
        notion_client: NotionClient,
        ms_graph_client: MSGraphClient,
        team_id: str,
        team_display_name: str,
        state_manager: Optional[StateManager] = None,
        progress_callback=None,
    ):
        self.notion = notion_client
        self.ms_graph = ms_graph_client
        self.team_id = team_id
        self.team_display_name = team_display_name
        self.state = state_manager
        self.progress = progress_callback or (lambda msg: None)
        self.resource_handler = TeamsResourceHandler(notion_client, ms_graph_client, team_id)

    # ------------------------------------------------------------------
    # Schema-Management

    def ensure_database_schema(self, database_id: str) -> None:
        """Stellt sicher, dass die Notion-DB alle erforderlichen Properties hat."""
        try:
            current = self.notion.get_database(database_id)
            existing = current.get("properties", {})
            missing = {
                name: cfg for name, cfg in self.BASE_PROPERTIES.items()
                if name not in existing
            }
            if missing:
                self.notion.update_database(database_id, missing)
                self.progress(f"[i] {len(missing)} Properties zur Datenbank hinzugefuegt")
        except Exception as e:
            self.progress(f"[Warning] Schema-Pruefung fehlgeschlagen: {e}")

    # ------------------------------------------------------------------
    # Migration einer Channel-Page

    def migrate_channel(
        self,
        channel: Channel,
        messages: List[Message],
        database_id: str,
    ) -> Dict[str, Any]:
        """Komplette Migration eines Channels.

        Schritte:
            1. Find-or-Create der Notion-Page anhand der ChannelId-Property.
            2. Rebuild: alle bestehenden Bloecke entfernen.
            3. Header-Block + chronologische Toggle-Bloecke pro Message anhaengen.
            4. State (notion_id) merken fuer Wiederfindung beim naechsten Lauf.

        Returns:
            Dict mit `notion_page_id`, `message_count`, `failed_blocks`.
        """
        # Channel-Kontext fuer hostedContents-URL-Aufloesung setzen
        self.resource_handler.set_channel_context(channel.id)
        self.notion.pin_token()
        try:
            page_id = self._find_or_create_channel_page(database_id, channel, len(messages))
            self.progress(
                f"[📂] Channel '{channel.display_name}' → Notion-Page {page_id}"
            )

            removed = self.notion.delete_all_block_children(page_id)
            if removed:
                self.progress(f"[🗑] {removed} bestehende Bloecke entfernt (Rebuild)")

            sorted_msgs = sort_messages_chronologically(messages)
            blocks = self._build_channel_blocks(channel, sorted_msgs)

            failed_blocks = 0
            if blocks:
                result = self.notion.append_blocks(page_id, blocks)
                failed_blocks = int(result.get("_failed_blocks", 0) or 0)

            # Properties (LastSync + MessageCount) updaten
            self._update_sync_properties(page_id, len(messages))

            # State persistieren (nur fuer Wiederfindung der Page-ID)
            if self.state:
                key = generate_channel_key(self.team_id, channel.id)
                self.state.set_page_state(key, page_id, checksum=str(len(messages)))

            return {
                "notion_page_id": page_id,
                "message_count": len(messages),
                "failed_blocks": failed_blocks,
            }
        finally:
            self.notion.unpin_token()

    # ------------------------------------------------------------------
    # Internals

    def _find_or_create_channel_page(
        self, database_id: str, channel: Channel, message_count: int
    ) -> str:
        """Existierende Channel-Page anhand ChannelId finden, sonst neu anlegen."""
        # Schritt 1: State-Lookup (vermeidet API-Call wenn bekannt)
        if self.state:
            key = generate_channel_key(self.team_id, channel.id)
            state_entry = self.state.get_page_state(key)
            if state_entry and state_entry.get("notion_id"):
                return state_entry["notion_id"]

        # Schritt 2: Suche per ChannelId-Property
        try:
            existing = self.notion.find_page_by_property(database_id, "ChannelId", channel.id)
            if existing:
                return existing
        except Exception:
            pass

        # Schritt 3: Page neu anlegen
        properties = self._build_page_properties(channel, message_count)
        return self.notion.create_page(database_id, properties)

    def _build_page_properties(self, channel: Channel, message_count: int) -> Dict[str, Any]:
        """Notion-Properties fuer eine Channel-Page erzeugen."""
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        properties: Dict[str, Any] = {
            "Channel": {"title": [{"type": "text", "text": {"content": channel.display_name or "(unbenannt)"}}]},
            "Team": {"rich_text": [{"type": "text", "text": {"content": self.team_display_name or ""}}]},
            "ChannelId": {"rich_text": [{"type": "text", "text": {"content": channel.id}}]},
            "TeamId": {"rich_text": [{"type": "text", "text": {"content": self.team_id}}]},
            "ChannelType": {"select": {"name": channel.channel_type or "standard"}},
            "MessageCount": {"number": message_count},
            "LastSync": {"date": {"start": now_iso}},
        }
        if channel.created_dt:
            properties["CreatedDateTime"] = {"date": {"start": channel.created_dt}}
        if channel.web_url:
            properties["WebUrl"] = {"url": channel.web_url}
        return properties

    def _update_sync_properties(self, page_id: str, message_count: int) -> None:
        """LastSync + MessageCount nach Rebuild aktualisieren."""
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        try:
            self.notion.update_page(page_id, {
                "LastSync": {"date": {"start": now_iso}},
                "MessageCount": {"number": message_count},
            })
        except Exception as e:
            self.progress(f"[Warning] Konnte Sync-Properties nicht aktualisieren: {e}")

    def _build_channel_blocks(
        self, channel: Channel, messages: List[Message]
    ) -> List[Dict[str, Any]]:
        """Vollstaendige Block-Liste fuer den Channel-Body."""
        blocks: List[Dict[str, Any]] = []

        # Header-Block: Channel-Beschreibung + Statistik
        intro_lines: List[str] = []
        if channel.description:
            intro_lines.append(channel.description)
        intro_lines.append(
            f"{len(messages)} Top-Level-Beitraege · "
            f"Typ: {channel.channel_type} · "
            f"Team: {self.team_display_name}"
        )
        blocks.append({
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": "  ".join(intro_lines)[:1900]},
                    "annotations": {"italic": True, "color": "gray"},
                }],
                "icon": {"type": "emoji", "emoji": "💬"},
            },
        })
        blocks.append({"object": "block", "type": "divider", "divider": {}})

        # Chronologisch eine Toggle pro Top-Level-Message
        system_skipped = 0
        for msg in messages:
            # System-Messages (Channel-Created, Member-Added, Channel-Renamed,
            # Tab-Added etc.) sind reine Audit-Events ohne Inhalt und werden
            # konsequent uebersprungen.
            if msg.message_type and msg.message_type != "message":
                system_skipped += 1
                continue
            try:
                block = build_message_toggle(msg, self.resource_handler)
                if block is not None:
                    blocks.append(block)
            except Exception as e:
                self.progress(f"[⚠] Message {msg.id} konnte nicht konvertiert werden: {e}")
            # Mini-Pause zwischen Inline-Image-Uploads, falls welche im Toggle waren
            if msg.hosted_contents:
                time.sleep(0.05)

        if system_skipped:
            self.progress(f"[i] {system_skipped} System-Beitraege uebersprungen "
                          f"(Channel-Events, Tab-Aenderungen, etc.)")
        return blocks
