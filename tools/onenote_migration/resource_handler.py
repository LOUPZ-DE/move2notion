#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Resource-Handler für OneNote-zu-Notion Migration.

Dieses Modul behandelt:
- Download von OneNote-Assets (Bilder, Dateien)
- Content-Type Detection
- Upload zu Notion (File Upload API)
"""
import requests
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import urlparse
from bs4 import BeautifulSoup

from core.utils import detect_content_type_and_filename


class ResourceHandler:
    """Verwaltet Download und Upload von OneNote-Assets."""

    def __init__(self, notion_client, ms_graph_client, site_id: Optional[str] = None):
        """
        Initialisierung.
        
        Args:
            notion_client: NotionClient-Instanz
            ms_graph_client: MSGraphClient-Instanz
            site_id: SharePoint-Site-ID (optional)
        """
        self.notion = notion_client
        self.ms_graph = ms_graph_client
        self.site_id = site_id
        self.cache: Dict[str, str] = {}  # URL -> file_upload_id

    def process_image(self, img_url: str, page_id: str) -> Optional[Dict[str, Any]]:
        """
        Bild verarbeiten und zu Notion hochladen.
        
        Args:
            img_url: URL des Bildes
            page_id: Notion-Page-ID (ungenutzt, für Kompatibilität)
            
        Returns:
            Notion-Image-Block oder None bei Fehler
        """
        # Cache-Check
        if img_url in self.cache:
            return self.notion.create_image_block(self.cache[img_url])

        try:
            # URL für Graph API anpassen
            fixed_url = self._fix_graph_url(img_url)
            
            # Bild herunterladen
            data, content_type = self._download_resource(fixed_url)
            if not data:
                return None
            
            # Content-Type und Dateiname bestimmen
            final_ct, filename = detect_content_type_and_filename(data, content_type, img_url)
            
            # Zu Notion hochladen
            file_upload_id = self.notion.upload_file(filename, data, final_ct)
            if not file_upload_id:
                return None
            
            # Cachen
            self.cache[img_url] = file_upload_id
            
            # Image-Block erstellen
            return self.notion.create_image_block(file_upload_id)

        except Exception as e:
            print(f"[⚠] Bild-Upload fehlgeschlagen ({img_url}): {e}")
            return None

    def process_file(self, file_url: str, file_name: str, page_id: str) -> Optional[Dict[str, Any]]:
        """
        Datei verarbeiten und zu Notion hochladen.
        
        Args:
            file_url: URL der Datei
            file_name: Dateiname
            page_id: Notion-Page-ID (ungenutzt, für Kompatibilität)
            
        Returns:
            Notion-File-Block oder None bei Fehler
        """
        # Cache-Check
        if file_url in self.cache:
            return self.notion.create_file_block(self.cache[file_url])

        try:
            # URL für Graph API anpassen
            fixed_url = self._fix_graph_url(file_url)
            
            # Datei herunterladen
            data, content_type = self._download_resource(fixed_url)
            if not data:
                return None
            
            # Content-Type und Dateiname bestimmen
            final_ct, filename = detect_content_type_and_filename(data, content_type, file_url)
            
            # Verwende Original-Namen wenn vorhanden
            if file_name and file_name != "Download":
                filename = file_name
            
            # Zu Notion hochladen
            file_upload_id = self.notion.upload_file(filename, data, final_ct)
            if not file_upload_id:
                return None
            
            # Cachen
            self.cache[file_url] = file_upload_id
            
            # File-Block erstellen
            return self.notion.create_file_block(file_upload_id)

        except Exception as e:
            print(f"[⚠] Datei-Upload fehlgeschlagen ({file_name}): {e}")
            return None

    def _download_resource(self, url: str) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Ressource von OneNote herunterladen.
        
        Args:
            url: Resource-URL
            
        Returns:
            (Daten, Content-Type) oder (None, None) bei Fehler
        """
        try:
            # MS Graph Auth-Header
            headers = self.ms_graph.auth.microsoft.headers
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            content_type = response.headers.get("Content-Type", "").split(";")[0].strip()
            
            return response.content, content_type or None

        except Exception as e:
            print(f"[⚠] Download fehlgeschlagen ({url}): {e}")
            return None, None

    def _fix_graph_url(self, url: str) -> str:
        """
        OneNote-URL für Graph API anpassen.
        
        Ändert /onenote/resources/ URLs zu Graph API Format.
        """
        if "/onenote/resources/" in url:
            # Extrahiere Resource-ID
            import re
            match = re.search(r"/onenote/resources/([^/?]+)", url)
            if match and self.site_id:
                resource_id = match.group(1)
                # Verwende site_id (wurde von ContentMapper gesetzt)
                return f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/onenote/resources/{resource_id}/content"
        
        # Korrigiere alte /siteCollections/ URLs
        if "/siteCollections/" in url:
            url = url.replace("/siteCollections/", "/sites/")
        
        return url

    def extract_images_from_html(self, html: str) -> List[str]:
        """
        Bild-URLs aus HTML extrahieren.
        
        Args:
            html: HTML-String
            
        Returns:
            Liste von Bild-URLs
        """
        soup = BeautifulSoup(html, "html.parser")
        images = []
        
        # <img> Tags
        for img in soup.find_all("img"):
            src = img.get("data-fullres-src") or img.get("data-src") or img.get("src")
            if src and self._is_valid_image_url(src):
                images.append(src)
        
        # <object> Tags (können auch Bilder sein)
        for obj in soup.find_all("object"):
            data_url = obj.get("data") or obj.get("data-fullres-src")
            obj_type = (obj.get("type") or "").lower()
            if data_url and obj_type.startswith("image/"):
                images.append(data_url)
        
        return images

    def extract_files_from_html(self, html: str) -> List[Tuple[str, str]]:
        """
        Datei-URLs aus HTML extrahieren.
        
        Args:
            html: HTML-String
            
        Returns:
            Liste von (URL, Name)-Tupeln
        """
        soup = BeautifulSoup(html, "html.parser")
        files = []
        
        # <a> Tags mit Download-Links
        for link in soup.find_all("a"):
            href = str(link.get("href", ""))
            text = link.get_text(strip=True) or "Download"
            
            # Ignoriere: mailto, tel, #-Links
            if not href or href.startswith("mailto:") or href.startswith("tel:") or href.startswith("#"):
                continue
            
            # Prüfe ob gültige Datei-URL
            if self._is_valid_file_url(href):
                files.append((href, text))
        
        # <object> Tags (nicht-Bilder)
        for obj in soup.find_all("object"):
            data_url = obj.get("data") or obj.get("data-fullres-src")
            obj_type = (obj.get("type") or "").lower()
            if data_url and not obj_type.startswith("image/"):
                files.append((data_url, "Attached File"))
        
        return files

    def _is_valid_image_url(self, url: str) -> bool:
        """Prüfe ob URL ein gültiges Bild ist."""
        if not url:
            return False
        
        # Ignoriere Data-URLs
        if url.startswith("data:"):
            return False
        
        # OneNote-Ressourcen sind OK
        if "/onenote/resources/" in url:
            return True
        
        # Prüfe Extension
        lower_url = url.lower()
        image_exts = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg")
        return any(ext in lower_url for ext in image_exts)

    def _is_valid_file_url(self, url: str) -> bool:
        """Prüfe ob URL eine gültige Datei ist."""
        if not url:
            return False
        
        # Ignoriere Data-URLs
        if url.startswith("data:"):
            return False
        
        # OneNote-Ressourcen sind OK
        if "/onenote/resources/" in url:
            return True
        
        # Prüfe Extension
        lower_url = url.lower()
        file_exts = (".pdf", ".docx", ".xlsx", ".pptx", ".zip", ".txt", ".csv")
        return any(ext in lower_url for ext in file_exts)
