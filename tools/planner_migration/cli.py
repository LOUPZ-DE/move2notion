#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI-Interface für Planner-zu-Notion Migration.

Dieses Modul orchestriert die verschiedenen Komponenten der Planner-Migration:
- CSV-Verarbeitung
- Personen-Mapping
- Notion-Datenbank-Operationen
- State Management
"""
import argparse
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

# Core-Module importieren
from core.auth import auth_manager, AuthConfig
from core.notion_client import NotionClient
from core.utils import validate_file_exists


class PlannerMigrationCLI:
    """CLI-Interface für Planner-Migration."""

    def __init__(self):
        self.notion: Optional[NotionClient] = None
        self.args = None

    def parse_arguments(self) -> argparse.Namespace:
        """Kommandozeilenargumente parsen."""
        parser = argparse.ArgumentParser(
            description="Microsoft Planner CSV zu Notion migrieren",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Beispiele:
  # Neue Datenbank erstellen
  python -m tools.planner_migration.cli --csv Aufgaben.csv --parent PAGE_ID --db-title "Projekt Aufgaben"

  # In bestehende Datenbank importieren
  python -m tools.planner_migration.cli --csv Aufgaben.csv --database DB_ID

  # Mit Upsert und Personen-Mapping
  python -m tools.planner_migration.cli --csv Aufgaben.csv --database DB_ID --upsert --people-map mapping.csv
            """
        )

        # Input-Optionen
        parser.add_argument("--csv", required=True, help="Pfad zur Planner-CSV-Datei")

        # Notion-Ziel-Optionen (mutually exclusive)
        target_group = parser.add_mutually_exclusive_group(required=True)
        target_group.add_argument("--parent", help="Notion Page ID (erstellt neue Datenbank)")
        target_group.add_argument("--database", help="Bestehende Notion Datenbank ID")

        parser.add_argument("--db-title", help="Titel für neue Datenbank (mit --parent)")

        # Erweiterte Optionen
        parser.add_argument("--people-map", help="CSV für Personen-Mapping (Name → Notion Email)")
        parser.add_argument("--unique", default="Vorgangsnummer (Planner)",
                          help="Property für Upsert-Identifikation (Standard: Vorgangsnummer)")
        parser.add_argument("--rate", type=float, default=3.0,
                          help="Rate Limit (Requests/Sekunde, Standard: 3.0)")
        parser.add_argument("--dry-run", action="store_true",
                          help="Trockenlauf ohne Notion-Änderungen")

        # Modus-Optionen
        parser.add_argument("--upsert", action="store_true",
                          help="Update bestehender Seiten statt neue erstellen")

        # Debug-Optionen
        parser.add_argument("--verbose", "-v", action="store_true",
                          help="Detaillierte Ausgaben")

        return parser.parse_args()

    def validate_arguments(self, args: argparse.Namespace) -> None:
        """Argumente validieren."""
        # CSV-Datei prüfen
        try:
            validate_file_exists(args.csv)
        except FileNotFoundError as e:
            print(f"[❌] CSV-Datei nicht gefunden: {e}")
            sys.exit(1)

        # Bei neuer Datenbank: db-title erforderlich
        if args.parent and not args.db_title:
            print("[❌] --db-title ist erforderlich bei Verwendung von --parent")
            sys.exit(1)

        # Personen-Mapping-Datei prüfen falls angegeben
        if args.people_map:
            try:
                validate_file_exists(args.people_map)
            except FileNotFoundError as e:
                print(f"[❌] Personen-Mapping-Datei nicht gefunden: {e}")
                sys.exit(1)

    def initialize_services(self) -> None:
        """Services initialisieren (Auth, Notion-Client)."""
        try:
            # Auth-Manager initialisieren
            auth_manager.initialize()

            # Notion-Client erstellen
            self.notion = NotionClient()

            if self.args and self.args.verbose:
                print("[✅] Services initialisiert")

        except Exception as e:
            print(f"[❌] Service-Initialisierung fehlgeschlagen: {e}")
            sys.exit(1)

    def run(self) -> None:
        """Hauptfunktion der CLI."""
        print("🧠 Planner-zu-Notion Migration")
        print("=" * 40)

        # Argumente parsen und validieren
        self.args = self.parse_arguments()
        self.validate_arguments(self.args)

        if self.args.verbose:
            print(f"[i] CSV-Datei: {self.args.csv}")
            if self.args.database:
                print(f"[i] Ziel-Datenbank: {self.args.database}")
            else:
                print(f"[i] Parent-Page: {self.args.parent}")
                print(f"[i] Datenbank-Titel: {self.args.db_title}")

        # Services initialisieren
        self.initialize_services()

        # Module orchestrieren und Migration durchführen
        self.run_migration()

    def run_migration(self) -> None:
        """Vollständige Migration durchführen."""
        from .processor import create_planner_processor
        from .people_mapper import create_people_mapper
        from .notion_mapper import create_notion_mapper
        from core.utils import setup_rate_limiting

        print("[🚀] Starte Migration...")

        # 1. CSV-Prozessor initialisieren und Daten laden
        print("[i] Verarbeite CSV-Datei...")
        processor = create_planner_processor(self.args.csv)
        processor.load_csv()
        processed_data = processor.process_all_rows()

        if not processed_data:
            print("[❌] Keine gültigen Daten in CSV gefunden")
            return

        print(f"[✅] {len(processed_data)} Zeilen verarbeitet")

        # Bereinigte CSV speichern
        clean_csv_path = processor.save_clean_csv()
        print(f"[i] Bereinigte CSV gespeichert: {clean_csv_path}")

        # 2. Personen-Mapper initialisieren (falls Mapping-CSV vorhanden)
        people_mapper = None
        if self.args.people_map:
            print("[i] Lade Personen-Mapping...")
            people_mapper = create_people_mapper(self.args.people_map)
            people_mapper.initialize_notion_client(self.notion)
            people_mapper.build_mappings()

            unmapped = people_mapper.get_unmapped_names()
            if unmapped:
                print(f"[⚠️] {len(unmapped)} Personen konnten nicht gemappt werden")

        # 3. Notion-Mapper initialisieren
        notion_mapper = create_notion_mapper(self.notion)

        # 4. Datenbank vorbereiten oder verwenden
        database_id = self._prepare_database(notion_mapper, processed_data)

        # 5. Daten importieren
        self._import_data(notion_mapper, database_id, processed_data, people_mapper)

    def _prepare_database(self, notion_mapper, processed_data) -> str:
        """Datenbank erstellen oder verwenden."""
        if self.args.database:
            # Bestehende Datenbank verwenden
            database_id = self.args.database
            print(f"[i] Verwende bestehende Datenbank: {database_id}")

            # Schema und Optionen vorbereiten
            notion_mapper.prepare_database_for_import(database_id, processed_data)

        else:
            # Neue Datenbank erstellen
            print(f"[i] Erstelle neue Datenbank: {self.args.db_title}")
            parent_page_id = self.args.parent

            db = self.notion.create_database(
                parent_page_id=parent_page_id,
                title=self.args.db_title,
                properties=notion_mapper.BASE_PROPERTIES
            )
            database_id = db["id"]
            print(f"[✅] Datenbank erstellt: {database_id}")

            # Optionen hinzufügen
            notion_mapper.prepare_database_for_import(database_id, processed_data)

        return database_id

    def _import_data(self, notion_mapper, database_id: str, processed_data: List[Dict],
                    people_mapper) -> None:
        """Daten in Notion importieren."""
        from core.utils import setup_rate_limiting

        print(f"[i] Importiere {len(processed_data)} Einträge...")

        # Rate Limiting konfigurieren
        delay = setup_rate_limiting(self.args.rate)

        success_count = 0
        error_count = 0

        for i, row in enumerate(processed_data):
            try:
                # Properties und Blöcke erstellen
                properties = notion_mapper.build_properties_for_row(row, people_mapper)
                children = notion_mapper.build_children_blocks(row)

                # Upsert-Logik
                page_id = None
                if self.args.upsert:
                    unique_value = row.get(self.args.unique)
                    if unique_value:
                        page_id = notion_mapper.find_existing_page(
                            database_id, self.args.unique, str(unique_value)
                        )

                # Seite erstellen oder aktualisieren
                if page_id:
                    # Bestehende Seite aktualisieren
                    self.notion.update_page(page_id, properties)
                    if children:
                        self.notion.append_blocks(page_id, children)
                    action = "aktualisiert"
                else:
                    # Neue Seite erstellen
                    self.notion.create_page(database_id, properties, children)
                    action = "erstellt"

                success_count += 1
                print(f"[{i+1}/{len(processed_data)}] {action}: {row.get('Name', 'Unbenannt')}")

                # Rate Limiting
                if delay > 0:
                    import time
                    time.sleep(delay)

            except Exception as e:
                error_count += 1
                print(f"[❌] Fehler bei Zeile {i+1}: {e}")
                if self.args.verbose:
                    import traceback
                    traceback.print_exc()

        # Zusammenfassung
        print("\n" + "=" * 50)
        print("📊 MIGRATIONS-ZUSAMMENFASSUNG")
        print("=" * 50)
        print(f"✅ Erfolgreich: {success_count}")
        print(f"❌ Fehler: {error_count}")
        print(f"📈 Erfolgsrate: {success_count/(success_count+error_count)*100:.1f}%" if (success_count+error_count) > 0 else "📈 Erfolgsrate: 0%")
        print(f"🗃️ Datenbank: {database_id}")
        print("=" * 50)


def main():
    """Einstiegspunkt für die CLI."""
    cli = PlannerMigrationCLI()
    cli.run()


if __name__ == "__main__":
    main()
