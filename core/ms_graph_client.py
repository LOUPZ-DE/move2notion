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
        """
        Sections eines Notebooks abrufen (inkl. Sections in Section Groups).
        
        OneNote kann Sections direkt im Notebook haben ODER in Section Groups
        (verschachtelte Ordner). Diese Methode lädt beide.
        """
        all_sections = []
        
        # 1. Direkte Sections abrufen
        notebook = self._make_request("GET", f"/sites/{site_id}/onenote/notebooks/{notebook_id}")
        sections_url = notebook.get("sectionsUrl")

        if sections_url:
            if sections_url.startswith(self.BASE_URL):
                sections_url = sections_url.replace(self.BASE_URL, "")
            result = self._make_request("GET", f"{sections_url}?$top=200")
            direct_sections = result.get("value", [])
            all_sections.extend(direct_sections)
        
        # 2. Section Groups abrufen und deren Sections laden
        section_groups_url = notebook.get("sectionGroupsUrl")
        if section_groups_url:
            if section_groups_url.startswith(self.BASE_URL):
                section_groups_url = section_groups_url.replace(self.BASE_URL, "")
            
            try:
                groups_result = self._make_request("GET", f"{section_groups_url}?$top=200")
                section_groups = groups_result.get("value", [])
                
                # DEBUG: Zeige gefundene Section Groups
                print(f"[🔍] {len(section_groups)} Section Group(s) gefunden:")
                for g in section_groups:
                    print(f"    - {g.get('displayName', 'Unbekannt')}")
                
                # Rekursiv Sections aus JEDER Gruppe laden (Fehler pro Gruppe abfangen!)
                for group in section_groups:
                    group_name = group.get("displayName", "Unbekannt")
                    try:
                        print(f"[📂] Lade Sections aus Gruppe: {group_name}")
                        group_sections = self._get_sections_from_group(site_id, group)
                        print(f"[📂] {len(group_sections)} Section(s) in '{group_name}' gefunden")
                        all_sections.extend(group_sections)
                    except Exception as group_error:
                        # Fehler nur für diese Gruppe loggen, andere Gruppen weiter verarbeiten
                        print(f"[⚠] Section Group '{group_name}' konnte nicht geladen werden: {group_error}")
                        import traceback
                        traceback.print_exc()
                    
            except Exception as e:
                # Fehler beim Abrufen der Section Groups Liste
                print(f"[⚠] Section Groups konnten nicht abgerufen werden: {e}")
                import traceback
                traceback.print_exc()
        
        return all_sections
    
    def _get_sections_from_group(self, site_id: str, group: Dict[str, Any], depth: int = 0) -> List[Dict[str, Any]]:
        """Rekursiv Sections aus einer Section Group laden (inkl. verschachtelter Gruppen)."""
        if depth > 5:  # Max Verschachtelungstiefe
            return []
        
        sections = []
        group_name = group.get("displayName", "")
        
        # Sections in dieser Gruppe
        sections_url = group.get("sectionsUrl")
        if sections_url:
            if sections_url.startswith(self.BASE_URL):
                sections_url = sections_url.replace(self.BASE_URL, "")
            try:
                result = self._make_request("GET", f"{sections_url}?$top=200")
                group_sections = result.get("value", [])
                # Prefix mit Gruppen-Name für bessere Übersicht
                for sec in group_sections:
                    if group_name:
                        sec["_groupName"] = group_name
                    sections.append(sec)
            except Exception:
                pass
        
        # Verschachtelte Section Groups
        nested_groups_url = group.get("sectionGroupsUrl")
        if nested_groups_url:
            if nested_groups_url.startswith(self.BASE_URL):
                nested_groups_url = nested_groups_url.replace(self.BASE_URL, "")
            try:
                result = self._make_request("GET", f"{nested_groups_url}?$top=200")
                nested_groups = result.get("value", [])
                for nested in nested_groups:
                    nested_sections = self._get_sections_from_group(site_id, nested, depth + 1)
                    sections.extend(nested_sections)
            except Exception:
                pass
        
        return sections

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
    
    def get_planner_plan_details(self, plan_id: str) -> Dict[str, Any]:
        """Planner-Plan Details abrufen (inkl. Category-Descriptions für Tags)."""
        endpoint = f"/planner/plans/{plan_id}/details"
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
            for member in result.get("value", []):
                # Nur echte User, keine Service Principals, Geräte, etc.
                member_type = member.get("@odata.type", "")
                if member_type == "#microsoft.graph.user":
                    members.append(member)

            next_link = result.get("@odata.nextLink")
            if next_link:
                endpoint = next_link.replace(self.BASE_URL, "")
            else:
                endpoint = None

        return members
    
    def get_user(self, user_id: str) -> Dict[str, Any]:
        """Einzelnen Benutzer anhand der User-ID abrufen."""
        endpoint = f"/users/{user_id}"
        return self._make_request("GET", endpoint)


# Convenience-Funktionen
def get_ms_graph_client() -> MSGraphClient:
    """Globalen Microsoft Graph-Client abrufen."""
    return MSGraphClient()
