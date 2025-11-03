#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI-Interface für Planner-zu-Notion Migration.

Dieses Modul orchestriert die verschiedenen Komponenten der Planner-Migration:
- Planner-API-Zugriff
- Personen-Mapping
- Notion-Datenbank-Operationen
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
            description="Microsoft Planner zu Notion migrieren (via API)",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Beispiele:
  # Plan direkt aus Planner importieren
  python -m tools.planner_migration.cli --plan-id PLAN_ID --database DB_ID

  # Mit Personen-Mapping
  python -m tools.planner_migration.cli --plan-id PLAN_ID --database DB_ID --people-map mapping.csv

  # Mit detaillierten Ausgaben
  python -m tools.planner_migration.cli --plan-id PLAN_ID --database DB_ID --verbose

Plan ID finden:
  Öffnen Sie einen Planner-Plan in Microsoft Planner
  URL: https://tasks.office.com/.../taskboard?groupId=xxx&planId=PLAN_ID
  Kopieren Sie die planId aus der URL
            """
        )

        # Input-Optionen
        parser.add_argument("--plan-id", required=True, help="Planner Plan ID")
        parser.add_argument("--database", required=True, help="Notion Datenbank ID")

        # Erweiterte Optionen
        parser.add_argument("--people-map", help="CSV für Personen-Mapping (Name → Notion Email)")
        parser.add_argument("--verbose", "-v", action="store_true",
                          help="Detaillierte Ausgaben")

        return parser.parse_args()

    def validate_arguments(self, args: argparse.Namespace) -> None:
        """Argumente validieren."""
        # Plan ID prüfen
        if not args.plan_id:
            print("[❌] --plan-id ist erforderlich")
            sys.exit(1)
        
        # Database ID prüfen
        if not args.database:
            print("[❌] --database ist erforderlich")
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
            print(f"[i] Plan ID: {self.args.plan_id}")
            print(f"[i] Ziel-Datenbank: {self.args.database}")

        # Services initialisieren
        self.initialize_services()

        # Module orchestrieren und Migration durchführen
        self.run_migration()

    def run_migration(self) -> None:
        """Vollständige Migration durchführen."""
        from core.ms_graph_client import MSGraphClient
        from .planner_api_mapper import create_planner_api_mapper
        from .people_mapper import create_people_mapper
        from .notion_mapper import create_notion_mapper

        print("[🚀] Starte Migration...")

        # 1. MS Graph Client erstellen
        print("[i] Verbinde mit Microsoft Graph API...")
        ms_client = MSGraphClient()
        
        # 2. Plan-Details abrufen
        print(f"[i] Rufe Plan-Details ab...")
        plan = ms_client.get_planner_plan(self.args.plan_id)
        plan_title = plan.get("title", "Unbekannter Plan")
        group_id = plan.get("owner")
        print(f"[✅] Plan gefunden: {plan_title}")
        
        # 2b. Plan-Details für Category-Descriptions abrufen
        try:
            plan_details = ms_client.get_planner_plan_details(self.args.plan_id)
            category_descriptions = plan_details.get("categoryDescriptions", {})
            if self.args.verbose:
                print(f"[i] {len(category_descriptions)} Categories gefunden")
        except Exception as e:
            if self.args.verbose:
                print(f"[⚠️] Plan-Details konnten nicht abgerufen werden: {e}")
            category_descriptions = {}
        
        # 3. Buckets abrufen
        print("[i] Rufe Buckets ab...")
        buckets = ms_client.list_planner_buckets(self.args.plan_id)
        print(f"[✅] {len(buckets)} Buckets gefunden")
        
        # 4. Tasks abrufen
        print("[i] Rufe Tasks ab...")
        tasks = ms_client.list_planner_tasks(self.args.plan_id)
        print(f"[✅] {len(tasks)} Tasks gefunden")
        
        # 5. Task-Details abrufen
        print("[i] Rufe Task-Details ab...")
        tasks_details = {}
        for i, task in enumerate(tasks):
            task_id = task.get("id")
            if task_id:
                try:
                    details = ms_client.get_task_details(task_id)
                    tasks_details[task_id] = details
                    if self.args.verbose:
                        print(f"  [{i+1}/{len(tasks)}] Details für '{task.get('title', 'Unbenannt')}'")
                except Exception as e:
                    if self.args.verbose:
                        print(f"  [⚠️] Details für Task {task_id} nicht abrufbar: {e}")
        
        print(f"[✅] Details für {len(tasks_details)} Tasks abgerufen")
        
        # 6. Gruppenmitglieder abrufen
        group_members = []
        if group_id:
            try:
                print("[i] Rufe Gruppenmitglieder ab...")
                group_members = ms_client.get_group_members(group_id)
                print(f"[✅] {len(group_members)} Mitglieder gefunden")
            except Exception as e:
                print(f"[⚠️] Gruppenmitglieder konnten nicht abgerufen werden: {e}")
        
        # 7. API-Mapper erstellen und Daten konvertieren
        print("[i] Konvertiere Daten...")
        api_mapper = create_planner_api_mapper()
        api_mapper.set_buckets(buckets)
        api_mapper.set_users(group_members)
        api_mapper.set_category_descriptions(category_descriptions)
        
        rows = api_mapper.map_tasks_to_rows(tasks, tasks_details)
        print(f"[✅] {len(rows)} Tasks konvertiert")
        
        if not rows:
            print("[❌] Keine Tasks gefunden")
            return
        
        # 8. Personen-Mapper initialisieren (falls Mapping-CSV vorhanden)
        people_mapper = None
        if self.args.people_map:
            print("[i] Lade Personen-Mapping...")
            people_mapper = create_people_mapper(self.args.people_map)
            people_mapper.initialize_notion_client(self.notion)
            people_mapper.build_mappings()

            unmapped = people_mapper.get_unmapped_names()
            if unmapped:
                print(f"[⚠️] {len(unmapped)} Personen konnten nicht gemappt werden")

        # 9. Notion-Mapper initialisieren
        notion_mapper = create_notion_mapper(self.notion)

        # 10. Datenbank vorbereiten
        database_id = self.args.database
        print(f"[i] Bereite Datenbank vor...")
        notion_mapper.prepare_database_for_import(database_id, rows)

        # 11. Daten importieren
        self._import_data(notion_mapper, database_id, rows, people_mapper)


    def _import_data(self, notion_mapper, database_id: str, rows: List[Dict],
                    people_mapper) -> None:
        """Daten in Notion importieren."""
        print(f"[i] Importiere {len(rows)} Einträge...")

        success_count = 0
        error_count = 0

        for i, row in enumerate(rows):
            try:
                # Properties und Blöcke erstellen
                properties = notion_mapper.build_properties_for_row(row, people_mapper)
                children = notion_mapper.build_children_blocks(row)

                # Seite erstellen
                self.notion.create_page(database_id, properties, children)
                
                success_count += 1
                task_name = row.get('Name', 'Unbenannt')
                print(f"[{i+1}/{len(rows)}] Erstellt: {task_name}")

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
