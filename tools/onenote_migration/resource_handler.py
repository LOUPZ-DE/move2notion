#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Resource-Handler für OneNote-zu-Notion Migration.

Dieses Modul behandelt:
- Download von OneNote-Assets (Bilder, Dateien)
- Upload zu Notion
- Caching für bereits hochgeladene Dateien
"""
import os
import tempfile
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.parse import urlparse

import requests


class ResourceHandler:
    """Verwaltet Download und Upload von OneNote-Assets."""

    def __init__(self, notion_client, ms_graph_client):
        """
        Initialisierung.
        
        Args:
            notion_client: NotionClient-Instanz
            ms_graph_client: MSGraphClient-Instanz
        """
        self.notion = notion_client
        self.ms_graph = ms_graph_client
        self.cache: Dict[str, str] = {}  # URL -> Notion-Block-ID
        self.temp_dir = tempfile.mkdtemp(prefix="onenote_assets_")

    def __del__(self):
        """Aufräumen: Temporäre Dateien löschen."""
        try:
            import shutil
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
        except:
            pass

    def process_image(self, img_url: str, page_id: str) -> Optional[Dict[str, Any]]:
        """
        Bild verarbeiten und zu Notion hochladen.
        
        Args:
            img_url: URL des Bildes
            page_id: Notion-Page-ID für Upload
            
        Returns:
            Notion-Image-Block oder None bei Fehler
        """
        # Cache-Check
        if img_url in self.cache:
            return {
                "object": "block",
                "type": "image",
                "image": {
                    "type": "file",
                    "file": {"url": self.cache[img_url]}
                }
            }

        try:
            # Bild herunterladen
            local_path = self._download_resource(img_url)
            if not local_path:
                return None

            # Zu Notion hochladen
            notion_url = self._upload_to_notion(local_path, page_id)
            if not notion_url:
                return None

            # Cachen
            self.cache[img_url] = notion_url

            # Notion-Block erstellen
            return {
                "object": "block",
                "type": "image",
                "image": {
                    "type": "file",
                    "file": {"url": notion_url}
                }
            }

        except Exception as e:
            print(f"[⚠] Bild-Upload fehlgeschlagen ({img_url}): {e}")
            return None

    def process_file(self, file_url: str, file_name: str, page_id: str) -> Optional[Dict[str, Any]]:
        """
        Datei verarbeiten und zu Notion hochladen.
        
        Args:
            file_url: URL der Datei
            file_name: Dateiname
            page_id: Notion-Page-ID für Upload
            
        Returns:
            Notion-File-Block oder None bei Fehler
        """
        # Cache-Check
        if file_url in self.cache:
            return {
                "object": "block",
                "type": "file",
                "file": {
                    "type": "file",
                    "file": {"url": self.cache[file_url]},
                    "caption": [{"type": "text", "text": {"content": file_name}}]
                }
            }

        try:
            # Datei herunterladen
            local_path = self._download_resource(file_url, file_name)
            if not local_path:
                return None

            # Zu Notion hochladen
            notion_url = self._upload_to_notion(local_path, page_id)
            if not notion_url:
                return None

            # Cachen
            self.cache[file_url] = notion_url

            # Notion-Block erstellen
            return {
                "object": "block",
                "type": "file",
                "file": {
                    "type": "file",
                    "file": {"url": notion_url},
                    "caption": [{"type": "text", "text": {"content": file_name}}]
                }
            }

        except Exception as e:
            print(f"[⚠] Datei-Upload fehlgeschlagen ({file_name}): {e}")
            return None

    def _download_resource(self, url: str, filename: Optional[str] = None) -> Optional[str]:
        """
        Ressource herunterladen.
        
        Args:
            url: URL der Ressource
            filename: Optionaler Dateiname
            
        Returns:
            Lokaler Pfad oder None bei Fehler
        """
        try:
            # OneNote-URLs korrigieren: /siteCollections/ → /sites/
            if "/siteCollections/" in url:
                url = url.replace("/siteCollections/", "/sites/")
            
            # Dateiname aus URL oder Parameter
            if not filename:
                parsed = urlparse(url)
                filename = os.path.basename(parsed.path) or self._generate_filename(url)

            # Sicherer Dateiname
            safe_filename = "".join(c for c in filename if c.isalnum() or c in "._- ")
            local_path = os.path.join(self.temp_dir, safe_filename)

            # Download mit MS Graph Auth-Header
            headers = self.ms_graph.auth.microsoft.headers if hasattr(self.ms_graph, 'auth') else {}
            
            response = requests.get(url, headers=headers, timeout=30, stream=True)
            response.raise_for_status()

            # Speichern
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            return local_path

        except Exception as e:
            print(f"[⚠] Download fehlgeschlagen ({url}): {e}")
            return None

    def _upload_to_notion(self, file_path: str, page_id: str) -> Optional[str]:
        """
        Datei zu Notion hochladen.
        
        Args:
            file_path: Lokaler Dateipfad
            page_id: Notion-Page-ID
            
        Returns:
            Upload-ID oder None bei Fehler
        """
        # Notion-kompatible Extensions
        SUPPORTED_EXTENSIONS = {
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            '.txt', '.csv', '.zip', '.rar', '7z',
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp',
            '.mp3', '.mp4', '.wav', '.webm', '.mov',
            '.json', '.xml', '.html'
        }
        
        try:
            filename = os.path.basename(file_path)
            file_ext = os.path.splitext(filename)[1].lower()
            
            # Prüfe ob Extension unterstützt ist
            if file_ext not in SUPPORTED_EXTENSIONS:
                print(f"[⚠] Extension nicht unterstützt: {filename} ({file_ext})")
                return None
            
            with open(file_path, 'rb') as f:
                data = f.read()
            
            # Content-Type bestimmen
            import mimetypes
            content_type, _ = mimetypes.guess_type(file_path)
            
            # Zu Notion hochladen
            upload_id = self.notion.upload_file(filename, data, content_type)
            
            if upload_id:
                print(f"[✅] Datei hochgeladen: {filename}")
            else:
                print(f"[⚠] Upload fehlgeschlagen: {filename}")
            
            return upload_id

        except Exception as e:
            print(f"[⚠] Upload-Fehler: {e}")
            return None

    def _generate_filename(self, url: str) -> str:
        """Dateiname aus URL generieren."""
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        return f"resource_{url_hash}"

    def extract_images_from_html(self, html: str) -> list:
        """
        Bild-URLs aus HTML extrahieren.
        
        Args:
            html: HTML-String
            
        Returns:
            Liste von Bild-URLs
        """
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(html, "html.parser")
        images = []
        
        for img in soup.find_all("img"):
            src = img.get("src")
            if src:
                images.append(src)
        
        return images

    def extract_files_from_html(self, html: str) -> list:
        """
        Datei-URLs aus HTML extrahieren.
        
        Args:
            html: HTML-String
            
        Returns:
            Liste von (URL, Name)-Tupeln
        """
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(html, "html.parser")
        files = []
        
        for link in soup.find_all("a"):
            href = str(link.get("href", ""))
            text = link.get_text(strip=True)
            
            # Ignoriere: mailto, tel, #-Links
            if not href or href.startswith("mailto:") or href.startswith("tel:") or href.startswith("#"):
                continue
            
            # Datei-Extensions prüfen
            if any(ext in href.lower() for ext in [".pdf", ".docx", ".xlsx", ".pptx", ".zip", ".jpg", ".png", ".gif"]):
                files.append((href, text or "Download"))
            # Oder externe URLs
            elif href.startswith("http://") or href.startswith("https://"):
                files.append((href, text or "Download"))
        
        return files
