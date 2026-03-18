"""
Notion API Client mit gemeinsamen Operationen für alle Migrationstools.
"""
import time
import requests
from typing import Dict, List, Any, Optional
from .auth import auth_manager


class NotionAPIError(Exception):
    """Exception für Notion API Fehler."""
    pass


class NotionClient:
    """Wrapper für Notion API Operationen."""

    def __init__(self, auth_manager_instance=None):
        self.auth = auth_manager_instance or auth_manager
        self._pinned_token = None  # Fester Token fuer Seiten-Migration (file_upload-Kompatibilitaet)

    def _normalize_uuid(self, uuid_str: str) -> str:
        """
        Normalisiere Notion-UUID Format.
        Akzeptiert: 'Y28f2d0f82ce180749f1ff29284908c89' → 'Y28f2d0f-82ce-1807-49f1-ff29284908c89'
        """
        if not uuid_str:
            raise NotionAPIError("Database ID cannot be empty")
        
        # Entferne Leerzeichen
        uuid_str = uuid_str.strip()
        
        # Entferne vorhandene Bindestriche
        clean = uuid_str.replace("-", "")
        
        # Wenn bereits normalisiert (36 Zeichen mit Bindestrichen)
        if len(uuid_str) == 36 and uuid_str.count("-") == 4:
            return uuid_str
        
        # Akzeptiere 32-Zeichen UUIDs
        if len(clean) == 32:
            return f"{clean[0:8]}-{clean[8:12]}-{clean[12:16]}-{clean[16:20]}-{clean[20:32]}"
        
        # Für alle anderen Formate: Warnung + original zurück
        if len(clean) < 32 or len(clean) > 36:
            print(f"[⚠] Warnung: Unerwartetes UUID-Format ({len(clean)} Zeichen): {uuid_str}")
            print(f"[i] Erwartet: 32 oder 36 Zeichen")
            print(f"[i] Tipps: Prüfen Sie die Database-ID in Notion (Share-Button → Copy link)")
        
        return uuid_str

    def pin_token(self):
        """Token fuer die Dauer einer Seiten-Migration pinnen.

        Alle nachfolgenden Requests (Upload + Append) verwenden denselben Token,
        damit file_upload-IDs beim append_blocks erkannt werden.
        """
        self._pinned_token = self.auth.notion_pool.next()

    def unpin_token(self):
        """Token-Pin aufheben, zurueck zu Round-Robin."""
        self._pinned_token = None

    def _get_token(self):
        """Aktuellen Token holen (gepinnt oder Round-Robin)."""
        return self._pinned_token or self.auth.notion_pool.next()

    def _get_headers(self) -> Dict[str, str]:
        """Headers via gepinnten Token oder Round-Robin holen."""
        return self._get_token().headers

    def _get_headers_no_content_type(self) -> Dict[str, str]:
        """Headers ohne Content-Type via gepinnten Token oder Round-Robin holen."""
        return self._get_token().headers_no_content_type

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Generische HTTP-Anfrage an Notion API mit Retry bei Verbindungsfehlern."""
        url = f"https://api.notion.com/v1{endpoint}"
        last_exc = None

        for attempt in range(3):
            if attempt > 0:
                time.sleep(1.5 * attempt)
            try:
                headers = self._get_headers()
                if method.lower() == "get":
                    response = requests.get(url, headers=headers, **kwargs)
                elif method.lower() == "post":
                    response = requests.post(url, headers=headers, **kwargs)
                elif method.lower() == "patch":
                    response = requests.patch(url, headers=headers, **kwargs)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                # Rate limit: kurze Pause nach jedem Request
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 2))
                    time.sleep(retry_after)
                    continue

                # Server-Fehler (502/503/504): Retry mit Backoff
                if response.status_code >= 500:
                    wait = 2 * (attempt + 1)
                    print(f"[⏳] Notion API {response.status_code}, Retry nach {wait}s (Versuch {attempt + 1}/3)")
                    time.sleep(wait)
                    if attempt == 2:
                        raise NotionAPIError(f"Notion API error: {response.status_code} - {response.text}")
                    continue

                if not response.ok:
                    raise NotionAPIError(f"Notion API error: {response.status_code} - {response.text}")

                return response.json()

            except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError) as e:
                last_exc = e
                continue

        raise last_exc or NotionAPIError("Request failed after retries")

    def get_database(self, database_id: str) -> Dict[str, Any]:
        """Datenbank-Informationen abrufen."""
        database_id = self._normalize_uuid(database_id)
        return self._make_request("GET", f"/databases/{database_id}")

    def query_database(
        self, 
        database_id: str, 
        filter_obj: Optional[Dict] = None,
        start_cursor: Optional[str] = None,
        page_size: int = 100
    ) -> Dict[str, Any]:
        """Datenbank abfragen mit Pagination-Support."""
        database_id = self._normalize_uuid(database_id)
        data = {"page_size": min(page_size, 100)}
        
        if filter_obj:
            data["filter"] = filter_obj
        if start_cursor:
            data["start_cursor"] = start_cursor

        return self._make_request("POST", f"/databases/{database_id}/query", json=data)

    def create_database(self, parent_page_id: str, title: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        """Neue Datenbank erstellen."""
        data = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": title}}],
            "properties": properties
        }
        return self._make_request("POST", "/databases", json=data)

    def update_database(self, database_id: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        """Datenbank-Properties aktualisieren."""
        return self._make_request("PATCH", f"/databases/{database_id}", json={"properties": properties})

    def create_page(self, parent_id: str, properties: Dict[str, Any], children: Optional[List[Dict]] = None) -> str:
        """Neue Seite erstellen."""
        # Korrigiere UUID-Format falls nötig
        parent_id = self._normalize_uuid(parent_id)
        
        data = {
            "parent": {"type": "database_id", "database_id": parent_id},
            "properties": properties
        }

        if children:
            data["children"] = children[:100]  # Notion-Limit

        result = self._make_request("POST", "/pages", json=data)
        return result["id"]

    def update_page(self, page_id: str, properties: Dict[str, Any]) -> None:
        """Seite aktualisieren."""
        self._make_request("PATCH", f"/pages/{page_id}", json={"properties": properties})
    
    def update_page_archived(self, page_id: str, archived: bool = True) -> None:
        """Seite archivieren oder wiederherstellen."""
        self._make_request("PATCH", f"/pages/{page_id}", json={"archived": archived})

    def get_block_children(self, block_id: str, start_cursor: Optional[str] = None) -> Dict[str, Any]:
        """
        Kind-Blöcke eines Blocks/einer Seite abrufen (mit Pagination).
        
        Returns:
            Dict mit 'results', 'has_more', 'next_cursor'
        """
        params = {"page_size": 100}
        if start_cursor:
            params["start_cursor"] = start_cursor
        
        return self._make_request("GET", f"/blocks/{block_id}/children", params=params)
    
    def get_all_block_children(self, block_id: str) -> List[Dict[str, Any]]:
        """Alle Kind-Blöcke eines Blocks/einer Seite abrufen (alle Seiten)."""
        all_blocks = []
        has_more = True
        cursor = None
        
        while has_more:
            response = self.get_block_children(block_id, start_cursor=cursor)
            all_blocks.extend(response.get("results", []))
            
            has_more = response.get("has_more", False)
            cursor = response.get("next_cursor")
        
        return all_blocks
    
    def update_block(self, block_id: str, content: Optional[Dict[str, Any]] = None, archived: bool = False) -> None:
        """
        Block aktualisieren.
        
        Args:
            block_id: Block-ID
            content: Block-Content (z.B. {"paragraph": {"rich_text": [...]}})
            archived: True zum Archivieren/Löschen
        """
        data = {}
        if content:
            data.update(content)
        if archived:
            data["archived"] = archived
        
        if data:
            self._make_request("PATCH", f"/blocks/{block_id}", json=data)
    
    def append_blocks(self, block_id: str, children: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Blöcke an bestehende Seite anhängen.

        Bei Batch-Fehlern wird der Batch halbiert und erneut versucht (Bisection).
        So wird der fehlerhafte Block isoliert und übersprungen, statt den
        gesamten Batch zu verlieren.

        Returns:
            Dict mit 'results' vom letzten erfolgreichen Batch,
            plus 'failed_blocks' (int) und 'total_blocks' (int).
        """
        url = f"/blocks/{block_id}/children"
        result = None
        failed_blocks = 0
        total_blocks = len(children)

        def _send_batch(batch: List[Dict]) -> bool:
            """Batch senden. Bei Fehler: halbieren und einzeln retrien."""
            nonlocal result, failed_blocks
            try:
                result = self._make_request("PATCH", url, json={"children": batch})
                time.sleep(self.auth.notion_pool.batch_sleep)
                return True
            except Exception as e:
                if len(batch) == 1:
                    # Einzelner Block fehlgeschlagen — überspringen und loggen
                    failed_blocks += 1
                    btype = batch[0].get("type", "?")
                    content_preview = ""
                    if btype in batch[0]:
                        rt = batch[0][btype].get("rich_text", [])
                        texts = [t.get("text", {}).get("content", "")[:40] for t in rt[:2] if t.get("type") == "text"]
                        content_preview = " ".join(texts)
                    print(f"[⛔] Block übersprungen ({btype}): {e}")
                    if content_preview:
                        print(f"     Inhalt: \"{content_preview}...\"")
                    return False

                # Batch halbieren und beide Hälften versuchen
                mid = len(batch) // 2
                print(f"[🔄] Batch ({len(batch)} Blöcke) fehlgeschlagen, halbiere... ({e})")
                _send_batch(batch[:mid])
                time.sleep(self.auth.notion_pool.batch_sleep)
                _send_batch(batch[mid:])
                return False

        # Blöcke in Batches von 50 senden (Notion-Limit)
        for i in range(0, total_blocks, 50):
            batch = children[i:i+50]
            _send_batch(batch)

        if failed_blocks:
            print(f"[⚠] {failed_blocks} von {total_blocks} Blöcken fehlgeschlagen (übersprungen)")

        result = result or {}
        result["_failed_blocks"] = failed_blocks
        result["_total_blocks"] = total_blocks
        return result

    def find_page_by_property(self, database_id: str, property_name: str, property_value: str) -> Optional[str]:
        """Seite anhand einer Property finden (nur ID)."""
        result = self.find_page_with_properties(database_id, property_name, property_value)
        return result["id"] if result else None
    
    def find_page_with_properties(self, database_id: str, property_name: str, property_value: str) -> Optional[Dict[str, Any]]:
        """
        Seite anhand einer Property finden (vollständige Page inkl. Properties).
        
        Returns:
            Vollständiges Page-Objekt oder None
        """
        # Versuche verschiedene Property-Typen
        filters = [
            {"property": property_name, "rich_text": {"equals": property_value}},
            {"property": property_name, "title": {"equals": property_value}},
            {"property": property_name, "url": {"equals": property_value}}
        ]

        for filter_obj in filters:
            try:
                response = self.query_database(database_id, filter_obj)
                results = response.get("results", [])
                if results:
                    return results[0]  # Vollständige Page zurückgeben
            except NotionAPIError:
                continue

        return None
    
    def list_users(self) -> List[Dict[str, Any]]:
        """Alle Benutzer im Workspace abrufen."""
        all_users = []
        has_more = True
        start_cursor = None
        
        while has_more:
            params = {"page_size": 100}
            if start_cursor:
                params["start_cursor"] = start_cursor
            
            response = self._make_request("GET", "/users", params=params)
            all_users.extend(response.get("results", []))
            
            has_more = response.get("has_more", False)
            start_cursor = response.get("next_cursor")
        
        return all_users

    def upload_file(self, filename: str, data: bytes, content_type: Optional[str] = None) -> Optional[str]:
        """
        Datei zu Notion hochladen (2-Schritt File Upload API).
        
        Schritt 1: file_upload erstellen
        Schritt 2: Datei senden (WICHTIG: OHNE Content-Type Header!)
        """
        # Validierung
        if len(data) > 20 * 1024 * 1024:
            print(f"[⚠] Datei zu groß (>20MB): {filename}")
            return None
        
        ct = content_type or "application/octet-stream"

        # WICHTIG: Gepinnten Token verwenden (gleicher Token fuer Upload + Append).
        # Schritt 1: file_upload erstellen
        response = requests.post(
            "https://api.notion.com/v1/file_uploads",
            headers=self._get_headers(),
            json={"filename": filename, "content_type": ct}
        )

        if response.status_code != 200:
            print(f"[⚠] file_upload creation failed: {response.text[:300]}")
            return None

        file_upload_id = response.json().get("id")

        # Schritt 2: Datei senden
        # KRITISCH: Nicht Content-Type manuell setzen!
        # requests.post() mit files= setzt automatisch multipart/form-data mit boundary
        files = {"file": (filename, data, ct)}
        upload_response = requests.post(
            f"https://api.notion.com/v1/file_uploads/{file_upload_id}/send",
            headers=self._get_headers_no_content_type(),
            files=files
        )

        if upload_response.status_code != 200:
            print(f"[⚠] file send failed: {upload_response.text[:300]}")
            return None

        return file_upload_id

    def create_image_block(self, file_upload_id: str) -> Dict[str, Any]:
        """Bild-Block aus Upload-ID erstellen."""
        return {
            "object": "block",
            "type": "image",
            "image": {"type": "file_upload", "file_upload": {"id": file_upload_id}}
        }

    def create_file_block(self, file_upload_id: str) -> Dict[str, Any]:
        """Datei-Block aus Upload-ID erstellen."""
        return {
            "object": "block",
            "type": "file",
            "file": {"type": "file_upload", "file_upload": {"id": file_upload_id}}
        }

    def create_table_block(self, rows: List[List[str]], has_column_header: bool = False) -> Dict[str, Any]:
        """Tabellen-Block erstellen."""
        return {
            "object": "block",
            "type": "table",
            "table": {
                "table_width": max(len(row) for row in rows) if rows else 0,
                "has_column_header": has_column_header,
                "has_row_header": False
            }
        }

    def create_table_row_blocks(self, rows: List[List[str]]) -> List[Dict[str, Any]]:
        """Tabellenzeilen-Blöcke erstellen."""
        blocks = []
        for row in rows:
            cells = [[{"type": "text", "text": {"content": cell}}] for cell in row]
            blocks.append({
                "object": "block",
                "type": "table_row",
                "table_row": {"cells": cells}
            })
        return blocks


# Convenience-Funktionen
def get_notion_client() -> NotionClient:
    """Globalen Notion-Client abrufen."""
    return NotionClient()
