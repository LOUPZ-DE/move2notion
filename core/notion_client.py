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

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Generische HTTP-Anfrage an Notion API."""
        url = f"https://api.notion.com/v1{endpoint}"

        if method.lower() == "get":
            response = requests.get(url, headers=self.auth.notion.headers, **kwargs)
        elif method.lower() == "post":
            response = requests.post(url, headers=self.auth.notion.headers, **kwargs)
        elif method.lower() == "patch":
            response = requests.patch(url, headers=self.auth.notion.headers, **kwargs)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        if not response.ok:
            raise NotionAPIError(f"Notion API error: {response.status_code} - {response.text}")

        return response.json()

    def get_database(self, database_id: str) -> Dict[str, Any]:
        """Datenbank-Informationen abrufen."""
        database_id = self._normalize_uuid(database_id)
        return self._make_request("GET", f"/databases/{database_id}")

    def query_database(self, database_id: str, filter_obj: Optional[Dict] = None) -> Dict[str, Any]:
        """Datenbank abfragen."""
        database_id = self._normalize_uuid(database_id)
        data = {}
        if filter_obj:
            data["filter"] = filter_obj

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

    def append_blocks(self, block_id: str, children: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Blöcke an bestehende Seite anhängen."""
        url = f"/blocks/{block_id}/children"
        result = None

        # Blöcke in Batches von 50 senden (Notion-Limit)
        for i in range(0, len(children), 50):
            batch = children[i:i+50]
            result = self._make_request("PATCH", url, json={"children": batch})
            time.sleep(0.12)  # Rate limiting

        return result or {}

    def find_page_by_property(self, database_id: str, property_name: str, property_value: str) -> Optional[str]:
        """Seite anhand einer Property finden."""
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
                    return results[0]["id"]
            except NotionAPIError:
                continue

        return None

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
        
        # Schritt 1: file_upload erstellen
        response = requests.post(
            "https://api.notion.com/v1/file_uploads",
            headers=self.auth.notion.headers,
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
            headers=self.auth.notion.headers_no_content_type,  # NUR Authorization + Notion-Version
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
