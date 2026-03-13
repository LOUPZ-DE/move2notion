"""
Gemeinsame Authentifizierung für Microsoft Graph und Notion API.
"""
import os
import sys
import itertools
import threading
from typing import Dict, Any, Optional, List
import msal
import requests
from dataclasses import dataclass
from dotenv import load_dotenv

# Lade .env-Datei
load_dotenv()


@dataclass
class AuthConfig:
    """Konfiguration für Authentifizierung."""
    ms_client_id: str
    ms_tenant_id: str = "consumers"
    ms_scopes: Optional[list] = None
    notion_token: Optional[str] = None
    # Web-spezifische Konfiguration
    ms_client_secret: Optional[str] = None
    redirect_uri: Optional[str] = None
    # Auth-Modus: "delegated" oder "application"
    auth_mode: str = "delegated"

    def __post_init__(self):
        if self.ms_scopes is None:
            self.ms_scopes = ["Notes.Read.All", "Sites.Read.All"]


class MicrosoftAuthenticator:
    """Microsoft Graph Authentifizierung mit MSAL."""

    def __init__(self, config: AuthConfig):
        self.config = config
        self.cache_file = os.path.join(os.path.expanduser("~"), ".ms_notion_migration_token_cache.bin")
        
        # Token-Cache laden/erstellen
        self.cache = msal.SerializableTokenCache()
        if os.path.exists(self.cache_file):
            with open(self.cache_file, "r") as f:
                self.cache.deserialize(f.read())
        
        self.app = msal.PublicClientApplication(
            client_id=config.ms_client_id,
            authority=f"https://login.microsoftonline.com/{config.ms_tenant_id}",
            token_cache=self.cache
        )
        self._token = None

    def _save_cache(self):
        """Token-Cache speichern."""
        if self.cache.has_state_changed:
            with open(self.cache_file, "w") as f:
                f.write(self.cache.serialize())

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
        self._save_cache()
        return result

    @property
    def token(self) -> str:
        """Access Token abrufen (mit automatischem Refresh)."""
        # Versuche zuerst, Token aus Cache zu holen
        accounts = self.app.get_accounts()
        if accounts:
            result = self.app.acquire_token_silent(
                scopes=self.config.ms_scopes,
                account=accounts[0]
            )
            if result and "access_token" in result:
                self._token = result
                self._save_cache()
                return result["access_token"]
        
        # Wenn kein Token im Cache, neuen Token anfordern
        if not self._token:
            self._token = self.acquire_token_device_code()
        return self._token["access_token"]

    @property
    def headers(self) -> Dict[str, str]:
        """HTTP Headers für Microsoft Graph API."""
        return {"Authorization": f"Bearer {self.token}"}


class MicrosoftWebAuthenticator:
    """Microsoft Graph Authentifizierung für Web-Apps (Authorization Code Flow)."""

    def __init__(self, config: AuthConfig):
        if not config.ms_client_secret:
            raise ValueError("MS_CLIENT_SECRET is required for web authentication")
        if not config.redirect_uri:
            raise ValueError("REDIRECT_URI is required for web authentication")
        
        self.config = config
        self.app = msal.ConfidentialClientApplication(
            client_id=config.ms_client_id,
            client_credential=config.ms_client_secret,
            authority=f"https://login.microsoftonline.com/{config.ms_tenant_id}"
        )
        self._token_cache = {}  # Session-basierter Cache (session_id -> token)

    def get_auth_url(self, session_id: str, state: Optional[str] = None) -> str:
        """URL für Login-Weiterleitung generieren."""
        if state is None:
            state = session_id
        
        scopes = self.config.ms_scopes or ["Notes.Read.All", "Sites.Read.All"]
        auth_url = self.app.get_authorization_request_url(
            scopes=scopes,
            redirect_uri=self.config.redirect_uri,
            state=state
        )
        return auth_url

    def acquire_token_by_auth_code(self, code: str, session_id: str) -> Dict[str, Any]:
        """Token über Authorization Code erwerben."""
        scopes = self.config.ms_scopes or ["Notes.Read.All", "Sites.Read.All"]
        result = self.app.acquire_token_by_authorization_code(
            code=code,
            scopes=scopes,
            redirect_uri=self.config.redirect_uri
        )
        
        if "access_token" not in result:
            raise RuntimeError(f"Could not acquire token: {result.get('error_description', result)}")
        
        # Token im Session-Cache speichern
        self._token_cache[session_id] = result
        return result

    def get_token(self, session_id: str) -> Optional[str]:
        """Access Token für Session abrufen (mit automatischem Refresh)."""
        if session_id not in self._token_cache:
            return None
        
        token_data = self._token_cache[session_id]
        
        # Versuche Token zu refreshen falls vorhanden
        if "refresh_token" in token_data:
            scopes = self.config.ms_scopes or ["Notes.Read.All", "Sites.Read.All"]
            result = self.app.acquire_token_by_refresh_token(
                refresh_token=token_data["refresh_token"],
                scopes=scopes
            )
            if result and "access_token" in result:
                self._token_cache[session_id] = result
                return result["access_token"]
        
        # Fallback: Aktuellen Token zurückgeben
        return token_data.get("access_token")

    def get_headers(self, session_id: str) -> Dict[str, str]:
        """HTTP Headers für Microsoft Graph API."""
        token = self.get_token(session_id)
        if not token:
            raise RuntimeError(f"No token available for session {session_id}")
        return {"Authorization": f"Bearer {token}"}

    def clear_session(self, session_id: str):
        """Session-Token löschen (Logout)."""
        if session_id in self._token_cache:
            del self._token_cache[session_id]


