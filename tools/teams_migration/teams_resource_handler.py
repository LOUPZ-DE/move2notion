#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teams-spezifischer Resource-Handler fuer Bilder und Anhaenge.

Erweitert den OneNote-`ResourceHandler` um Teams-`hostedContents`-URL-Schema.
Inline-Bilder in Message-Bodies (`<img src=".../hostedContents/{id}/$value">`)
werden als Notion-Image-Bloecke materialisiert; Datei-Anhaenge mit
SharePoint-URL bleiben Verweise (siehe `message_block_builder.build_attachment_blocks`).
"""
import base64
import re
from typing import Optional, Dict, Any

from tools.onenote_migration.resource_handler import ResourceHandler


def _sharepoint_url_to_graph_share_endpoint(url: str) -> Optional[str]:
    """SharePoint-/OneDrive-URL in Microsoft Graph `shares/{token}`-Form wandeln.

    Microsofts „Shares"-API akzeptiert jede SharePoint-URL als base64url-codierter
    Token mit `u!`-Prefix. Damit kann der Datei-Inhalt mit demselben Graph-Bearer-
    Token abgerufen werden, statt einen separaten SharePoint-Token zu erwerben.

    Siehe https://learn.microsoft.com/graph/api/shares-get
    """
    if not url:
        return None
    if "sharepoint.com" not in url and "1drv.ms" not in url:
        return None
    encoded = base64.urlsafe_b64encode(url.encode("utf-8")).decode("ascii").rstrip("=")
    return f"/shares/u!{encoded}/driveItem/content"


_HOSTED_RE = re.compile(
    r"/teams/(?P<team>[^/]+)/channels/(?P<channel>[^/]+)/messages/(?P<msg>[^/]+)/hostedContents/(?P<hosted>[^/]+)",
    re.IGNORECASE,
)
_RELATIVE_HOSTED_RE = re.compile(
    r"hostedContents/([^/'\"\s\)]+)/\$value", re.IGNORECASE
)


class TeamsResourceHandler(ResourceHandler):
    """Resource-Handler fuer Teams-Migration.

    Trackt aktiven Team-/Channel-Kontext, damit relative `hostedContents`-IDs
    in vollstaendige Graph-URLs aufgeloest werden koennen.
    """

    def __init__(self, notion_client, ms_graph_client, team_id: str):
        super().__init__(notion_client, ms_graph_client, site_id=None)
        self.team_id = team_id
        self._current_channel_id: Optional[str] = None

    def set_channel_context(self, channel_id: str):
        """Vor dem Verarbeiten eines Channels setzen, damit URLs korrekt sind."""
        self._current_channel_id = channel_id

    # ------------------------------------------------------------------
    # Public API fuer message_block_builder

    def download_image_from_url(
        self, url: str, filename_hint: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Bild direkt von einer beliebigen URL (z. B. SharePoint) herunterladen
        und als Notion-Image-Block zurueckgeben.

        Genutzt fuer Teams-Attachments mit `contentType: "reference"`, die auf
        eine SharePoint-Bilddatei zeigen. Der Graph-Bearer-Token wird mitgeschickt
        und funktioniert in der Regel auch fuer `*.sharepoint.com`-URLs des
        Heimat-Tenants.
        """
        if not url:
            return None
        if url in self.cache:
            return self.notion.create_image_block(self.cache[url])
        try:
            # SharePoint-URLs ueber Graph "Shares" API laden — Graph-Token ist
            # fuer `*.sharepoint.com` direkt nicht autorisiert (SharePoint
            # erwartet einen separaten Token); der `/shares/u!<base64>`-Umweg
            # umgeht das.
            share_endpoint = _sharepoint_url_to_graph_share_endpoint(url)
            if share_endpoint:
                share_url = f"https://graph.microsoft.com/v1.0{share_endpoint}"
                data, content_type = self._download_resource(share_url)
            else:
                data, content_type = self._download_resource(url)
            if not data:
                return None
            from core.utils import detect_content_type_and_filename
            final_ct, filename = detect_content_type_and_filename(
                data, content_type, filename_hint or url
            )
            file_upload_id = self.notion.upload_file(filename, data, final_ct)
            if not file_upload_id:
                return None
            self.cache[url] = file_upload_id
            return self.notion.create_image_block(file_upload_id)
        except Exception as e:  # pragma: no cover - defensiv
            print(f"[⚠] Bild konnte nicht geladen werden ({url}): {e}")
            return None

    def download_file_from_url(
        self, url: str, filename_hint: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Beliebige Datei (PDF, DOCX, XLSX, ...) von einer SharePoint-URL
        herunterladen und als Notion-File-Block einbetten.

        Geht denselben `/shares/u!<base64>/driveItem/content`-Weg wie der
        Image-Downloader. Bei Dateien >20 MB (Notion Upload-Limit) wird `None`
        zurueckgegeben, sodass der Caller auf Bookmark zurueckfallen kann.
        """
        if not url:
            return None
        cache_key = f"file::{url}"
        if cache_key in self.cache:
            return self.notion.create_file_block(self.cache[cache_key])
        try:
            share_endpoint = _sharepoint_url_to_graph_share_endpoint(url)
            if share_endpoint:
                share_url = f"https://graph.microsoft.com/v1.0{share_endpoint}"
                data, content_type = self._download_resource(share_url)
            else:
                data, content_type = self._download_resource(url)
            if not data:
                return None
            if len(data) > 20 * 1024 * 1024:
                # Notion-Upload-Limit erreicht → Caller faellt auf Bookmark zurueck
                return None
            from core.utils import detect_content_type_and_filename
            final_ct, filename = detect_content_type_and_filename(
                data, content_type, filename_hint or url
            )
            file_upload_id = self.notion.upload_file(filename, data, final_ct)
            if not file_upload_id:
                return None
            self.cache[cache_key] = file_upload_id
            return self.notion.create_file_block(file_upload_id)
        except Exception as e:  # pragma: no cover - defensiv
            print(f"[⚠] Datei konnte nicht geladen werden ({url}): {e}")
            return None

    def process_hosted_content_image(
        self, hosted_id: str, message_id: str
    ) -> Optional[Dict[str, Any]]:
        """Bild direkt anhand der hostedContent-ID laden (fuer Image-Attachments
        ohne contentUrl).

        Konstruiert die vollstaendige Graph-URL und delegiert an den
        bestehenden Download/Upload-Pfad.
        """
        if not hosted_id or not self._current_channel_id:
            return None
        url = (
            f"https://graph.microsoft.com/v1.0/teams/{self.team_id}"
            f"/channels/{self._current_channel_id}/messages/{message_id}"
            f"/hostedContents/{hosted_id}/$value"
        )
        if url in self.cache:
            return self.notion.create_image_block(self.cache[url])
        try:
            data, content_type = self._download_resource(url)
            if not data:
                return None
            from core.utils import detect_content_type_and_filename
            final_ct, filename = detect_content_type_and_filename(
                data, content_type, f"{hosted_id}.bin"
            )
            file_upload_id = self.notion.upload_file(filename, data, final_ct)
            if not file_upload_id:
                return None
            self.cache[url] = file_upload_id
            return self.notion.create_image_block(file_upload_id)
        except Exception as e:  # pragma: no cover - defensiv
            print(f"[⚠] hostedContent {hosted_id} konnte nicht geladen werden: {e}")
            return None

    def process_message_image(self, src: str, message_id: str) -> Optional[Dict[str, Any]]:
        """Inline-Bild aus einem Teams-Message-Body verarbeiten.

        Args:
            src: src-Attribut der `<img>` (kann vollstaendige Graph-URL oder
                relative hostedContents-Referenz sein).
            message_id: Aktuelle Top-Level-Message-ID (fuer URL-Aufloesung).

        Returns:
            Notion image-Block oder None bei Fehler.
        """
        if not src:
            return None
        if src.startswith("data:"):
            return None
        url = self._fix_graph_url(src, message_id=message_id)
        if not url:
            return None
        # Cache-Check (URL als Key)
        if url in self.cache:
            return self.notion.create_image_block(self.cache[url])
        try:
            data, content_type = self._download_resource(url)
            if not data:
                return None
            from core.utils import detect_content_type_and_filename
            final_ct, filename = detect_content_type_and_filename(data, content_type, url)
            file_upload_id = self.notion.upload_file(filename, data, final_ct)
            if not file_upload_id:
                return None
            self.cache[url] = file_upload_id
            return self.notion.create_image_block(file_upload_id)
        except Exception as e:  # pragma: no cover - defensiv
            print(f"[⚠] Inline-Bild-Upload fehlgeschlagen ({src}): {e}")
            return None

    # ------------------------------------------------------------------
    # Override

    def _fix_graph_url(self, url: str, message_id: Optional[str] = None) -> Optional[str]:
        """Teams-URLs in vollstaendige Graph-API-URLs uebersetzen."""
        if not url:
            return None

        # Bereits vollstaendige Graph-URL mit /teams/.../hostedContents/{id}/$value
        if "graph.microsoft.com" in url and "hostedContents" in url and "$value" in url:
            return url

        # Vollstaendige Graph-URL ohne $value — anhaengen
        if "graph.microsoft.com" in url and "hostedContents" in url and not url.endswith("$value"):
            return url.rstrip("/") + "/$value"

        # Relative hostedContents-Referenz: hostedContents/{id}/$value
        rel_match = _RELATIVE_HOSTED_RE.search(url)
        if rel_match and message_id and self._current_channel_id:
            hosted_id = rel_match.group(1)
            return (
                f"https://graph.microsoft.com/v1.0/teams/{self.team_id}"
                f"/channels/{self._current_channel_id}/messages/{message_id}"
                f"/hostedContents/{hosted_id}/$value"
            )

        # /teams/.../hostedContents/... ohne Domain
        match = _HOSTED_RE.search(url)
        if match:
            base = "https://graph.microsoft.com/v1.0"
            path = url[match.start():]
            full = f"{base}/{path.lstrip('/')}"
            if not full.endswith("$value"):
                full = full.rstrip("/") + "/$value"
            return full

        # Externe http(s)-URLs: unveraendert zurueckgeben (bookmark-Faehigkeit)
        if url.startswith("http://") or url.startswith("https://"):
            return url

        return None
