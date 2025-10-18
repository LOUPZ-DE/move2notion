#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI-Interface für OneNote-zu-Notion Migration.

Dieses Modul orchestriert die OneNote-Migration:
- SharePoint-Site-Verbindung
- OneNote-Notebook/Section/Page-Verarbeitung
- Rich-Content-Parsing und Asset-Download
- Notion-Import mit State Management
"""
import argparse
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

# Core-Module importieren
from core.auth import auth_manager
from core.notion_client import NotionClient
from core.ms_graph_client import MSGraphClient
from core.state_manager import StateManager, generate_page_key, calculate_checksum

# Tool-Module importieren
from .content_mapper import ContentMapper
from .resource_handler import ResourceHandler


class OneNoteMigrationCLI:
    """CLI-Interface für OneNote-Migration."""

    def __init__(self):
        self.notion: Optional[NotionClient] = None
        self.ms_graph: Optional[MSGraphClient] = None
        self.state_manager: Optional[StateManager] = None
        self.content_mapper: Optional[ContentMapper] = None
        self.args = None

    def parse_arguments(self) -> argparse.Namespace:
        """Kommandozeilenargumente parsen."""
        parser = argparse.ArgumentParser(
            description="OneNote zu Notion migrieren",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Beispiele:
  # OneNote-Abschnitt importieren
  python -m tools.onenote_migration.cli --site-url "https://tenant.sharepoint.com/sites/Site" --notebook "Notizbuch" --section "Abschnitt"

  # Mit Zeitfilter und Resume
  python -m tools.onenote_migration.cli --site-url "..." --notebook "Notizbuch" --since 2025-01-01 --resume

  # Nur bestimmtes Notebook (alle Sections)
  python -m tools.onenote_migration.cli --site-url "..." --notebook "Notizbuch" --resume
            """
        )

        # Erforderliche Parameter
        parser.add_argument("--site-url", required=True,
                          help="SharePoint-Site-URL")

        # OneNote-Quell-Optionen
        notebook_group = parser.add_mutually_exclusive_group()
        notebook_group.add_argument("--notebook", help="Notebook-Name (fuzzy match)")
        notebook_group.add_argument("--notebook-id", help="Notebook-ID")

        parser.add_argument("--section", help="Section-Name (optional)")

        # Notion-Ziel
        parser.add_argument("--database-id", help="Ziel-Notion-Datenbank-ID")
        parser.add_argument("--dry-run", action="store_true",
                          help="Trockenlauf ohne Änderungen")

        # Zeitfilter
        parser.add_argument("--since", help="Nur seit Datum geänderte Seiten (YYYY-MM-DD)")

        # State Management
        parser.add_argument("--resume", action="store_true",
                          help="Überspringe unveränderte Seiten")
        parser.add_argument("--state-path", help="Pfad für State-Datei")

        # Debug-Optionen
        parser.add_argument("--verbose", "-v", action="store_true",
                          help="Detaillierte Ausgaben")

        return parser.parse_args()

    def initialize_services(self) -> None:
        """Services initialisieren."""
        try:
            # Auth-Manager initialisieren
            auth_manager.initialize()

            # Clients erstellen
            self.notion = NotionClient()
            self.ms_graph = MSGraphClient()

            # State Manager
            state_path = self.args.state_path if self.args else None
            self.state_manager = StateManager(state_path)

            # Content Mapper wird später mit site_id initialisiert

            if self.args and self.args.verbose:
                print("[✅] Services initialisiert")

        except Exception as e:
            print(f"[❌] Service-Initialisierung fehlgeschlagen: {e}")
            sys.exit(1)

    def run(self) -> None:
        """Hauptfunktion der CLI."""
        print("📝 OneNote-zu-Notion Migration")
        print("=" * 40)

        # Argumente parsen
        self.args = self.parse_arguments()

        if self.args.verbose:
            print(f"[i] Site-URL: {self.args.site_url}")
            if self.args.notebook:
                print(f"[i] Notebook: {self.args.notebook}")
            if self.args.section:
                print(f"[i] Section: {self.args.section}")

        # Services initialisieren
        self.initialize_services()

        # Migration durchführen
        self.run_migration()

    def run_migration(self) -> None:
        """Vollständige Migration durchführen."""
        print("[🚀] Starte OneNote-Migration...")

        # 1. SharePoint-Site auflösen
        print("[i] Löse SharePoint-Site auf...")
        site_id = self._resolve_site()

        # 2. OneNote-Notebook(s) finden
        notebooks = self._find_notebooks(site_id)

        # 3. Sections verarbeiten
        for notebook in notebooks:
            self._process_notebook(site_id, notebook)

    def _resolve_site(self) -> str:
        """SharePoint-Site auflösen."""
        try:
            site_id = self.ms_graph.resolve_site_id_from_url(self.args.site_url)
            print(f"[✅] Site aufgelöst: {site_id}")
            return site_id
        except Exception as e:
            print(f"[❌] Site-Auflösung fehlgeschlagen: {e}")
            sys.exit(1)

    def _find_notebooks(self, site_id: str) -> List[Dict[str, Any]]:
        """OneNote-Notebooks finden."""
        try:
            notebooks = self.ms_graph.list_site_notebooks(site_id)

            if not notebooks:
                print("[❌] Keine Notebooks gefunden")
                sys.exit(1)

            # Notebook filtern falls angegeben
            if self.args.notebook_id:
                notebook = self._find_notebook_by_id(notebooks, self.args.notebook_id)
            elif self.args.notebook:
                notebook = self._find_notebook_by_name(notebooks, self.args.notebook)
            else:
                # Alle Notebooks verwenden
                return notebooks

            if not notebook:
                print("[❌] Notebook nicht gefunden")
                self._list_available_notebooks(notebooks)
                sys.exit(1)

            print(f"[✅] Notebook gefunden: {notebook['displayName']}")
            return [notebook]

        except Exception as e:
            print(f"[❌] Notebook-Suche fehlgeschlagen: {e}")
            sys.exit(1)

    def _find_notebook_by_id(self, notebooks: List[Dict], notebook_id: str) -> Optional[Dict]:
        """Notebook anhand ID finden."""
        # Exakte ID-Match
        for nb in notebooks:
            if nb.get("id") == notebook_id:
                return nb

        # Teilweise ID-Match (z.B. ohne Prefix)
        for nb in notebooks:
            if str(nb.get("id", "")).lower().endswith(str(notebook_id).lower().replace("1-", "")):
                return nb

        return None

    def _find_notebook_by_name(self, notebooks: List[Dict], name: str) -> Optional[Dict]:
        """Notebook anhand Name finden (fuzzy match)."""
        from difflib import get_close_matches

        notebook_names = [nb.get("displayName", "") for nb in notebooks]
        matches = get_close_matches(name, notebook_names, n=1, cutoff=0.2)

        if matches:
            for nb in notebooks:
                if nb.get("displayName") == matches[0]:
                    return nb

        return None

    def _list_available_notebooks(self, notebooks: List[Dict]) -> None:
        """Verfügbare Notebooks auflisten."""
        print("\nVerfügbare Notebooks:")
        for nb in notebooks:
            print(f"  - {nb.get('displayName')} [id={nb.get('id')}]")

    def _process_notebook(self, site_id: str, notebook: Dict[str, Any]) -> None:
        """Notebook verarbeiten."""
        notebook_id = notebook["id"]
        notebook_name = notebook["displayName"]

        print(f"\n📚 Verarbeite Notebook: {notebook_name}")

        # ContentMapper mit site_id initialisieren (falls noch nicht gemacht)
        if not self.content_mapper:
            self.content_mapper = ContentMapper(self.notion, self.ms_graph, site_id)

        # Sections laden
        sections = self._get_sections(site_id, notebook_id)

        # Section filtern falls angegeben
        if self.args.section:
            sections = [s for s in sections if s.get("displayName") == self.args.section]
            if not sections:
                print(f"[❌] Section '{self.args.section}' nicht gefunden")
                return

        # Sections verarbeiten
        for section in sections:
            self._process_section(site_id, notebook_id, section)

    def _get_sections(self, site_id: str, notebook_id: str) -> List[Dict[str, Any]]:
        """Sections eines Notebooks laden."""
        try:
            return self.ms_graph.get_notebook_sections(site_id, notebook_id)
        except Exception as e:
            print(f"[❌] Section-Laden fehlgeschlagen: {e}")
            return []

    def _process_section(self, site_id: str, notebook_id: str, section: Dict[str, Any]) -> None:
        """Section verarbeiten."""
        section_id = section["id"]
        section_name = section["displayName"]

        print(f"  📄 Section: {section_name}")

        # Seiten laden
        pages = self._get_pages(site_id, section_id)

        # Seiten verarbeiten
        for page in pages:
            self._process_page(site_id, notebook_id, section_id, page)

    def _get_pages(self, site_id: str, section_id: str) -> List[Dict[str, Any]]:
        """Seiten einer Section laden."""
        try:
            return self.ms_graph.list_pages_for_section(
                site_id, section_id,
                since=self.args.since if self.args else None
            )
        except Exception as e:
            print(f"[❌] Seiten-Laden fehlgeschlagen: {e}")
            return []

    def _process_page(self, site_id: str, notebook_id: str, section_id: str, page: Dict[str, Any]) -> None:
        """Einzelne Seite verarbeiten."""
        page_id = page["id"]
        page_title = page.get("title") or "Untitled"

        # State-Key generieren
        state_key = generate_page_key(site_id, notebook_id, section_id, page_id)

        # Bei Resume: Seite überspringen falls unverändert
        if self.args and self.args.resume:
            # TODO: HTML-Inhalt laden und Checksumme berechnen
            pass
            # if self.state_manager.is_page_unchanged(state_key, current_checksum):
            #     print(f"  = {page_title} (unverändert)")
            #     return

        print(f"    📃 Seite: {page_title}")

        if self.args and self.args.dry_run:
            print(f"      [Dry-run] Würde importieren: {page_title}")
            return

        # Datenbank-ID prüfen
        if not self.args.database_id:
            print(f"      [⚠] Keine Datenbank-ID angegeben, überspringe Import")
            return

        # Seite mit ContentMapper verarbeiten
        if self.content_mapper:
            notion_page_id = self.content_mapper.map_page_to_notion(
                onenote_page=page,
                database_id=self.args.database_id,
                section_name=self._get_section_name(section_id),
                notebook_name=self._get_notebook_name(notebook_id)
            )
            
            # State-Update könnte hier erfolgen (optional für später)
            # if notion_page_id and self.state_manager:
            #     self.state_manager.mark_page_processed(state_key, checksum)
            pass

    def _get_section_name(self, section_id: str) -> str:
        """Section-Name aus Cache oder aktueller Verarbeitung holen."""
        # Vereinfacht: Könnte aus Cache geholt werden
        return ""

    def _get_notebook_name(self, notebook_id: str) -> str:
        """Notebook-Name aus Cache oder aktueller Verarbeitung holen."""
        # Vereinfacht: Könnte aus Cache geholt werden
        return ""


def main():
    """Einstiegspunkt für die CLI."""
    cli = OneNoteMigrationCLI()
    cli.run()


if __name__ == "__main__":
    main()
