#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Notion-Block-Builder fuer Teams-Messages.

Pure Funktionen ohne API-Calls (ausser dem optional uebergebenen
ResourceHandler, der hostedContents/Attachments als Bloecke materialisiert).

Block-Layout pro Message:

    toggle:
        rich_text: [Author bold, " · ", Datum italic gray, " · ", Vorschau gray]
        children:
            - body_blocks (HTML → paragraphs/lists/etc.)
            - attachment_blocks (image / file / bookmark)
            - reactions_paragraph (italic gray)
            - reply_toggles (rekursiv)

Replies werden chronologisch geordnet als nested toggles unter dem Parent
abgelegt — Notion erlaubt children innerhalb von toggle-Bloecken.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup, NavigableString, Tag

from .teams_api_mapper import Message, Reaction, Mention


REACTION_EMOJI: Dict[str, str] = {
    "like": "👍",
    "heart": "❤️",
    "laugh": "😂",
    "surprised": "😮",
    "sad": "😢",
    "angry": "😠",
}

# Wieviel Zeichen Vorschau im Toggle-Header
PREVIEW_CHARS = 60
# Notion-Limit fuer einen einzelnen rich_text-text-Inhalt (2000 chars).
# Wir lassen Puffer und splitten ab 1900.
RICH_TEXT_MAX = 1900


def _format_dt(iso_dt: Optional[str]) -> str:
    """ISO-Datum in deutsches 'D.M.YYYY HH:MM'-Format (z.B. '5.12.2024 15:53').

    Uhrzeit bleibt UTC (wie Microsoft Graph sie liefert); MS Teams selbst zeigt
    die UTC-Uhrzeit in Kanal-Headern auch unkonvertiert an, daher konsistent.
    """
    if not iso_dt:
        return ""
    try:
        # Microsoft Graph liefert "2024-03-15T13:42:11.123Z"
        cleaned = iso_dt.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        return f"{dt.day}.{dt.month}.{dt.year} {dt.strftime('%H:%M')}"
    except Exception:
        return iso_dt[:16]


def _split_long_text(text: str, max_len: int = RICH_TEXT_MAX) -> List[str]:
    """Lange Texte in Notion-konforme Stuecke splitten."""
    if len(text) <= max_len:
        return [text] if text else []
    chunks = []
    for i in range(0, len(text), max_len):
        chunks.append(text[i:i + max_len])
    return chunks


def _rich_text(content: str, *, bold: bool = False, italic: bool = False,
               color: str = "default", link: Optional[str] = None,
               code: bool = False) -> List[Dict[str, Any]]:
    """Rich-Text-Eintrag mit Formatierungen erzeugen, splittet lange Inhalte.

    Wenn `link` nicht gesetzt ist, werden enthaltene http(s)-URLs automatisch
    in eigene rich_text-Eintraege mit `link.url` aufgesplittet — damit werden
    sie in Notion klickbar.
    """
    if link:
        return _build_chunks(content, bold=bold, italic=italic, code=code,
                             color=color, link=link)
    return _autolink_rich_text(content, bold=bold, italic=italic, code=code,
                               color=color)


def _build_chunks(content: str, *, bold: bool, italic: bool, code: bool,
                  color: str, link: Optional[str]) -> List[Dict[str, Any]]:
    parts = []
    for chunk in _split_long_text(content):
        item: Dict[str, Any] = {
            "type": "text",
            "text": {"content": chunk},
            "annotations": {
                "bold": bold,
                "italic": italic,
                "code": code,
                "color": color,
            },
        }
        if link:
            item["text"]["link"] = {"url": link}
        parts.append(item)
    return parts


_URL_PATTERN = re.compile(
    r"(https?://[^\s<>\"')\]]+[^\s<>\"')\].,;:!?])"
)


