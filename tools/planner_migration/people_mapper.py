#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Personen-Mapping für Planner-zu-Notion Migration.

Dieses Modul behandelt:
- CSV-Mapping-Datei einlesen (Name_in_CSV → Notion_Email)
- Notion-Benutzer über API abrufen
- Mapping zwischen CSV-Namen und Notion-User-IDs erstellen
"""
from pathlib import Path
from typing import Dict, List, Optional

# Core-Module importieren
from core.utils import read_csv_file, split_multi_values
from core.notion_client import NotionClient


class PeopleMapper:
    """Verwaltet Personen-Mapping zwischen CSV und Notion."""

    def __init__(self, mapping_csv_path: Optional[str] = None):
        self.mapping_csv_path = Path(mapping_csv_path) if mapping_csv_path else None
        self.notion: Optional[NotionClient] = None

        # Mapping-Daten
        self.name_to_email: Dict[str, str] = {}
        self.email_to_user_id: Dict[str, str] = {}
        self.name_to_user_id: Dict[str, str] = {}

    def initialize_notion_client(self, notion_client: NotionClient):
        """Notion-Client setzen."""
        self.notion = notion_client

    def load_mapping_csv(self) -> None:
        """Mapping-CSV laden und Name-zu-Email-Mapping erstellen."""
        if not self.mapping_csv_path or not self.mapping_csv_path.exists():
            return

        mapping_data = read_csv_file(self.mapping_csv_path, delimiter=",")

        for row in mapping_data:
            name = row.get("Name_in_CSV", "").strip()
            email = row.get("Notion_Email", "").strip()

            if name and email:
                self.name_to_email[name] = email

    def fetch_notion_users(self) -> None:
        """Notion-Benutzer abrufen und Email-zu-User-ID-Mapping erstellen."""
        if not self.notion:
            raise RuntimeError("Notion-Client nicht initialisiert")

        try:
            # Notion-Benutzer abrufen
            users = self.notion.list_users()
            
            for user in users:
                user_id = user.get("id")
                user_type = user.get("type")
                
                # Nur echte Personen, keine Bots
                if user_type != "person":
                    continue
                
                # E-Mail aus person-Objekt extrahieren
                person = user.get("person", {})
                email = person.get("email")
                
                if email and user_id:
                    self.email_to_user_id[email.lower()] = user_id
            
            print(f"[i] {len(self.email_to_user_id)} Notion-Benutzer gefunden")

        except Exception as e:
            print(f"[Warning] Notion-Benutzer konnten nicht abgerufen werden: {e}")

    def build_mappings(self) -> None:
        """Vollständiges Mapping aufbauen."""
        # 1. CSV-Mapping laden
        self.load_mapping_csv()

        # 2. Notion-Benutzer abrufen
        self.fetch_notion_users()

        # 3. Name-zu-User-ID-Mapping erstellen (case-insensitive E-Mail-Matching)
        for name, email in self.name_to_email.items():
            email_lower = email.lower()
            if email_lower in self.email_to_user_id:
                self.name_to_user_id[name] = self.email_to_user_id[email_lower]

    def get_user_id(self, name: str) -> Optional[str]:
        """User-ID für einen Namen abrufen."""
        return self.name_to_user_id.get(name)

    def get_user_ids_for_names(self, names_text: str) -> List[str]:
        """User-IDs für kommagetrennte Namen abrufen."""
        if not names_text:
            return []

        names = [name.strip() for name in names_text.split(",") if name.strip()]
        user_ids = []

        for name in names:
            user_id = self.get_user_id(name)
            if user_id:
                user_ids.append(user_id)

        return user_ids

    def get_unmapped_names(self) -> List[str]:
        """Namen zurückgeben, die nicht gemappt werden konnten."""
        return [
            name for name in self.name_to_email.keys()
            if name not in self.name_to_user_id
        ]

    def generate_template_csv(self, csv_names: List[str], output_path: Path) -> None:
        """Template-CSV für fehlende Namen generieren."""
        template_data = []

        for name in csv_names:
            if name not in self.name_to_email:
                template_data.append({
                    "Name_in_CSV": name,
                    "Notion_Email": ""
                })

        if template_data:
            import pandas as pd
            df = pd.DataFrame(template_data)
            df.to_csv(output_path, index=False, encoding="utf-8")
            print(f"[i] Template-CSV erstellt: {output_path}")


def create_people_mapper(mapping_csv_path: Optional[str] = None) -> PeopleMapper:
    """Factory-Funktion für PeopleMapper."""
    return PeopleMapper(mapping_csv_path)
