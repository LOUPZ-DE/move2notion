#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI-Interface für Microsoft 365 Overview.

Listet alle Teams-Gruppen mit ihren OneNote-Notebooks und Planner-Plänen auf.
"""
import argparse
import json
import sys
from typing import Optional, List, Dict, Any

from core.auth import auth_manager
from core.ms_graph_client import MSGraphClient


class OverviewCLI:
    """CLI-Interface für Microsoft 365 Overview."""

    def __init__(self):
        self.ms_graph: Optional[MSGraphClient] = None
        self.args = None

    def parse_arguments(self) -> argparse.Namespace:
        """Kommandozeilenargumente parsen."""
        parser = argparse.ArgumentParser(
            description="Microsoft 365-Gruppen mit Notebooks und Planner-Plänen auflisten",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Beispiele:
  # Alle Gruppen mit Notebooks und Plans auflisten
  python -m tools.overview.cli

  # Mit detaillierten Ausgaben
  python -m tools.overview.cli --verbose

  # Nur Gruppen ohne Notebooks/Plans (schneller)
  python -m tools.overview.cli --groups-only

  # Ausgabe als JSON
  python -m tools.overview.cli --json
            """
        )

        parser.add_argument("--verbose", "-v", action="store_true",
                            help="Detaillierte Ausgaben")
        parser.add_argument("--groups-only", action="store_true",
                            help="Nur Gruppen auflisten (ohne Notebooks/Plans)")
        parser.add_argument("--json", action="store_true",
                            help="Ausgabe als JSON")

        return parser.parse_args()

    def initialize_services(self) -> None:
        """Services initialisieren."""
        try:
            auth_manager.initialize()
            self.ms_graph = MSGraphClient()

            if self.args and self.args.verbose:
                print("[OK] Services initialisiert")
        except Exception as e:
            print(f"[FEHLER] Service-Initialisierung fehlgeschlagen: {e}")
            sys.exit(1)

    @property
    def is_application_mode(self) -> bool:
        """Prüfen ob Application-Modus aktiv ist."""
        return auth_manager.auth_mode == "application"

    def run(self) -> None:
        """Hauptfunktion der CLI."""
        self.args = self.parse_arguments()

        if not self.args.json:
            print("Microsoft 365 Overview")
            print("=" * 50)

        self.initialize_services()

        if self.is_application_mode and not self.args.json:
            print("[i] Auth-Modus: Application (Client Credentials)")
            print("[i] OneNote-Notebooks nicht verfuegbar (Microsoft erfordert Delegated Auth fuer OneNote-API seit 03/2025)")

        self.run_overview()

    def run_overview(self) -> None:
        """Gruppen mit Notebooks und Plans auflisten."""
        if not self.args.json:
            print("[i] Rufe Microsoft 365-Gruppen ab...")

        groups = self.ms_graph.list_groups()

        if not self.args.json:
            print(f"[OK] {len(groups)} Gruppen gefunden")

        if not groups:
            if not self.args.json:
                print("[i] Keine Microsoft 365-Gruppen im Tenant gefunden.")
            elif self.args.json:
                print(json.dumps([], ensure_ascii=False))
            return

        results = []

        for i, group in enumerate(groups):
            group_id = group["id"]
            group_name = group.get("displayName", "Unbekannt")

            entry = {
                "id": group_id,
                "name": group_name,
                "mail": group.get("mail", ""),
                "description": group.get("description", ""),
                "notebooks": [],
                "plans": [],
            }

            if not self.args.groups_only:
                # OneNote-Notebooks abrufen (nur im Delegated-Modus)
                if self.is_application_mode:
                    entry["notebooks_error"] = "Nicht verfuegbar im Application-Modus (Delegated Auth erforderlich)"
                else:
                    try:
                        notebooks = self.ms_graph.list_group_notebooks(group_id)
                        entry["notebooks"] = [
                            {"id": nb.get("id", ""), "name": nb.get("displayName", "")}
                            for nb in notebooks
                        ]
                    except Exception as e:
                        entry["notebooks_error"] = str(e)
                        if self.args.verbose:
                            print(f"  [WARNUNG] Notebooks fuer '{group_name}' nicht abrufbar: {e}")

                # Planner-Plans abrufen
                try:
                    plans = self.ms_graph.list_group_planner_plans(group_id)
                    entry["plans"] = [
                        {"id": p.get("id", ""), "name": p.get("title", "")}
                        for p in plans
                    ]
                except Exception as e:
                    entry["plans_error"] = str(e)
                    if self.args.verbose:
                        print(f"  [WARNUNG] Plans fuer '{group_name}' nicht abrufbar: {e}")

            results.append(entry)

            if self.args.verbose and not self.args.json:
                nb_count = len(entry.get("notebooks", []))
                plan_count = len(entry.get("plans", []))
                print(f"  [{i + 1}/{len(groups)}] {group_name}: {nb_count} Notebooks, {plan_count} Plans")

        # Ausgabe
        if self.args.json:
            print(json.dumps(results, indent=2, ensure_ascii=False))
        else:
            self._print_formatted(results)

    def _print_formatted(self, results: List[Dict[str, Any]]) -> None:
        """Ergebnisse formatiert ausgeben."""
        print()
        print("=" * 70)
        print(f"{'MICROSOFT 365 GRUPPEN':^70}")
        print("=" * 70)

        for entry in results:
            print(f"\n{'─' * 70}")
            print(f"  {entry['name']}")
            if entry.get("mail"):
                print(f"  Mail: {entry['mail']}")
            if entry.get("description"):
                desc = entry["description"][:80]
                print(f"  Beschreibung: {desc}")
            print(f"  ID: {entry['id']}")

            # Notebooks
            notebooks = entry.get("notebooks", [])
            if notebooks:
                print(f"\n  OneNote Notebooks ({len(notebooks)}):")
                for nb in notebooks:
                    print(f"    - {nb['name']}")
                    print(f"      ID: {nb['id']}")
            elif "notebooks_error" in entry:
                print(f"\n  OneNote Notebooks: [Fehler] {entry['notebooks_error']}")
            elif not self.args.groups_only:
                print(f"\n  OneNote Notebooks: keine")

            # Plans
            plans = entry.get("plans", [])
            if plans:
                print(f"\n  Planner-Plaene ({len(plans)}):")
                for p in plans:
                    print(f"    - {p['name']}")
                    print(f"      ID: {p['id']}")
            elif "plans_error" in entry:
                print(f"\n  Planner-Plaene: [Fehler] {entry['plans_error']}")
            elif not self.args.groups_only:
                print(f"\n  Planner-Plaene: keine")

        # Zusammenfassung
        total_notebooks = sum(len(e.get("notebooks", [])) for e in results)
        total_plans = sum(len(e.get("plans", [])) for e in results)
        print(f"\n{'=' * 70}")
        print(f"  Zusammenfassung: {len(results)} Gruppen, "
              f"{total_notebooks} Notebooks, {total_plans} Planner-Plaene")
        print(f"{'=' * 70}")


def main():
    """Einstiegspunkt fuer die CLI."""
    cli = OverviewCLI()
    cli.run()


if __name__ == "__main__":
    main()