class MicrosoftAppAuthenticator:
    """Microsoft Graph Authentifizierung mit Client Credentials Flow (Application Permissions).

    Verwendet Application Permissions (kein User-Login erforderlich).
    Geeignet für Server-zu-Server-Szenarien und automatisierte Pipelines.
    """

    def __init__(self, config: AuthConfig):
        if not config.ms_client_secret:
            raise ValueError("MS_CLIENT_SECRET is required for application authentication")

        self.config = config
        self.app = msal.ConfidentialClientApplication(
            client_id=config.ms_client_id,
            client_credential=config.ms_client_secret,
            authority=f"https://login.microsoftonline.com/{config.ms_tenant_id}"
        )
        self._token = None

    @property
    def token(self) -> str:
        """Access Token abrufen (MSAL cached intern, ca. 1h gültig)."""
        # Client Credentials Flow nutzt immer .default Scope
        result = self.app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )

        if result and "access_token" in result:
            self._token = result
            return result["access_token"]

        if self._token and "access_token" in self._token:
            return self._token["access_token"]

        error_desc = result.get("error_description", "Unknown error") if result else "No result"
        raise RuntimeError(f"Client Credentials token acquisition failed: {error_desc}")

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


class NotionTokenPool:
    """Round-Robin über mehrere Notion API Tokens für höheren Durchsatz.

    Notion erlaubt ~3 Requests/Sekunde pro Integration (API Key).
    Mit mehreren Tokens kann der Durchsatz linear skaliert werden.

    Konfiguration via NOTION_TOKEN (kommasepariert):
        NOTION_TOKEN=secret_abc,secret_def,secret_ghi

    Der Pool trackt aktive Konsumenten (Migrations-Prozesse) und berechnet
    den optimalen Batch-Sleep dynamisch: 0.12s / tokens * workers.
    """

    BASE_SLEEP = 0.12  # Basis-Sleep fuer 1 Token, 1 Worker

    def __init__(self, tokens_str: str):
        token_list = [t.strip() for t in tokens_str.split(",") if t.strip()]
        if not token_list:
            raise ValueError("Mindestens ein NOTION_TOKEN erforderlich")
        self._authenticators = [NotionAuthenticator(t) for t in token_list]
        self._cycle = itertools.cycle(self._authenticators)
        self._lock = threading.Lock()
        self._active_workers = 0

    def next(self) -> NotionAuthenticator:
        """Naechsten Token im Round-Robin holen (thread-safe)."""
        with self._lock:
            return next(self._cycle)

    @property
    def count(self) -> int:
        """Anzahl konfigurierter Tokens."""
        return len(self._authenticators)

    @property
    def primary(self) -> NotionAuthenticator:
        """Erster Token (fuer Kompatibilitaet)."""
        return self._authenticators[0]

    @property
    def batch_sleep(self) -> float:
        """Optimaler Sleep zwischen Batches (dynamisch berechnet).

        Formel: BASE_SLEEP / token_count * max(active_workers, 1)
        - 1 Token, 1 Worker:  0.12s
        - 2 Tokens, 1 Worker: 0.06s
        - 2 Tokens, 2 Worker: 0.12s (jeder Worker bekommt halbes Budget)
        - 3 Tokens, 2 Worker: 0.08s
        """
        workers = max(self._active_workers, 1)
        return self.BASE_SLEEP / self.count * workers

    def register_worker(self):
        """Worker (Migration) als aktiv registrieren."""
        with self._lock:
            self._active_workers += 1

    def unregister_worker(self):
        """Worker (Migration) als beendet abmelden."""
        with self._lock:
            self._active_workers = max(0, self._active_workers - 1)


