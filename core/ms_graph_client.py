"""
Microsoft Graph API Client für verschiedene Microsoft-Dienste.
"""
import requests
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse
from .auth import auth_manager


class MSGraphAPIError(Exception):
    """Exception für Microsoft Graph API Fehler."""
    pass


class MSGraphClient:
    """Client für Microsoft Graph API."""

    BASE_URL = "https://graph.microsoft.com/v1.0"

    def __init__(self, auth_manager_instance=None):
        self.auth = auth_manager_instance or auth_manager

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Generische HTTP-Anfrage an Microsoft Graph API."""
        url = f"{self.BASE_URL}{endpoint}"

        if method.lower() == "get":
            response = requests.get(url, headers=self.auth.microsoft.headers, **kwargs)
        elif method.lower() == "post":
            response = requests.post(url, headers=self.auth.microsoft.headers, **kwargs)
        elif method.lower() == "patch":
            response = requests.patch(url, headers=self.auth.microsoft.headers, **kwargs)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        if not response.ok:
            raise MSGraphAPIError(f"Microsoft Graph API error: {response.status_code} - {response.text}")

        return response.json()

    def resolve_site_id_from_url(self, site_url: str) -> str:
        """Site-ID aus SharePoint-URL auflösen."""
        parsed = urlparse(site_url)
        host = parsed.netloc
        path = parsed.path.lstrip("/")

        if path.startswith("sites/"):
            rel = path[len("sites/"):]
            endpoint = f"/sites/{host}:/sites/{rel}?$select=id,displayName"
        elif path.startswith("teams/"):
            rel = path[len("teams/"):]
            endpoint = f"/sites/{host}:/teams/{rel}?$select=id,displayName"
        else:
            endpoint = f"/sites/{host}?$select=id,displayName"

        result = self._make_request("GET", endpoint)
        return result["id"]

    def list_site_notebooks(self, site_id: str) -> List[Dict[str, Any]]:
        """OneNote-Notebooks einer Site auflisten."""
        notebooks = []
        endpoint = f"/sites/{site_id}/onenote/notebooks?$top=200"

        while endpoint:
            result = self._make_request("GET", endpoint)
            notebooks.extend(result.get("value", []))

            # Nächste Seite laden falls vorhanden
            next_link = result.get("@odata.nextLink")
            if next_link:
                # Extrahiere Endpoint aus voller URL
                endpoint = next_link.replace(self.BASE_URL, "")
            else:
                endpoint = None

        return notebooks

    def get_notebook_sections(self, site_id: str, notebook_id: str) -> List[Dict[str, Any]]:
        """Sections eines Notebooks abrufen."""
        # Zuerst Notebook-Details abrufen um sectionsUrl zu bekommen
        notebook = self._make_request("GET", f"/sites/{site_id}/onenote/notebooks/{notebook_id}")
        sections_url = notebook.get("sectionsUrl")

        if not sections_url:
            raise MSGraphAPIError("Notebook entry missing sectionsUrl")

        # Entferne Base-URL falls vorhanden
        if sections_url.startswith(self.BASE_URL):
            sections_url = sections_url.replace(self.BASE_URL, "")

        result = self._make_request("GET", f"{sections_url}?$top=200")
        return result.get("value", [])

    def list_pages_for_section(self, site_id: str, section_id: str, since: Optional[str] = None) -> List[Dict[str, Any]]:
        """Seiten einer Section auflisten."""
        # Zuerst Section-Details abrufen um pagesUrl zu bekommen
        section = self._make_request("GET", f"/sites/{site_id}/onenote/sections/{section_id}")
        pages_url = section.get("pagesUrl")

        if not pages_url:
            return []

        # Entferne Base-URL falls vorhanden
        if pages_url.startswith(self.BASE_URL):
            pages_url = pages_url.replace(self.BASE_URL, "")

        # Query-Parameter hinzufügen
        url = f"{pages_url}?$top=100"
        if since:
            url += f"&$filter=lastModifiedDateTime ge {since}T00:00:00Z"

        pages = []
        current_url = url

        while current_url:
            result = self._make_request("GET", current_url)
            pages.extend(result.get("value", []))

            # Nächste Seite laden falls vorhanden
            next_link = result.get("@odata.nextLink")
            if next_link and next_link.startswith(self.BASE_URL):
                current_url = next_link.replace(self.BASE_URL, "")
            else:
                current_url = None

        return pages

    def get_page_content(self, site_id: str, page_id: str) -> bytes:
        """HTML-Inhalt einer OneNote-Seite abrufen."""
        url = f"{self.BASE_URL}/sites/{site_id}/onenote/pages/{page_id}/content"
        response = requests.get(url, headers=self.auth.microsoft.headers)

        if not response.ok:
            raise MSGraphAPIError(f"Page content fetch failed: {response.status_code} - {response.text}")

        return response.content

    def get_resource_content(self, site_id: str, resource_id: str) -> bytes:
        """Binärinhalt einer OneNote-Ressource abrufen."""
        url = f"{self.BASE_URL}/sites/{site_id}/onenote/resources/{resource_id}/content"
        response = requests.get(url, headers=self.auth.microsoft.headers)

        if not response.ok:
            raise MSGraphAPIError(f"Resource fetch failed: {response.status_code} - {response.text}")

        return response.content

    def list_users(self) -> List[Dict[str, Any]]:
        """Benutzer auflisten (für Personen-Mapping)."""
        users = []
        endpoint = "/users?$top=100"

        while endpoint:
            result = self._make_request("GET", endpoint)
            users.extend(result.get("value", []))

            # Nächste Seite laden falls vorhanden
            next_link = result.get("@odata.nextLink")
            if next_link:
                endpoint = next_link.replace(self.BASE_URL, "")
            else:
                endpoint = None

        return users

    # ===== Planner-API-Methoden =====

    def get_planner_plan(self, plan_id: str) -> Dict[str, Any]:
        """Planner-Plan Details abrufen."""
        endpoint = f"/planner/plans/{plan_id}"
        return self._make_request("GET", endpoint)

    def list_planner_buckets(self, plan_id: str) -> List[Dict[str, Any]]:
        """Alle Buckets eines Planner-Plans abrufen."""
        buckets = []
        endpoint = f"/planner/plans/{plan_id}/buckets"

        while endpoint:
            result = self._make_request("GET", endpoint)
            buckets.extend(result.get("value", []))

            # Nächste Seite laden falls vorhanden
            next_link = result.get("@odata.nextLink")
            if next_link:
                endpoint = next_link.replace(self.BASE_URL, "")
            else:
                endpoint = None

        return buckets

    def list_planner_tasks(self, plan_id: str) -> List[Dict[str, Any]]:
        """Alle Tasks eines Planner-Plans abrufen."""
        tasks = []
        endpoint = f"/planner/plans/{plan_id}/tasks"

        while endpoint:
            result = self._make_request("GET", endpoint)
            tasks.extend(result.get("value", []))

            # Nächste Seite laden falls vorhanden
            next_link = result.get("@odata.nextLink")
            if next_link:
                endpoint = next_link.replace(self.BASE_URL, "")
            else:
                endpoint = None

        return tasks

    def get_task_details(self, task_id: str) -> Dict[str, Any]:
        """Detaillierte Task-Informationen abrufen (inkl. Beschreibung, Checklisten)."""
        endpoint = f"/planner/tasks/{task_id}/details"
        return self._make_request("GET", endpoint)

    def get_group_members(self, group_id: str) -> List[Dict[str, Any]]:
        """Gruppenmitglieder abrufen (für Planner-Zuweisungen)."""
        members = []
        endpoint = f"/groups/{group_id}/members"

        while endpoint:
            result = self._make_request("GET", endpoint)
            members.extend(result.get("value", []))

            # Nächste Seite laden falls vorhanden
            next_link = result.get("@odata.nextLink")
            if next_link:
                endpoint = next_link.replace(self.BASE_URL, "")
            else:
                endpoint = None

        return members


# Convenience-Funktionen
def get_ms_graph_client() -> MSGraphClient:
    """Globalen Microsoft Graph-Client abrufen."""
    return MSGraphClient()
