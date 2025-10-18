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

from .html_parser import html_to_blocks_and_tables, append_table


class ContentMapper:
    """Orchestriert die Konvertierung von OneNote-Content zu Notion."""

    def __init__(self, notion_client, ms_graph_client, site_id: str):
        """
        Initialisierung.
        
        Args:
            notion_client: NotionClient-Instanz
            ms_graph_client: MSGraphClient-Instanz
            site_id: SharePoint-Site-ID
        """
        self.notion = notion_client
        self.ms_graph = ms_graph_client
        self.site_id = site_id

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

            # 3. HTML parsen - MIT INLINE BILDERN!
            blocks, tables = html_to_blocks_and_tables(
                html_content,
                self.site_id,
                self.ms_graph,
                self.notion
            )

            # 4. Web-URL extrahieren
            web_url = onenote_page.get("links", {}).get("oneNoteWebUrl", {}).get("href")
            
            # 5. Notion-Properties erstellen
            properties = self._build_properties(
                title=page_title,
                page_id=page_id,
                database_id=database_id,
                section=section_name,
                notebook=notebook_name,
                created=created_time,
                modified=modified_time,
                web_url=web_url
            )

            # 6. Prüfe ob Page bereits existiert (Update vs. Create)
            existing_page_id = self.notion.find_page_by_property(
                database_id,
                "OneNotePageId",
                page_id
            )
            
            if existing_page_id:
                # Update: Properties aktualisieren UND Blöcke löschen/neu hinzufügen
                self.notion.update_page(existing_page_id, properties)
                notion_page_id = existing_page_id
                print(f"[🔄] Page aktualisiert: {page_title}")
                # WICHTIG: Bei Updates müssen auch Blöcke neu geschrieben werden!
                # Alte Blöcke können nicht gelöscht werden, aber neue werden hinzugefügt
            else:
                # Create: Neue Page erstellen
                notion_page_id = self.notion.create_page(
                    parent_id=database_id,
                    properties=properties
                )
                
                if not notion_page_id:
                    print(f"[❌] Page-Erstellung fehlgeschlagen: {page_title}")
                    return None

            # 7. Blöcke hinzufügen (Bilder sind bereits INLINE!)
            if blocks:
                # FAIL-SAFE: Validiere alle Blöcke vor dem Senden
                validated_blocks = self._validate_blocks(blocks)
                self.notion.append_blocks(notion_page_id, validated_blocks)

            # 8. Tabellen als echte Table-Blöcke hinzufügen
            if tables:
                for table in tables:
                    append_table(self.notion, notion_page_id, table)

            print(f"[✅] Page importiert: {page_title}")
            return notion_page_id

        except Exception as e:
            print(f"[❌] Page-Import fehlgeschlagen ({onenote_page.get('title', 'Unknown')}): {e}")
            return None

    # _process_assets wurde entfernt - Bilder werden jetzt inline in html_to_blocks_and_tables verarbeitet!

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
        page_id: str,
        database_id: str,
        section: str = "",
        notebook: str = "",
        created: Optional[str] = None,
        modified: Optional[str] = None,
        web_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Notion-Properties erstellen.
        
        Nur Properties setzen, die in der Datenbank existieren!
        """
        # Hole Datenbank-Schema
        try:
            db = self.notion.get_database(database_id)
            db_props = db.get("properties", {})
            print(f"[📋] Datenbank-Properties: {list(db_props.keys())}")
            print(f"[📋] section_name='{section}', notebook='{notebook}'")
        except Exception as e:
            print(f"[❌] Fehler beim Abrufen der DB-Properties: {e}")
            db_props = {}
        
        properties = {}
        
        # Title (immer erforderlich)
        title_key = next((k for k, v in db_props.items() if v.get("type") == "title"), "Name")
        properties[title_key] = {
            "title": [{"type": "text", "text": {"content": title[:200]}}]
        }
        
        # OneNotePageId - nur wenn Property existiert
        if "OneNotePageId" in db_props:
            prop_type = db_props["OneNotePageId"].get("type")
            if prop_type == "rich_text":
                properties["OneNotePageId"] = {
                    "rich_text": [{"type": "text", "text": {"content": page_id}}]
                }
            elif prop_type == "url":
                properties["OneNotePageId"] = {"url": page_id}
        
        # Section - nur wenn Property existiert
        if section and "Section" in db_props:
            prop_type = db_props["Section"].get("type")
            print(f"[🔍] Section-Property gefunden: Type={prop_type}, Value={section}")
            if prop_type == "select":
                properties["Section"] = {"select": {"name": section}}
                print(f"[✅] Section gesetzt: {section}")
            else:
                print(f"[⚠] Section-Property ist nicht vom Typ 'select', sondern '{prop_type}'")
        elif section:
            print(f"[⚠] Section-Property existiert nicht in Datenbank (section_name='{section}')")
        
        # SourceURL - nur wenn Property existiert
        if web_url and "SourceURL" in db_props and db_props["SourceURL"].get("type") == "url":
            properties["SourceURL"] = {"url": web_url}
        
        # Notebook - nur wenn Property existiert
        if notebook and "Notebook" in db_props:
            properties["Notebook"] = {
                "rich_text": [{"type": "text", "text": {"content": notebook}}]
            }
        
        # Created - nur wenn Property existiert
        if created and "Created" in db_props and db_props["Created"].get("type") == "date":
            properties["Created"] = {"date": {"start": created}}
        
        # Modified - nur wenn Property existiert
        if modified and "Modified" in db_props and db_props["Modified"].get("type") == "date":
            properties["Modified"] = {"date": {"start": modified}}
        
        return properties

    def _validate_blocks(self, blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Validiere alle Blöcke und stelle sicher dass rich_text <= 2000 Zeichen.
        
        FAIL-SAFE gegen Notion API Validierungsfehler.
        """
        validated = []
        
        for block in blocks:
            block_type = block.get("type")
            if not block_type:
                continue
            
            # Block-Content holen
            content = block.get(block_type, {})
            rich_text = content.get("rich_text", [])
            
            # Validiere jedes rich_text-Element
            new_rich_text = []
            for rt in rich_text:
                if rt.get("type") == "text":
                    text_content = rt.get("text", {}).get("content", "")
                    text_length = len(text_content)
                    
                    if text_length > 2000:
                        # Zu lang! Teile in 2000er-Chunks
                        link = rt.get("text", {}).get("link")
                        for i in range(0, text_length, 2000):
                            chunk = text_content[i:i+2000]
                            if link:
                                new_rich_text.append({"type": "text", "text": {"content": chunk, "link": link}})
                            else:
                                new_rich_text.append({"type": "text", "text": {"content": chunk}})
                    else:
                        new_rich_text.append(rt)
                else:
                    new_rich_text.append(rt)
            
            # Wenn rich_text zu lang wurde, teile in mehrere Blöcke
            if len(new_rich_text) > 0:
                # Berechne Gesamt-Länge
                total_length = sum(len(rt.get("text", {}).get("content", "")) for rt in new_rich_text if rt.get("type") == "text")
                
                if total_length <= 2000:
                    # Alles OK: Ein Block
                    content["rich_text"] = new_rich_text
                    validated.append(block)
                else:
                    # Zu lang: Teile in mehrere Blöcke
                    current_block_rt = []
                    current_length = 0
                    
                    for rt in new_rich_text:
                        rt_length = len(rt.get("text", {}).get("content", "")) if rt.get("type") == "text" else 0
                        
                        if current_length + rt_length > 2000 and current_block_rt:
                            # Speichere aktuellen Block
                            new_block = {
                                "object": "block",
                                "type": block_type,
                                block_type: {"rich_text": current_block_rt}
                            }
                            validated.append(new_block)
                            current_block_rt = [rt]
                            current_length = rt_length
                        else:
                            current_block_rt.append(rt)
                            current_length += rt_length
                    
                    # Letzten Block hinzufügen
                    if current_block_rt:
                        new_block = {
                            "object": "block",
                            "type": block_type,
                            block_type: {"rich_text": current_block_rt}
                        }
                        validated.append(new_block)
            else:
                # Leerer Block - überspringe
                pass
        
        return validated

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