class AuthManager:
    """Zentrale Authentifizierungsverwaltung."""

    def __init__(self):
        self._ms_auth = None
        self._notion_auth = None
        self._notion_pool = None
        self._config = None
        self._mode = None

    def initialize(self, config: Optional[AuthConfig] = None, mode: str = "cli"):
        """Auth-Manager mit Konfiguration initialisieren.

        Args:
            config: Authentifizierungs-Konfiguration
            mode: Interaktionsmodus ("cli" oder "web")

        Auth-Modus wird durch MS_AUTH_MODE Umgebungsvariable gesteuert:
            - "delegated" (default): Device Code Flow (CLI) / Auth Code Flow (Web)
            - "application": Client Credentials Flow (kein User-Login)
        """
        if config is None:
            auth_mode = os.getenv("MS_AUTH_MODE", "delegated").lower().strip()
            config = AuthConfig(
                ms_client_id=os.getenv("MS_CLIENT_ID", ""),
                ms_tenant_id=os.getenv("MS_TENANT_ID", "consumers"),
                ms_scopes=[s.strip() for s in os.getenv("MS_GRAPH_SCOPES", "Notes.Read.All,Sites.Read.All").split(",")],
                notion_token=os.getenv("NOTION_TOKEN", ""),
                ms_client_secret=os.getenv("MS_CLIENT_SECRET"),
                redirect_uri=os.getenv("FLASK_REDIRECT_URI", "http://localhost:8080/callback"),
                auth_mode=auth_mode
            )

        if not config.ms_client_id:
            raise ValueError("MS_CLIENT_ID environment variable is required")
        if not config.notion_token:
            raise ValueError("NOTION_TOKEN environment variable is required")

        self._config = config
        self._mode = mode

        # Authentifizierungs-Modus auswählen
        if config.auth_mode == "application":
            # Validierungen für Application-Modus
            if not config.ms_client_secret:
                raise ValueError(
                    "MS_CLIENT_SECRET is required when MS_AUTH_MODE=application. "
                    "Create a Client Secret in Azure AD > Certificates & secrets."
                )
            if config.ms_tenant_id in ("consumers", "common"):
                raise ValueError(
                    "MS_TENANT_ID must be a specific tenant ID when MS_AUTH_MODE=application. "
                    "Client Credentials Flow does not work with 'common' or 'consumers'."
                )
            self._ms_auth = MicrosoftAppAuthenticator(config)
        elif mode == "cli":
            self._ms_auth = MicrosoftAuthenticator(config)
        elif mode == "web":
            self._ms_auth = MicrosoftWebAuthenticator(config)
        else:
            raise ValueError(f"Invalid authentication mode: {mode}. Use 'cli' or 'web'.")

        self._notion_pool = NotionTokenPool(config.notion_token)
        self._notion_auth = self._notion_pool.primary

        if self._notion_pool.count > 1:
            print(f"[i] Notion Token-Pool: {self._notion_pool.count} Tokens konfiguriert (Round-Robin)")

    @property
    def microsoft(self):
        """Microsoft Graph Authenticator (CLI oder Web)."""
        if not self._ms_auth:
            raise RuntimeError("AuthManager not initialized. Call initialize() first.")
        return self._ms_auth

    @property
    def mode(self) -> Optional[str]:
        """Aktueller Interaktionsmodus (cli/web)."""
        return self._mode

    @property
    def auth_mode(self) -> Optional[str]:
        """Aktueller Auth-Modus (delegated/application)."""
        if self._config:
            return self._config.auth_mode
        return None

    @property
    def notion(self) -> NotionAuthenticator:
        """Notion API Authenticator (erster Token, fuer Kompatibilitaet)."""
        if not self._notion_auth:
            raise RuntimeError("AuthManager not initialized. Call initialize() first.")
        return self._notion_auth

    @property
    def notion_pool(self) -> NotionTokenPool:
        """Notion Token-Pool fuer Round-Robin."""
        if not self._notion_pool:
            raise RuntimeError("AuthManager not initialized. Call initialize() first.")
        return self._notion_pool


# Globaler Auth-Manager
auth_manager = AuthManager()