def _autolink_rich_text(content: str, *, bold: bool, italic: bool,
                        code: bool, color: str) -> List[Dict[str, Any]]:
    """Erkennt http(s)-URLs in Plain-Text und macht sie klickbar."""
    if not content:
        return []
    # Wenn Code-Annotation, KEINE Auto-Linkification (Code soll roh bleiben)
    if code:
        return _build_chunks(content, bold=bold, italic=italic, code=code,
                             color=color, link=None)
    parts: List[Dict[str, Any]] = []
    last_end = 0
    for match in _URL_PATTERN.finditer(content):
        start, end = match.span()
        if start > last_end:
            parts.extend(_build_chunks(content[last_end:start],
                                       bold=bold, italic=italic, code=False,
                                       color=color, link=None))
        url = match.group(0)
        parts.extend(_build_chunks(url, bold=bold, italic=italic, code=False,
                                   color=color, link=url))
        last_end = end
    if last_end < len(content):
        parts.extend(_build_chunks(content[last_end:], bold=bold, italic=italic,
                                   code=False, color=color, link=None))
    return parts


def _strip_html_to_text(html: str, max_len: int = PREVIEW_CHARS) -> str:
    """Erste Zeile/Vorschau-Text aus Message-Body extrahieren."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[:max_len].rstrip() + "…"
    return text


def build_header_rich_text(msg: Message) -> List[Dict[str, Any]]:
    """Toggle-Header: **Author** · _Datum_ · Vorschau."""
    rt: List[Dict[str, Any]] = []
    rt.extend(_rich_text(msg.from_display_name or "Unbekannt", bold=True))
    rt.extend(_rich_text(" · "))
    rt.extend(_rich_text(_format_dt(msg.created_dt), italic=True, color="gray"))
    preview = _strip_html_to_text(msg.body_html or "")
    if preview:
        rt.extend(_rich_text(" · "))
        rt.extend(_rich_text(preview, color="gray"))
    if msg.subject:
        rt.extend(_rich_text("  ["))
        rt.extend(_rich_text(msg.subject, italic=True))
        rt.extend(_rich_text("]"))
    if msg.importance and msg.importance != "normal":
        rt.extend(_rich_text(f"  ⚠ {msg.importance}", bold=True, color="red"))
    return rt


def _is_url(href: str) -> bool:
    return bool(href) and (href.startswith("http://") or href.startswith("https://"))


def _build_inline_rich_text(node: Any, mentions_by_id: Dict[int, Mention]) -> List[Dict[str, Any]]:
    """Inline-Konvertierung eines BS4-Knotens zu Notion-Rich-Text.

    Behandelt rekursiv:
      - <strong>/<b>, <em>/<i>, <u>, <s>/<strike>, <code>
      - <a href="...">  → Link (nur http/https akzeptiert von Notion)
      - <at id="N">     → Mention (rich_text mit blauer Farbe + mailto-Link)
      - <emoji>         → Plain-Text-Emoji
      - <br>            → "\n"
    """
    if isinstance(node, NavigableString):
        text = str(node)
        return _rich_text(text) if text else []

    if not isinstance(node, Tag):
        return []

    name = (node.name or "").lower()

    # Mentions: <at id="0">@Username</at>
    if name == "at":
        mention_id_raw = node.get("id")
        try:
            mention_id = int(mention_id_raw) if mention_id_raw is not None else -1
        except (TypeError, ValueError):
            mention_id = -1
        m = mentions_by_id.get(mention_id)
        text = node.get_text(strip=False) or (m.display_name if m else "@?")
        link = f"mailto:{m.email}" if m and m.email else None
        return _rich_text(f"@{text.lstrip('@')}", bold=True, color="blue", link=link)

    # Inline-Bilder (hostedContents) werden separat als Bild-Bloecke verarbeitet,
    # an dieser Stelle ueberspringen wir <img>.
    if name == "img":
        return []

    if name == "br":
        return _rich_text("\n")

    # Links — nur http/https akzeptiert Notion
    if name == "a":
        href = (node.get("href") or "").strip()
        text = node.get_text(strip=False) or href
        if _is_url(href):
            return _rich_text(text, link=href)
        return _rich_text(text)

    # Inline-Emoji — Teams sendet <emoji id="..." alt="😀">
    if name == "emoji":
        alt = node.get("alt") or node.get_text(strip=False) or ""
        return _rich_text(alt)

    # Formatierungs-Wrapper: rekursiv mit erweiterten Annotations
    children_rt: List[Dict[str, Any]] = []
    for child in node.children:
        children_rt.extend(_build_inline_rich_text(child, mentions_by_id))

    annot_overrides: Dict[str, Any] = {}
    if name in ("strong", "b"):
        annot_overrides["bold"] = True
    elif name in ("em", "i"):
        annot_overrides["italic"] = True
    elif name == "u":
        annot_overrides["underline"] = True
    elif name in ("s", "strike", "del"):
        annot_overrides["strikethrough"] = True
    elif name == "code":
        annot_overrides["code"] = True

    if annot_overrides:
        for rt in children_rt:
            rt.setdefault("annotations", {}).update(annot_overrides)

    return children_rt


def _block_paragraph(rich_text: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": rich_text}}


def _block_bullet(rich_text: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": rich_text},
    }


def _block_numbered(rich_text: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "object": "block",
        "type": "numbered_list_item",
        "numbered_list_item": {"rich_text": rich_text},
    }


def _block_heading(level: int, rich_text: List[Dict[str, Any]]) -> Dict[str, Any]:
    level = max(1, min(3, level))
    key = f"heading_{level}"
    return {"object": "block", "type": key, key: {"rich_text": rich_text}}


def _block_quote(rich_text: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"object": "block", "type": "quote", "quote": {"rich_text": rich_text}}


def _block_code(text: str, language: str = "plain text") -> Dict[str, Any]:
    return {
        "object": "block",
        "type": "code",
        "code": {
            "rich_text": [{"type": "text", "text": {"content": text[:RICH_TEXT_MAX]}}],
            "language": language,
        },
    }


def _block_divider() -> Dict[str, Any]:
    return {"object": "block", "type": "divider", "divider": {}}


def build_body_blocks(msg: Message, resource_handler=None) -> List[Dict[str, Any]]:
    """HTML-Body einer Teams-Message in Notion-Bloecke konvertieren.

    Verarbeitet die in Teams-Bodies ueblichen Tags. Inline `<img src=".../hostedContents/...">`
    wird zu einem Image-Block, sofern `resource_handler` gesetzt und der
    hostedContent-Download erfolgreich ist.
    """
    if not msg.body_html:
        return []

    if msg.body_content_type == "text":
        return [_block_paragraph(_rich_text(msg.body_html))]

    soup = BeautifulSoup(msg.body_html, "html.parser")
    mentions_by_id = {m.mention_id: m for m in msg.mentions}

    blocks: List[Dict[str, Any]] = []

    def render(node: Any, depth: int = 0):
        if isinstance(node, NavigableString):
            text = str(node).strip()
            if text:
                blocks.append(_block_paragraph(_rich_text(text)))
            return
        if not isinstance(node, Tag):
            return

        name = (node.name or "").lower()

        if name in ("html", "body", "div", "span"):
            for child in node.children:
                render(child, depth)
            return

        # <attachment id="..."> ist nur ein Marker, der auf msg.attachments verweist.
        # Wird ueber build_attachment_blocks separat materialisiert.
        if name == "attachment":
            return

        if name == "p":
            rt = _build_inline_rich_text(node, mentions_by_id)
            # Inline-Bilder als separate Image-Bloecke materialisieren
            _emit_inline_images(node, msg, resource_handler, blocks)
            if rt:
                blocks.append(_block_paragraph(rt))
            return

        if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(name[1])
            rt = _build_inline_rich_text(node, mentions_by_id)
            if rt:
                blocks.append(_block_heading(level, rt))
            return

        if name == "ul":
            for li in node.find_all("li", recursive=False):
                rt = _build_inline_rich_text(li, mentions_by_id)
                _emit_inline_images(li, msg, resource_handler, blocks)
                if rt:
                    blocks.append(_block_bullet(rt))
            return

        if name == "ol":
            for li in node.find_all("li", recursive=False):
                rt = _build_inline_rich_text(li, mentions_by_id)
                _emit_inline_images(li, msg, resource_handler, blocks)
                if rt:
                    blocks.append(_block_numbered(rt))
            return

        if name == "blockquote":
            rt = _build_inline_rich_text(node, mentions_by_id)
            if rt:
                blocks.append(_block_quote(rt))
            return

        if name == "pre":
            text = node.get_text("\n", strip=False)
            if text.strip():
                blocks.append(_block_code(text))
            return

        if name == "hr":
            blocks.append(_block_divider())
            return

        if name == "img":
            _emit_inline_images(node, msg, resource_handler, blocks)
            return

        if name == "table":
            # Tabellen vereinfacht als Code-Block (Notion-Tabellen brauchen
            # spezielle Vorabstrukturen). Teams-Messages enthalten selten Tabellen.
            text = node.get_text("\n", strip=True)
            if text:
                blocks.append(_block_paragraph(_rich_text(text)))
            return

        # Default: rekursiv
        rt = _build_inline_rich_text(node, mentions_by_id)
        if rt:
            blocks.append(_block_paragraph(rt))

    for top in soup.children:
        render(top)

    return blocks


def _emit_inline_images(parent_node: Tag, msg: Message, resource_handler, blocks: List[Dict[str, Any]]):
    """Innerhalb eines Tags vorkommende `<img>` zu Notion-Bloecken machen."""
    if resource_handler is None:
        return
    for img in parent_node.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if not src:
            continue
        block = resource_handler.process_message_image(src, msg.id)
        if block:
            blocks.append(block)


_IMAGE_EXT_RE = re.compile(r"\.(png|jpe?g|gif|webp|bmp|svg)$", re.IGNORECASE)
_HASH_FILENAME_RE = re.compile(r"^([0-9a-f]{16,64})\.[a-z0-9]+$", re.IGNORECASE)


def _looks_like_image(att) -> bool:
    """Heuristik: Ist dieses Attachment ein Bild?

    Microsoft schickt fuer Inline-Bilder oft `contentType=null`, `contentUrl=null`
    und nur einen Filename wie `<hex-guid>.png` — daher Datei-Endung pruefen.
    """
    ct = (att.content_type or "").lower()
    if ct.startswith("image/"):
        return True
    if att.name and _IMAGE_EXT_RE.search(att.name):
        return True
    return False


def _hosted_id_from_attachment(att) -> Optional[str]:
    """hostedContent-ID aus Attachment ableiten.

    Microsoft setzt bei Inline-Bildern entweder `id` oder kodiert die ID in den
    Filename (32 Hex-Zeichen + Extension).
    """
    if att.id:
        return att.id
    if att.name:
        m = _HASH_FILENAME_RE.match(att.name)
        if m:
            return m.group(1)
    return None


def build_attachment_blocks(msg: Message, resource_handler=None) -> List[Dict[str, Any]]:
    """Anhaenge der Message als Notion-Bloecke.

    Verhalten je nach Typ:
      - SharePoint-Datei mit `contentUrl` (http/https): bookmark-Block.
      - Bild-Anhang (per contentType oder Filename-Endung): hostedContent-Upload
        ueber ResourceHandler (gecacht, dedupliziert Inline-Bilder im Body).
      - Sonstige Datei-Anhaenge ohne URL: Filename als Text mit 📎-Marker.

    Bilder werden ggf. via SharePoint-Shares-API direkt heruntergeladen und
    eingebettet; Dateien (PDF/DOCX/...) analog als File-Block. Bei Fehlschlag
    oder Notion-Upload-Limit (>20 MB) wird auf einen Bookmark zurueckgefallen.
    """
    blocks: List[Dict[str, Any]] = []

    for att in msg.attachments:
        is_image = _looks_like_image(att)

        # 1a) Bild mit URL → Shares-API-Download + Image-Block
        if att.content_url and _is_url(att.content_url) and is_image and resource_handler is not None:
            image_block = resource_handler.download_image_from_url(
                att.content_url, att.name or att.id
            )
            if image_block:
                blocks.append(image_block)
                continue
            # Fallthrough zum Bookmark-Fallback

        # 1b) Datei mit URL (PDF/DOCX/XLSX/...) → Shares-API-Download + File-Block
        if att.content_url and _is_url(att.content_url) and not is_image and resource_handler is not None:
            file_block = resource_handler.download_file_from_url(
                att.content_url, att.name or att.id
            )
            if file_block:
                blocks.append(file_block)
                continue
            # Fallthrough zum Bookmark-Fallback (Datei >20MB oder Download fehlgeschlagen)

        # 1c) Anhang mit URL, Download fehlgeschlagen → Bookmark
        if att.content_url and _is_url(att.content_url):
            label = att.name or "Anhang"
            blocks.append({
                "object": "block",
                "type": "bookmark",
                "bookmark": {
                    "url": att.content_url,
                    "caption": _rich_text(f"📎 {label}"),
                },
            })
            continue

        # 2) Bild ohne URL → hostedContent-Direct-Download
        if is_image:
            hosted_id = _hosted_id_from_attachment(att)
            if resource_handler is not None and hosted_id:
                image_block = resource_handler.process_hosted_content_image(hosted_id, msg.id)
                if image_block:
                    blocks.append(image_block)
                    continue
            blocks.append(_block_paragraph(
                _rich_text(f"🖼 {att.name or hosted_id or 'Bild'} "
                           f"(Bild konnte nicht geladen werden)",
                           italic=True, color="gray")
            ))
            continue

        # 3) Sonstige Anhaenge ohne URL: nur Filename anzeigen
        if att.name:
            blocks.append(_block_paragraph(
                _rich_text(f"📎 {att.name}", italic=True, color="gray")
            ))

    return blocks


def build_reactions_paragraph(msg: Message) -> Optional[Dict[str, Any]]:
    """Eine kursive Zeile mit allen Reactions (oder None)."""
    if not msg.reactions:
        return None
    # Nach Reaction-Typ gruppieren
    grouped: Dict[str, List[Reaction]] = {}
    for r in msg.reactions:
        grouped.setdefault(r.reaction_type, []).append(r)
    parts: List[str] = []
    for rtype, reactions in grouped.items():
        emoji = REACTION_EMOJI.get(rtype, rtype)
        names = ", ".join(r.user_display_name for r in reactions)
        parts.append(f"{emoji} {len(reactions)} ({names})")
    text = "  ".join(parts)
    return _block_paragraph(_rich_text(text, italic=True, color="gray"))


def build_message_toggle(msg: Message, resource_handler=None) -> Dict[str, Any]:
    """Komplette Toggle-Struktur fuer eine Message (inkl. Replies)."""
    children: List[Dict[str, Any]] = []
    children.extend(build_body_blocks(msg, resource_handler))
    children.extend(build_attachment_blocks(msg, resource_handler))

    reactions_block = build_reactions_paragraph(msg)
    if reactions_block:
        children.append(reactions_block)

    if msg.replies:
        for reply in msg.replies:
            reply_block = build_message_toggle(reply, resource_handler)
            if reply_block is not None:
                children.append(reply_block)

    # Notion-Limit: max 100 children pro Block-Erstellung. Lange Replies/Bodies
    # werden ggf. abgeschnitten — den Hinweis ergaenzen wir am Ende.
    truncated = False
    if len(children) > 100:
        truncated = True
        children = children[:99]
        children.append(_block_paragraph(
            _rich_text("[…] weitere Inhalte abgeschnitten (Notion-Limit 100 children)",
                       italic=True, color="red")
        ))

    if msg.is_deleted:
        children.insert(0, _block_paragraph(
            _rich_text("[geloeschte Nachricht]", italic=True, color="red")
        ))

    if not children:
        # Leere Messages (z. B. nur Reaktion ohne Body) komplett weglassen.
        return None

    return {
        "object": "block",
        "type": "toggle",
        "toggle": {
            "rich_text": build_header_rich_text(msg),
            "children": children,
        },
    }
