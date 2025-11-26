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
import warnings
from pathlib import Path
from typing import Optional, List, Dict, Any

# Unterdrücke urllib3 NotOpenSSLWarning (LibreSSL vs OpenSSL)
warnings.filterwarnings("ignore", category=Warning, module="urllib3")

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
        
        # Pass 2: Link-Resolution
        parser.add_argument("--resolve-links", action="store_true",
                          help="Pass 2: OneNote-interne Links auflösen (nach Import ausführen)")

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

        # Pass 2: Link-Resolution oder normale Migration
        if self.args.resolve_links:
            self.run_link_resolution()
        else:
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
        
        # 4. Automatisch Link-Resolution nach Import (wenn database_id angegeben)
        if self.args.database_id and not self.args.dry_run:
            print("\n[🔗] Starte automatische Link-Resolution...")
            self.run_link_resolution()

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

        # Notebook-Name speichern für späteren Zugriff
        self._current_notebook_name = notebook_name

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
        """Sections eines Notebooks laden (inkl. Section Groups)."""
        try:
            sections = self.ms_graph.get_notebook_sections(site_id, notebook_id)
            
            if self.args and self.args.verbose:
                print(f"[i] {len(sections)} Section(s) gefunden")
                for sec in sections:
                    group_name = sec.get("_groupName", "")
                    sec_name = sec.get("displayName", "Unbekannt")
                    if group_name:
                        print(f"    - {group_name} / {sec_name}")
                    else:
                        print(f"    - {sec_name}")
            
            if not sections:
                print(f"[⚠] Keine Sections gefunden in diesem Notebook")
            
            return sections
        except Exception as e:
            print(f"[❌] Section-Laden fehlgeschlagen: {e}")
            if self.args and self.args.verbose:
                import traceback
                traceback.print_exc()
            return []

    def _process_section(self, site_id: str, notebook_id: str, section: Dict[str, Any]) -> None:
        """Section verarbeiten."""
        section_id = section["id"]
        section_name = section["displayName"]
        section_group = section.get("_groupName", "")  # Section Group Name (falls in Gruppe)

        if section_group:
            print(f"  📄 Section: {section_group} / {section_name}")
        else:
            print(f"  📄 Section: {section_name}")

        # Section-Name und Gruppen-Name speichern für späteren Zugriff
        self._current_section_name = section_name
        self._current_section_group = section_group

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

        # Datenbank-ID prüfen
        if not self.args.database_id:
            print(f"    📃 Seite: {page_title}")
            print(f"      [⚠] Keine Datenbank-ID angegeben, überspringe Import")
            return

        # Bei Resume: Seite überspringen falls unverändert
        if self.args and self.args.resume and self.content_mapper:
            should_skip, reason = self.content_mapper.should_skip_page(page, self.args.database_id)
            if should_skip:
                print(f"    ⏭️ Seite: {page_title} ({reason})")
                return

        print(f"    📃 Seite: {page_title}")

        if self.args and self.args.dry_run:
            print(f"      [Dry-run] Würde importieren: {page_title}")
            return

        # Seite mit ContentMapper verarbeiten
        if self.content_mapper:
            notion_page_id = self.content_mapper.map_page_to_notion(
                onenote_page=page,
                database_id=self.args.database_id,
                section_name=getattr(self, '_current_section_name', ''),
                notebook_name=getattr(self, '_current_notebook_name', ''),
                section_group=getattr(self, '_current_section_group', '')
            )

    def _get_section_name(self, section_id: str) -> str:
        """Section-Name aus Cache oder aktueller Verarbeitung holen."""
        # Vereinfacht: Könnte aus Cache geholt werden
        return ""

    def _get_notebook_name(self, notebook_id: str) -> str:
        """Notebook-Name aus Cache oder aktueller Verarbeitung holen."""
        # Vereinfacht: Könnte aus Cache geholt werden
        return ""

    def run_link_resolution(self) -> None:
        """
        Pass 2: OneNote-interne Links in Notion-Seiten auflösen.
        
        Durchsucht alle Seiten mit "(Verlinkung unvollständig)" Markern
        und versucht, die Links zu korrigieren.
        """
        from .html_parser import INCOMPLETE_LINK_MARKER, extract_page_id_from_link
        
        print("[🔗] Pass 2: Link-Resolution")
        print("=" * 40)
        
        if not self.args.database_id:
            print("[❌] --database-id erforderlich für Link-Resolution")
            sys.exit(1)
        
        database_id = self.args.database_id
        
        if self.args.verbose:
            print(f"[i] Database-ID: {database_id}")
        
        # 1. Alle Seiten mit unvollständigen Links finden
        print("[i] Suche Seiten mit unvollständigen Links...")
        
        try:
            # Query alle Seiten in der Datenbank
            pages = self._query_all_pages(database_id)
            print(f"[i] {len(pages)} Seiten in Datenbank gefunden")
            
            if self.args.verbose and len(pages) == 0:
                # Debug: Prüfe ob Datenbank existiert
                try:
                    db_info = self.notion.get_database(database_id)
                    db_title = db_info.get("title", [{}])[0].get("plain_text", "Unbekannt")
                    print(f"[i] Datenbank gefunden: {db_title}")
                    print(f"[⚠] Die Datenbank ist leer oder hat keine Seiten.")
                except Exception as db_err:
                    print(f"[❌] Datenbank nicht gefunden oder kein Zugriff: {db_err}")
                    
        except Exception as e:
            print(f"[❌] Fehler beim Laden der Seiten: {e}")
            if self.args.verbose:
                import traceback
                traceback.print_exc()
            sys.exit(1)
        
        # 2. OneNote-PageId → Notion-PageId Mapping erstellen
        print("[i] Erstelle OneNote → Notion Mapping...")
        page_mapping = self._build_page_mapping(pages)
        print(f"[i] {len(page_mapping)} OneNote-Pages gemappt")
        
        # 3. Seiten durchgehen und Links korrigieren
        resolved_count = 0
        error_count = 0
        skipped_count = 0
        
        for page in pages:
            notion_page_id = page.get("id")
            page_title = self._get_page_title(page)
            
            try:
                # Blöcke der Seite laden
                blocks = self._get_all_blocks(notion_page_id)
                
                # Links in Blöcken finden und korrigieren
                updated = self._resolve_links_in_blocks(
                    notion_page_id, 
                    blocks, 
                    page_mapping,
                    INCOMPLETE_LINK_MARKER
                )
                
                if updated > 0:
                    resolved_count += updated
                    print(f"  [✅] {page_title}: {updated} Links korrigiert")
                else:
                    skipped_count += 1
                    if self.args.verbose:
                        print(f"  [=] {page_title}: keine unvollständigen Links")
                        
            except Exception as e:
                error_count += 1
                print(f"  [❌] {page_title}: {e}")
        
        # Zusammenfassung
        print()
        print("=" * 40)
        print(f"[✅] Link-Resolution abgeschlossen:")
        print(f"    - {resolved_count} Links korrigiert")
        print(f"    - {skipped_count} Seiten ohne Änderungen")
        print(f"    - {error_count} Fehler")

    def _query_all_pages(self, database_id: str) -> List[Dict[str, Any]]:
        """Alle Seiten einer Datenbank abrufen (mit Pagination)."""
        all_pages = []
        start_cursor = None
        
        while True:
            result = self.notion.query_database(
                database_id,
                start_cursor=start_cursor,
                page_size=100
            )
            
            all_pages.extend(result.get("results", []))
            
            if not result.get("has_more"):
                break
            start_cursor = result.get("next_cursor")
        
        return all_pages

    def _build_page_mapping(self, pages: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Erstellt ein Mapping von OneNote-PageId zu Notion-PageId.
        
        Returns:
            Dict[OneNotePageId, NotionPageId]
        """
        mapping = {}
        
        for page in pages:
            notion_id = page.get("id")
            properties = page.get("properties", {})
            
            # OneNotePageId Property suchen
            onenote_id_prop = properties.get("OneNotePageId", {})
            
            # Property-Typ erkennen (rich_text oder url)
            if onenote_id_prop.get("type") == "rich_text":
                rich_text = onenote_id_prop.get("rich_text", [])
                if rich_text:
                    onenote_page_id = rich_text[0].get("plain_text", "")
                    if onenote_page_id:
                        # Normalisieren (lowercase, ohne Klammern)
                        normalized_id = onenote_page_id.lower().strip("{}")
                        mapping[normalized_id] = notion_id
            elif onenote_id_prop.get("type") == "url":
                onenote_page_id = onenote_id_prop.get("url", "")
                if onenote_page_id:
                    normalized_id = onenote_page_id.lower().strip("{}")
                    mapping[normalized_id] = notion_id
        
        return mapping

    def _get_page_title(self, page: Dict[str, Any]) -> str:
        """Titel einer Notion-Page extrahieren."""
        properties = page.get("properties", {})
        
        # Titel-Property finden (hat type="title")
        for prop_name, prop_value in properties.items():
            if prop_value.get("type") == "title":
                title_array = prop_value.get("title", [])
                if title_array:
                    return title_array[0].get("plain_text", "Untitled")
        
        return "Untitled"

    def _get_all_blocks(self, page_id: str) -> List[Dict[str, Any]]:
        """Alle Blöcke einer Seite abrufen (inkl. Children)."""
        all_blocks = []
        
        def fetch_blocks(parent_id: str, depth: int = 0):
            if depth > 3:  # Max Tiefe
                return
            
            start_cursor = None
            while True:
                result = self.notion.get_block_children(parent_id, start_cursor=start_cursor)
                blocks = result.get("results", [])
                
                for block in blocks:
                    all_blocks.append(block)
                    
                    # Rekursiv Children laden
                    if block.get("has_children"):
                        fetch_blocks(block.get("id"), depth + 1)
                
                if not result.get("has_more"):
                    break
                start_cursor = result.get("next_cursor")
        
        fetch_blocks(page_id)
        return all_blocks

    def _resolve_links_in_blocks(
        self, 
        page_id: str, 
        blocks: List[Dict[str, Any]], 
        page_mapping: Dict[str, str],
        incomplete_marker: str
    ) -> int:
        """
        Links in Blöcken korrigieren.
        
        Returns:
            Anzahl der korrigierten Links
        """
        from .html_parser import extract_page_id_from_link
        
        resolved_count = 0
        
        for block in blocks:
            block_id = block.get("id")
            block_type = block.get("type")
            
            if not block_type:
                continue
            
            # Block-Content holen
            content = block.get(block_type, {})
            rich_text = content.get("rich_text", [])
            
            if not rich_text:
                continue
            
            # Prüfen ob unvollständige Links vorhanden
            needs_update = False
            new_rich_text = []
            
            for rt in rich_text:
                text_content = rt.get("text", {}).get("content", "")
                link = rt.get("text", {}).get("link")
                
                if incomplete_marker in text_content and link:
                    # Unvollständiger Link gefunden!
                    href = link.get("url", "")
                    onenote_page_id = extract_page_id_from_link(href)
                    
                    if onenote_page_id:
                        # Normalisieren
                        normalized_id = onenote_page_id.lower().strip("{}")
                        
                        # Notion-Page-ID nachschlagen
                        notion_target_id = page_mapping.get(normalized_id)
                        
                        if notion_target_id:
                            # Link korrigieren!
                            new_text = text_content.replace(incomplete_marker, "")
                            notion_url = f"https://notion.so/{notion_target_id.replace('-', '')}"
                            
                            new_rt = rt.copy()
                            new_rt["text"] = {
                                "content": new_text,
                                "link": {"url": notion_url}
                            }
                            new_rich_text.append(new_rt)
                            needs_update = True
                            resolved_count += 1
                            continue
                
                # Unverändert übernehmen
                new_rich_text.append(rt)
            
            # Block aktualisieren wenn nötig
            if needs_update and not self.args.dry_run:
                try:
                    self.notion.update_block(block_id, {
                        block_type: {"rich_text": new_rich_text}
                    })
                except Exception as e:
                    if self.args.verbose:
                        print(f"    [⚠] Block-Update fehlgeschlagen: {e}")
        
        return resolved_count


def main():
    """Einstiegspunkt für die CLI."""
    cli = OneNoteMigrationCLI()
    cli.run()


if __name__ == "__main__":
    main()
