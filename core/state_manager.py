"""
State Management für Idempotenz und Resume-Funktionalität.
"""
import os
import json
import hashlib
from typing import Dict, Any, Optional
from pathlib import Path


class StateManager:
    """Verwaltung von Migrationszuständen für Idempotenz."""

    def __init__(self, state_path: Optional[str] = None):
        if state_path is None:
            state_path = os.path.expanduser(os.getenv("ON2N_STATE", "~/.onenote2notion/state.json"))

        self.state_path = Path(state_path)
        self._state: Dict[str, Any] = {"pages": {}}

    def _ensure_state_dir(self):
        """Verzeichnis für State-Datei erstellen falls nicht vorhanden."""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    def load_state(self) -> Dict[str, Any]:
        """State aus Datei laden."""
        try:
            if self.state_path.exists():
                with open(self.state_path, "r", encoding="utf-8") as f:
                    self._state = json.load(f)
        except Exception as e:
            print(f"[Warning] Could not load state: {e}")
            self._state = {"pages": {}}

        return self._state

    def save_state(self):
        """State in Datei speichern."""
        self._ensure_state_dir()
        try:
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2)
        except Exception as e:
            print(f"[Warning] Could not save state: {e}")

    def get_page_state(self, key: str) -> Optional[Dict[str, Any]]:
        """State für eine bestimmte Seite abrufen."""
        return self._state.get("pages", {}).get(key)

    def set_page_state(self, key: str, page_id: str, checksum: str, timestamp: Optional[int] = None):
        """State für eine Seite setzen."""
        if "pages" not in self._state:
            self._state["pages"] = {}

        import time
        self._state["pages"][key] = {
            "notion_id": page_id,
            "checksum": checksum,
            "ts": timestamp or int(time.time())
        }
        self.save_state()

    def is_page_unchanged(self, key: str, current_checksum: str) -> bool:
        """Prüfen ob sich eine Seite seit dem letzten Import geändert hat."""
        page_state = self.get_page_state(key)
        if not page_state:
            return False

        return page_state.get("checksum") == current_checksum

    def get_all_pages(self) -> Dict[str, Dict[str, Any]]:
        """Alle gespeicherten Seiten-States abrufen."""
        return self._state.get("pages", {})

    def clear_state(self):
        """Gesamten State löschen."""
        self._state = {"pages": {}}
        self.save_state()

    def remove_page_state(self, key: str):
        """State für eine bestimmte Seite entfernen."""
        if "pages" in self._state and key in self._state["pages"]:
            del self._state["pages"][key]
            self.save_state()


def generate_page_key(site_id: str, notebook_id: str, section_id: str, page_id: str) -> str:
    """Eindeutigen Schlüssel für eine OneNote-Seite generieren."""
    return f"{site_id}:{notebook_id}:{section_id}:{page_id}"


def calculate_checksum(content: bytes) -> str:
    """MD5-Checksumme für Content berechnen."""
    return hashlib.md5(content).hexdigest()


# Convenience-Funktionen
def get_state_manager(state_path: Optional[str] = None) -> StateManager:
    """Globalen State-Manager abrufen."""
    return StateManager(state_path)
