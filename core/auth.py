"""
Gemeinsame Authentifizierung für Microsoft Graph und Notion API.
"""
import os
import sys
from typing import Dict, Any, Optional
import msal
import requests
from dataclasses import dataclass


@dataclass
class AuthConfig:
    """Konfiguration für Authentifizierung."""
    ms_client_id: str
    ms_tenant_id: str = "consumers"
    ms_scopes: Optional[list] = None
    notion_token: Optional[str] = None

    def __post_init__(self):
        if self.ms_scopes is None:
            self.ms_scopes = ["Notes.Read.All", "Sites.Read.All"]


class MicrosoftAuthenticator:
    """Microsoft Graph Authentifizierung mit MSAL."""

    def __init__(self, config: AuthConfig):
        self.config = config
        self.app = msal.PublicClientApplication(
            client_id=config.ms_client_id,
            authority=f"https://login.microsoftonline.com/{config.ms_tenant_id}"
        )
        self._token = None

    def acquire_token_device_code(self) -> Dict[str, Any]:
        """Token über Device Code Flow erwerben."""
        flow = self.app.initiate_device_flow(scopes=self.config.ms_scopes)
        if "user_code" not in flow:
            raise RuntimeError(f"Device flow failed: {flow}")

        print("\n=== Microsoft Sign-in ===")
        print("Go to:", flow['verification_uri'])
        print("Enter code:", flow['user_code'])
        print("Waiting for authentication...")
        sys.stdout.flush()

        result = self.app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise RuntimeError(f"Could not acquire token: {result}")

        self._token = result
        return result

    @property
    def token(self) -> str:
        """Access Token abrufen."""
        if not self._token:
            self._token = self.acquire_token_device_code()
        return self._token["access_token"]

    @property
    def headers(self) -> Dict[str, str]:
        """HTTP Headers für Microsoft Graph API."""
        return {"Authorization": f"Bearer {self.token}"}


class NotionAuthenticator:
    """Notion API Authentifizierung."""

    def __init__(self, token: str):
        self.token = token
        self.version = "2022-06-28"

    @property
    def headers(self) -> Dict[str, str]:
        """HTTP Headers für Notion API."""
        return {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": self.version,
            "accept": "application/json",
            "content-type": "application/json"
        }

    @property
    def headers_no_content_type(self) -> Dict[str, str]:
        """HTTP Headers ohne Content-Type (für Multipart-Uploads)."""
        return {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": self.version,
            "accept": "application/json"
        }


class AuthManager:
    """Zentrale Authentifizierungsverwaltung."""

    def __init__(self):
        self._ms_auth = None
        self._notion_auth = None
        self._config = None

    def initialize(self, config: Optional[AuthConfig] = None):
        """Auth-Manager mit Konfiguration initialisieren."""
        if config is None:
            config = AuthConfig(
                ms_client_id=os.getenv("MS_CLIENT_ID", ""),
                ms_tenant_id=os.getenv("MS_TENANT_ID", "consumers"),
                ms_scopes=[s.strip() for s in os.getenv("MS_GRAPH_SCOPES", "Notes.Read.All,Sites.Read.All").split(",")],
                notion_token=os.getenv("NOTION_TOKEN", "")
            )

        if not config.ms_client_id:
            raise ValueError("MS_CLIENT_ID environment variable is required")
        if not config.notion_token:
            raise ValueError("NOTION_TOKEN environment variable is required")

        self._config = config
        self._ms_auth = MicrosoftAuthenticator(config)
        self._notion_auth = NotionAuthenticator(config.notion_token)

    @property
    def microsoft(self) -> MicrosoftAuthenticator:
        """Microsoft Graph Authenticator."""
        if not self._ms_auth:
            raise RuntimeError("AuthManager not initialized. Call initialize() first.")
        return self._ms_auth

    @property
    def notion(self) -> NotionAuthenticator:
        """Notion API Authenticator."""
        if not self._notion_auth:
            raise RuntimeError("AuthManager not initialized. Call initialize() first.")
        return self._notion_auth


# Globaler Auth-Manager
auth_manager = AuthManager()
