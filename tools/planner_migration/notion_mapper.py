#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Notion-Mapper für Planner-Daten.

Dieses Modul behandelt:
- Verarbeitete Daten in Notion-Properties konvertieren
- Notion-Blöcke für Beschreibung und Checklisten erstellen
- Datenbankschema-Management
"""
import re
from typing import Dict, List, Any, Optional

# Core-Module importieren
from core.notion_client import NotionClient


class NotionMapper:
    """Konvertiert verarbeitete Planner-Daten in Notion-Format."""

    # Basis-Properties für Planner-Datenbanken
    BASE_PROPERTIES = {
        "Name": {"title": {}},
        "Bucket": {"select": {}},
        "Status": {"select": {}},
        "Priorität": {"select": {}},
        "Tags": {"multi_select": {}},
        "Zugewiesen an": {"people": {}},
        "Erstellt von": {"people": {}},
        "Abgeschlossen von": {"people": {}},
        "Beschreibung": {"rich_text": {}},
        "Erstellungsdatum": {"date": {}},
        "Startdatum": {"date": {}},
        "Fälligkeitsdatum": {"date": {}},
        "Abgeschlossen am": {"date": {}},
        "Ist wiederkehrend": {"checkbox": {}},
        "Verspätet": {"checkbox": {}},
        "Vorgangsnummer (Planner)": {"rich_text": {}},
    }

    def __init__(self, notion_client: NotionClient):
        self.notion = notion_client

    def ensure_database_schema(self, database_id: str) -> None:
        """Stellt sicher, dass Datenbank alle erforderlichen Properties hat."""
        try:
            current_db = self.notion.get_database(database_id)
            existing_props = current_db.get("properties", {})

            # Fehlende Properties hinzufügen
            missing_props = {}
            for prop_name, prop_config in self.BASE_PROPERTIES.items():
                if prop_name not in existing_props:
                    missing_props[prop_name] = prop_config

            if missing_props:
                self.notion.update_database(database_id, missing_props)
                print(f"[i] {len(missing_props)} Properties zur Datenbank hinzugefügt")

        except Exception as e:
            print(f"[Warning] Schema-Prüfung fehlgeschlagen: {e}")

    def add_select_options_if_needed(self, database_id: str, property_name: str,
                                  option_names: List[str]) -> None:
        """Fehlende Select-Optionen zur Datenbank hinzufügen."""
        try:
            db = self.notion.get_database(database_id)
            prop = db["properties"].get(property_name)

            if not prop or prop["type"] not in ["select", "multi_select"]:
                return

            existing_options = {opt["name"] for opt in prop.get(prop["type"], {}).get("options", [])}
            new_options = [name for name in option_names if name and name not in existing_options]

            if new_options:
                # Bestehende Optionen + neue Optionen
                all_options = prop.get(prop["type"], {}).get("options", []) + [{"name": name} for name in new_options]
                self.notion.update_database(database_id, {
                    property_name: {prop["type"]: {"options": all_options}}
                })
                print(f"[i] {len(new_options)} neue Optionen für '{property_name}' hinzugefügt")

        except Exception as e:
            print(f"[Warning] Option-Update fehlgeschlagen für '{property_name}': {e}")

    def build_properties_for_row(self, row: Dict[str, Any], people_mapper) -> Dict[str, Any]:
        """Notion-Properties für eine Datenzeile erstellen."""
        properties = {
            "Name": {"title": [{"type": "text", "text": {"content": str(row.get("Name", ""))}}]}
        }

        # Select-Properties
        for prop_name in ["Bucket", "Status", "Priorität"]:
            value = row.get(prop_name)
            if value:
                properties[prop_name] = {"select": {"name": str(value)}}

        # Multi-Select (Tags)
        tags_value = row.get("Tags")
        if tags_value:
            tag_names = [tag.strip() for tag in str(tags_value).split(",") if tag.strip()]
            if tag_names:
                properties["Tags"] = {"multi_select": [{"name": name} for name in tag_names]}

        # Datums-Properties
        for prop_name in ["Erstellungsdatum", "Startdatum", "Fälligkeitsdatum", "Abgeschlossen am"]:
            value = row.get(prop_name)
            if value:
                properties[prop_name] = {"date": {"start": str(value)}}

        # Checkbox-Properties
        for prop_name in ["Ist wiederkehrend", "Verspätet"]:
            value = row.get(prop_name)
            if value:
                # Deutsche Boolean-Werte parsen
                is_checked = str(value).lower() in ["ja", "true", "1", "x", "yes"]
                properties[prop_name] = {"checkbox": is_checked}

        # Rich-Text-Properties
        for prop_name in ["Beschreibung", "Vorgangsnummer (Planner)"]:
            value = row.get(prop_name)
            if value:
                properties[prop_name] = {"rich_text": [{"type": "text", "text": {"content": str(value)}}]}

        # People-Properties (über Mapper)
        if people_mapper:
            for text_prop, people_prop in [
                ("Zugewiesen an (Text)", "Zugewiesen an"),
                ("Erstellt von (Text)", "Erstellt von"),
                ("Abgeschlossen von (Text)", "Abgeschlossen von")
            ]:
                text_value = row.get(text_prop)
                if text_value:
                    user_ids = people_mapper.get_user_ids_for_names(text_value)
                    if user_ids:
                        properties[people_prop] = {"people": [{"id": uid} for uid in user_ids]}

        return properties

    def build_children_blocks(self, row: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Notion-Blöcke für Beschreibung und Checklisten erstellen."""
        blocks = []

        # Beschreibung als Paragraph
        description = row.get("Beschreibung")
        if description:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": str(description)}}]
                }
            })

        # Checklisten - prüfe zuerst auf strukturierte Daten (aus API)
        checklist_structured = row.get("Checkliste_structured")
        
        if checklist_structured:
            # Strukturierte Checkliste (von API-Mapper) → echte To-Do-Blöcke
            for item in checklist_structured:
                title = item.get("title", "")
                checked = item.get("checked", False)
                if title:  # Nur nicht-leere Items
                    blocks.append({
                        "object": "block",
                        "type": "to_do",
                        "to_do": {
                            "rich_text": [{"type": "text", "text": {"content": title}}],
                            "checked": checked
                        }
                    })
        else:
            # Fallback: CSV-basierte Checklisten (alte Logik)
            checklist_raw = row.get("Checkliste_raw")
            checklist_done = row.get("Checkliste_done")

            if checklist_raw or checklist_done:
                # Erledigt/Gesamt-Zähler
                if checklist_done:
                    done_pattern = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")
                    match = done_pattern.match(str(checklist_done))
                    if match:
                        blocks.append({
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [{"type": "text", "text": {"content": f"Erledigt/Gesamt: {match.group(1)}/{match.group(2)}"}}]
                            }
                        })

                # Offene Checklistenpunkte als To-Do-Blöcke
                if checklist_raw:
                    checklist_items = [item.strip() for item in str(checklist_raw).split(";") if item.strip()]
                    for item in checklist_items:
                        blocks.append({
                            "object": "block",
                            "type": "to_do",
                            "to_do": {
                                "rich_text": [{"type": "text", "text": {"content": item}}],
                                "checked": False
                            }
                        })

        return blocks

    def find_existing_page(self, database_id: str, unique_property: str, unique_value: str) -> Optional[str]:
        """Bestehende Seite anhand einer eindeutigen Property finden."""
        if not unique_value:
            return None

        return self.notion.find_page_by_property(database_id, unique_property, unique_value)

    def prepare_database_for_import(self, database_id: str, processed_data: List[Dict[str, Any]]) -> None:
        """Datenbank auf Import vorbereiten (Schema + Optionen)."""
        print("[i] Bereite Datenbank vor...")

        # 1. Schema sicherstellen
        self.ensure_database_schema(database_id)

        # 2. Select-Optionen sammeln und hinzufügen
        option_mappings = {
            "Bucket": set(),
            "Status": set(),
            "Priorität": set(),
            "Tags": set()
        }

        for row in processed_data:
            for prop_name in option_mappings.keys():
                value = row.get(prop_name)
                if value:
                    if prop_name == "Tags":
                        # Tags aufsplitten
                        tags = [tag.strip() for tag in str(value).split(",") if tag.strip()]
                        option_mappings[prop_name].update(tags)
                    else:
                        option_mappings[prop_name].add(str(value))

        # Optionen hinzufügen
        for prop_name, options in option_mappings.items():
            if options:
                option_list = sorted(list(options))
                self.add_select_options_if_needed(database_id, prop_name, option_list)


def create_notion_mapper(notion_client: NotionClient) -> NotionMapper:
    """Factory-Funktion für NotionMapper."""
    return NotionMapper(notion_client)
