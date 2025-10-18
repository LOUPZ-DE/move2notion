#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Content-Mapper für OneNote-zu-Notion Migration.

Dieses Modul koordiniert:
- HTML-Parsing
- Ressourcen-Verarbeitung
- Notion-Page-Erstellung
"""
from typing import List, Dict, Any, Optional, Tuple

from .html_parser import parse_onenote_html
from .resource_handler import ResourceHandler


class ContentMapper:
    """Orchestriert die Konvertierung von OneNote-Content zu Notion."""

    def __init__(self, notion_client, ms_graph_client, site_id: str, resource_handler: Optional[ResourceHandler] = None):
        """
        Initialisierung.
        
        Args:
            notion_client: NotionClient-Instanz
            ms_graph_client: MSGraphClient-Instanz
            site_id: SharePoint-Site-ID
            resource_handler: Optionaler ResourceHandler
        """
        self.notion = notion_client
        self.ms_graph = ms_graph_client
        self.site_id = site_id
        self.resource_handler = resource_handler or ResourceHandler(notion_client, ms_graph_client)

    def map_page_to_notion(
        self,
        onenote_page: Dict[str, Any],
        database_id: str,
        section_name: str = "",
        notebook_name: str = ""
    ) -> Optional[str]:
        """
        OneNote-Page zu Notion konvertieren.
        
        Args:
            onenote_page: OneNote-Page-Metadaten
            database_id: Ziel-Notion-Datenbank-ID
            section_name: Section-Name für Kategorisierung
            notebook_name: Notebook-Name für Kategorisierung
            
        Returns:
            Notion-Page-ID oder None bei Fehler
        """
        try:
            # 1. Metadaten extrahieren
            page_title = onenote_page.get("title") or "Untitled"
            page_id = onenote_page["id"]
            created_time = onenote_page.get("createdDateTime")
            modified_time = onenote_page.get("lastModifiedDateTime")

            # 2. HTML-Content laden
            html_content = self._fetch_page_content(page_id)
            if not html_content:
                print(f"[⚠] Kein Content für Seite: {page_title}")
                return None

            # 3. HTML parsen
            blocks, tables = parse_onenote_html(html_content)

            # 4. Notion-Properties erstellen
            properties = self._build_properties(
                page_title,
                section_name,
                notebook_name,
                created_time,
                modified_time
            )

            # 5. Notion-Page erstellen
            notion_page_id = self.notion.create_page(
                database_id=database_id,
                properties=properties
            )

            if not notion_page_id:
                print(f"[❌] Page-Erstellung fehlgeschlagen: {page_title}")
                return None

            # 6. Assets verarbeiten (Bilder & Dateien)
            asset_blocks = self._process_assets(html_content, notion_page_id)
            
            # 7. Blöcke hinzufügen (Content + Assets)
            all_blocks = blocks + asset_blocks
            if all_blocks:
                self.notion.append_blocks(notion_page_id, all_blocks)

            # 8. Tabellen hinzufügen
            if tables:
                for table in tables:
                    self._add_table_to_page(notion_page_id, table)

            print(f"[✅] Page importiert: {page_title}")
            return notion_page_id

        except Exception as e:
            print(f"[❌] Page-Import fehlgeschlagen ({onenote_page.get('title', 'Unknown')}): {e}")
            return None

    def _process_assets(self, html_content: str, notion_page_id: str) -> List[Dict[str, Any]]:
        """
        Assets (Bilder & Dateien) aus HTML verarbeiten.
        
        Args:
            html_content: HTML-String der OneNote-Seite
            notion_page_id: Ziel-Notion-Page-ID
            
        Returns:
            Liste von Notion-Asset-Blöcken
        """
        asset_blocks = []
        
        try:
            # Bilder verarbeiten
            images = self.resource_handler.extract_images_from_html(html_content)
            for img_url in images:
                try:
                    img_block = self.resource_handler.process_image(img_url, notion_page_id)
                    if img_block:
                        asset_blocks.append(img_block)
                except Exception as e:
                    print(f"[⚠] Bild-Verarbeitung fehlgeschlagen ({img_url}): {e}")
            
            # Dateien verarbeiten
            files = self.resource_handler.extract_files_from_html(html_content)
            for file_url, file_name in files:
                try:
                    file_block = self.resource_handler.process_file(file_url, file_name, notion_page_id)
                    if file_block:
                        asset_blocks.append(file_block)
                except Exception as e:
                    print(f"[⚠] Datei-Verarbeitung fehlgeschlagen ({file_name}): {e}")
        
        except Exception as e:
            print(f"[⚠] Asset-Verarbeitung fehlgeschlagen: {e}")
        
        return asset_blocks

    def _fetch_page_content(self, page_id: str) -> Optional[str]:
        """OneNote-Page-Content laden."""
        try:
            # MS Graph API: Page-Content laden (mit site_id)
            content = self.ms_graph.get_page_content(self.site_id, page_id)
            return content
        except Exception as e:
            print(f"[⚠] Content-Laden fehlgeschlagen: {e}")
            return None

    def _build_properties(
        self,
        title: str,
        section: str,
        notebook: str,
        created: Optional[str],
        modified: Optional[str]
    ) -> Dict[str, Any]:
        """Notion-Properties erstellen."""
        properties = {
            "Name": {
                "title": [
                    {"type": "text", "text": {"content": title[:2000]}}
                ]
            }
        }

        # Optional: Section als Select
        if section:
            properties["Section"] = {
                "select": {"name": section[:100]}
            }

        # Optional: Notebook als Select
        if notebook:
            properties["Notebook"] = {
                "select": {"name": notebook[:100]}
            }

        # Optional: Created-Datum
        if created:
            properties["Created"] = {
                "date": {"start": created}
            }

        # Optional: Modified-Datum
        if modified:
            properties["Modified"] = {
                "date": {"start": modified}
            }

        return properties

    def _add_table_to_page(self, page_id: str, table: List[List[str]]) -> None:
        """Tabelle als Blöcke zu Notion-Page hinzufügen."""
        if not table:
            return

        # Tabellen-Header
        if len(table) > 0:
            header = table[0]
            header_text = " | ".join(header)
            self.notion.append_blocks(page_id, [{
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": f"📊 **{header_text}**"}}]
                }
            }])

        # Tabellen-Zeilen
        for row in table[1:]:
            row_text = " | ".join(row)
            self.notion.append_blocks(page_id, [{
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": row_text}}]
                }
            }])

    def process_batch(
        self,
        pages: List[Dict[str, Any]],
        database_id: str,
        section_name: str = "",
        notebook_name: str = ""
    ) -> Tuple[int, int]:
        """
        Batch von Pages verarbeiten.
        
        Args:
            pages: Liste von OneNote-Pages
            database_id: Notion-Datenbank-ID
            section_name: Section-Name
            notebook_name: Notebook-Name
            
        Returns:
            (Erfolge, Fehler) Tuple
        """
        success_count = 0
        error_count = 0

        for page in pages:
            result = self.map_page_to_notion(
                page,
                database_id,
                section_name,
                notebook_name
            )

            if result:
                success_count += 1
            else:
                error_count += 1

        return success_count, error_count
