#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OneNote HTML Parser - basiert auf v0.8.4 (bewährt)

Parst OneNote HTML und erstellt Notion-Blöcke.
Bilder werden INLINE verarbeitet während des Parsens.
"""
import re
import time
import requests
from typing import List, Dict, Any, Tuple, Optional
from bs4 import BeautifulSoup, NavigableString, Tag


# Marker für unvollständige Links (für Pass 2)
INCOMPLETE_LINK_MARKER = " (Verlinkung unvollständig)"


def is_onenote_internal_link(href: str) -> bool:
    """Prüft ob ein Link ein OneNote-interner Link ist."""
    if not href:
        return False
    return (
        href.startswith("onenote:") or
        "page-id=" in href.lower() or
        "&section-id=" in href.lower() or
        "onenote/pages/" in href.lower()
    )


def extract_page_id_from_link(href: str) -> Optional[str]:
    """Extrahiert die OneNote Page-ID aus verschiedenen Link-Formaten."""
    if not href:
        return None
    
    patterns = [
        r"page-id=\{?([a-f0-9-]+)\}?",  # page-id={guid} oder page-id=guid
        r"page-id=([^&]+)",              # page-id=...&
        r"/pages/([^/?\s]+)",            # /pages/id
    ]
    
    for pattern in patterns:
        match = re.search(pattern, href, re.IGNORECASE)
        if match:
            return match.group(1).strip("{}")
    
    return None


def is_notion_valid_url(href: str) -> bool:
    """Prüft ob eine URL von der Notion API akzeptiert wird.

    Notion akzeptiert nur http/https URLs. file:///, mailto:, ftp://,
    Netzwerkpfade (\\\\server) und andere Schemata werden abgelehnt
    und lassen den gesamten Block-Batch fehlschlagen.
    """
    if not href:
        return False
    h = href.strip()
    return h.startswith("http://") or h.startswith("https://") or h.startswith("onenote:")


def process_onenote_link(href: str) -> Tuple[str, str]:
    """
    Verarbeitet einen Link und markiert OneNote-interne Links.

    Returns:
        (url, suffix) - URL bleibt erhalten, suffix wird an Text angehängt.
        Gibt (None, suffix) zurück wenn die URL ungültig ist.
    """
    if is_onenote_internal_link(href):
        # OneNote-interner Link: Original-URL behalten, aber markieren
        return href, INCOMPLETE_LINK_MARKER

    # Ungültige URLs (file:///, mailto:, Netzwerkpfade etc.) entfernen
    if not is_notion_valid_url(href):
        return None, f" [Link: {href}]"

    # Normaler externer Link
    return href, ""


def process_list_recursive(
    list_el: Tag,
    depth: int = 0,
    max_depth: int = 3,
    checkbox_unicode_true: Tuple = ("☑", "✅", "✓", "✔"),
    checkbox_unicode_false: Tuple = ("☐", "⬜", "☒", "◻"),
    handle_images_fn=None,
    blocks_ref=None
) -> List[Dict[str, Any]]:
    """
    Rekursive Listen-Verarbeitung mit Nested List Support (max. 3 Ebenen).
    
    Args:
        list_el: Das ul/ol Element
        depth: Aktuelle Verschachtelungstiefe (0-2)
        max_depth: Maximale Verschachtelungstiefe (Standard: 3)
        checkbox_unicode_true: Tuple mit Unicode-Zeichen für aktivierte Checkboxen
        checkbox_unicode_false: Tuple mit Unicode-Zeichen für deaktivierte Checkboxen
        handle_images_fn: Funktion zur Bildverarbeitung (optional)
        blocks_ref: Referenz zur blocks-Liste für Bilder (optional)
        
    Returns:
        Liste von Notion-Blöcken
    """
    items: List[Dict[str, Any]] = []
    ordered = (list_el.name.lower() == "ol")
    block_type = "numbered_list_item" if ordered else "bulleted_list_item"
    
    for li in list_el.find_all("li", recursive=False):
        # Bilder-Check (wenn Funktion übergeben wurde)
        # Bilder werden zu blocks_ref hinzugefügt, Text wird trotzdem extrahiert
        if handle_images_fn and blocks_ref is not None:
            handle_images_fn(li, create_paragraph=False)
        
        # To-Do Detection
        checked = False
        is_todo = False
        
        # Checkbox input
        cb = li.find("input", {"type": "checkbox"})
        if cb:
            is_todo = True
            checked = cb.has_attr("checked")
        
        # data-tag="to-do"
        if not is_todo and (li.get("data-tag") and "to-do" in li.get("data-tag", "").lower()):
            is_todo = True
        
        # Checkbox als Bild
        if not is_todo:
            img = li.find("img")
            if img and any(x in (img.get("alt", "").lower()) for x in ["to do", "todo", "checked", "unchecked"]):
                is_todo = True
                checked = "check" in img.get("alt", "").lower()
        
        # Unicode-Checkboxen
        if not is_todo:
            text = li.get_text(" ", strip=True)
            if text.startswith(checkbox_unicode_true):
                is_todo = True
                checked = True
            elif text.startswith(checkbox_unicode_false):
                is_todo = True
                checked = False
            elif re.match(r"^\s*\[(x|X)\]\s+", text):
                is_todo = True
                checked = True
            elif re.match(r"^\s*\[\s\]\s+", text):
                is_todo = True
                checked = False
        
        # Block erstellen
        if is_todo:
            item = {
                "object": "block",
                "type": "to_do",
                "to_do": {
                    "rich_text": build_rich_text(li, exclude_nested_lists=True),
                    "checked": checked
                }
            }
        else:
            item = {
                "object": "block",
                "type": block_type,
                block_type: {
                    "rich_text": build_rich_text(li, exclude_nested_lists=True)
                }
            }
        
        # Verschachtelte Liste finden und verarbeiten (wenn noch nicht max depth)
        if depth < max_depth - 1:  # -1 weil depth bei 0 startet
            nested_list = li.find(["ul", "ol"], recursive=False)
            if nested_list:
                children = process_list_recursive(
                    nested_list,
                    depth=depth + 1,
                    max_depth=max_depth,
                    checkbox_unicode_true=checkbox_unicode_true,
                    checkbox_unicode_false=checkbox_unicode_false,
                    handle_images_fn=handle_images_fn,
                    blocks_ref=blocks_ref
                )
                if children:
                    # Children zum Block hinzufügen
                    if is_todo:
                        item["to_do"]["children"] = children
                    else:
                        item[block_type]["children"] = children
        
        items.append(item)
    
    return items


def build_rich_text(node: Tag, exclude_nested_lists: bool = False) -> List[Dict[str, Any]]:
    """
    Rich-Text aus HTML-Element erstellen mit Formatierungs-Support.
    
    Unterstützt: bold, italic, underline, strikethrough, code
    Erkennt sowohl HTML-Tags als auch CSS-Styles!
    """
    parts: List[Dict[str, Any]] = []
    
    def _css_color_to_notion(css_value: str) -> Optional[str]:
        """Mappt einen CSS-Farbwert auf einen Notion-Farbnamen.

        Notion kennt: gray, brown, orange, yellow, green, blue, purple, pink, red.
        Plus Hintergrundfarben: *_background.
        """
        if not css_value:
            return None
        v = css_value.strip().lower()

        # Benannte CSS-Farben → Notion
        name_map = {
            "red": "red", "darkred": "red", "crimson": "red", "firebrick": "red",
            "green": "green", "darkgreen": "green", "lime": "green", "limegreen": "green",
            "forestgreen": "green", "seagreen": "green", "olive": "green",
            "blue": "blue", "darkblue": "blue", "navy": "blue", "royalblue": "blue",
            "mediumblue": "blue", "dodgerblue": "blue",
            "orange": "orange", "darkorange": "orange", "orangered": "orange",
            "yellow": "yellow", "gold": "yellow", "khaki": "yellow",
            "purple": "purple", "darkviolet": "purple", "indigo": "purple",
            "magenta": "purple", "mediumorchid": "purple", "blueviolet": "purple",
            "pink": "pink", "hotpink": "pink", "deeppink": "pink",
            "lightpink": "pink", "fuchsia": "pink",
            "brown": "brown", "saddlebrown": "brown", "sienna": "brown",
            "maroon": "brown", "chocolate": "brown",
            "gray": "gray", "grey": "gray", "darkgray": "gray", "darkgrey": "gray",
            "dimgray": "gray", "dimgrey": "gray", "slategray": "gray",
        }
        if v in name_map:
            return name_map[v]

        # Hex-Farben → RGB → nächste Notion-Farbe
        r, g, b = None, None, None
        if v.startswith("#"):
            hexval = v[1:]
            if len(hexval) == 3:
                hexval = hexval[0]*2 + hexval[1]*2 + hexval[2]*2
            if len(hexval) == 6:
                r, g, b = int(hexval[0:2], 16), int(hexval[2:4], 16), int(hexval[4:6], 16)
        elif v.startswith("rgb"):
            m = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", v)
            if m:
                r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))

        if r is not None:
            # Schwarz/Weiss/sehr helle Farben ignorieren
            if r + g + b < 60:  # fast schwarz
                return None
            if r + g + b > 700:  # fast weiss
                return None

            # Dominante Farbe bestimmen
            if r > 180 and g < 100 and b < 100:
                return "red"
            if g > 150 and r < 100 and b < 100:
                return "green"
            if r < 100 and g < 100 and b > 150:
                return "blue"
            if r > 180 and g > 100 and b < 80:
                return "orange"
            if r > 180 and g > 180 and b < 100:
                return "yellow"
            if r > 140 and b > 140 and g < 100:
                return "purple"
            if r > 180 and g < 130 and b > 130:
                return "pink"
            if r > 100 and g < 80 and b < 60:
                return "brown"
            if abs(r - g) < 40 and abs(g - b) < 40 and 60 < r < 180:
                return "gray"
            # Gemischte Farben: nächste Zuordnung
            if r >= g and r >= b:
                return "red" if r > 180 else "brown"
            if g >= r and g >= b:
                return "green"
            if b >= r and b >= g:
                return "blue"

        return None

    def parse_style_annotations(style_str: str) -> dict:
        """Parse CSS style string und extrahiere Formatierungs-Annotations inkl. Farbe."""
        annotations = {
            "bold": False,
            "italic": False,
            "strikethrough": False,
            "underline": False,
            "code": False,
            "color": None,       # Notion text color (z.B. "red", "green")
        }

        if not style_str:
            return annotations

        style_lower = style_str.lower()

        # Bold: font-weight:bold oder font-weight:700+
        if "font-weight:bold" in style_lower or any(f"font-weight:{w}" in style_lower for w in ["700", "800", "900"]):
            annotations["bold"] = True

        # Italic: font-style:italic
        if "font-style:italic" in style_lower:
            annotations["italic"] = True

        # Underline: text-decoration:underline
        if "text-decoration:underline" in style_lower:
            annotations["underline"] = True

        # Strikethrough: text-decoration:line-through
        if "text-decoration:line-through" in style_lower:
            annotations["strikethrough"] = True

        # Textfarbe: color:... (NICHT background-color)
        # Suche "color:" aber nicht "background-color:"
        m = re.search(r'(?<!-)color\s*:\s*([^;]+)', style_lower)
        if m:
            notion_color = _css_color_to_notion(m.group(1).strip())
            if notion_color:
                annotations["color"] = notion_color

        # Hintergrundfarbe: background-color:... oder background:...
        m = re.search(r'background(?:-color)?\s*:\s*([^;]+)', style_lower)
        if m:
            bg_color = _css_color_to_notion(m.group(1).strip())
            if bg_color:
                annotations["color"] = f"{bg_color}_background"

        return annotations
    
    def process_node(n, annotations=None):
        """Rekursiv durch DOM mit Annotations-Stack."""
        if annotations is None:
            annotations = {
                "bold": False,
                "italic": False,
                "strikethrough": False,
                "underline": False,
                "code": False,
                "color": None,
            }
        
        if isinstance(n, NavigableString):
            # Text mit aktuellen Formatierungen
            text = str(n)
            if text:
                parts.append({
                    "type": "text",
                    "text": {"content": text},
                    "annotations": annotations.copy()
                })
        elif isinstance(n, Tag):
            tag_name = n.name.lower()
            
            # Verschachtelte Listen überspringen wenn gewünscht (für Nested List Support)
            if exclude_nested_lists and tag_name in ("ul", "ol"):
                return
            
            # Neue Annotations basierend auf Tag UND Style
            new_annotations = annotations.copy()
            
            # ZUERST: CSS Styles parsen (OneNote verwendet diese!)
            style = n.get("style")
            if style:
                style_annotations = parse_style_annotations(str(style))
                # Merge mit existing annotations (OR-Logik für Booleans)
                for key in ("bold", "italic", "strikethrough", "underline", "code"):
                    if style_annotations.get(key):
                        new_annotations[key] = True
                # Farbe: inneres Element überschreibt äußeres
                if style_annotations.get("color"):
                    new_annotations["color"] = style_annotations["color"]
            
            # DANN: HTML-Tags (für andere Quellen)
            # Bold
            if tag_name in ("strong", "b"):
                new_annotations["bold"] = True
            
            # Italic
            elif tag_name in ("em", "i"):
                new_annotations["italic"] = True
            
            # Underline
            elif tag_name == "u":
                new_annotations["underline"] = True
            
            # Strikethrough
            elif tag_name in ("strike", "s", "del"):
                new_annotations["strikethrough"] = True
            
            # Code (inline)
            elif tag_name == "code":
                new_annotations["code"] = True
            
            # Links - spezielle Behandlung
            if tag_name == "a":
                href = n.get("href")
                if href:
                    # Link-Text mit aktuellen Formatierungen
                    txt = n.get_text()
                    if txt:
                        # OneNote-interne Links erkennen und markieren
                        link_url, link_suffix = process_onenote_link(href)
                        display_text = txt + link_suffix if link_suffix else txt
                        text_obj = {"content": display_text}
                        if link_url:
                            text_obj["link"] = {"url": link_url}
                        parts.append({
                            "type": "text",
                            "text": text_obj,
                            "annotations": new_annotations.copy()
                        })
                    return  # Kinder nicht mehr verarbeiten
            
            # Kinder rekursiv verarbeiten
            for child in n.children:
                process_node(child, new_annotations)
    
    # Verarbeitung starten
    process_node(node)
    
    # Whitespace-only Text-Parts entfernen (führen zu Problemen)
    parts = [p for p in parts if p["type"] != "text" or p["text"]["content"].strip()]
    
    # Notion-Limit: 2000 Zeichen pro rich_text Element — splitten statt abschneiden
    split_parts = []
    for p in parts:
        if p["type"] == "text" and len(p["text"]["content"]) > 2000:
            content = p["text"]["content"]
            annotations = p.get("annotations")
            link = p["text"].get("link")
            for i in range(0, len(content), 2000):
                chunk = {"type": "text", "text": {"content": content[i:i+2000]}}
                if link:
                    chunk["text"]["link"] = link
                if annotations:
                    chunk["annotations"] = annotations
                split_parts.append(chunk)
        else:
            split_parts.append(p)
    parts = split_parts
    
    # Annotations bereinigen
    for p in parts:
        if "annotations" in p:
            ann = p["annotations"]
            # color=None entfernen (Notion akzeptiert kein null)
            if "color" in ann and not ann["color"]:
                del ann["color"]
            # Komplett leere Annotations entfernen
            if not any(ann.values()):
                del p["annotations"]
    
    return parts or [{"type": "text", "text": {"content": ""}}]


def html_to_blocks_and_tables(
    html: str,
    site_id: str,
    ms_graph_client,
    notion_client
) -> Tuple[List[Dict[str, Any]], List[List[List[str]]]]:
    """
    OneNote HTML zu Notion-Blöcken konvertieren.
    
    WICHTIG: Bilder werden INLINE während des Parsens verarbeitet!
    
    Args:
        html: OneNote HTML-Content
        site_id: SharePoint Site-ID
        ms_graph_client: MSGraphClient für Resource-Downloads
        notion_client: NotionClient für Uploads
        
    Returns:
        (blocks, tables) - Notion-Blöcke und Tabellen
    """
    soup = BeautifulSoup(html, "html.parser")
    blocks: List[Dict[str, Any]] = []
    tables: List[List[List[str]]] = []
    
    # Helper-Funktionen für Block-Erstellung
    def add_paragraph_rich(el):
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": build_rich_text(el)}
        })
    
    def add_heading(level, el):
        k = f"heading_{level}"
        blocks.append({
            "object": "block",
            "type": k,
            k: {"rich_text": build_rich_text(el)}
        })
    
    def add_todo(el, checked=False):
        blocks.append({
            "object": "block",
            "type": "to_do",
            "to_do": {"rich_text": build_rich_text(el), "checked": checked}
        })
    
    def add_quote(el):
        blocks.append({
            "object": "block",
            "type": "quote",
            "quote": {"rich_text": build_rich_text(el)}
        })
    
    def add_code(text):
        blocks.append({
            "object": "block",
            "type": "code",
            "code": {
                "rich_text": [{"type": "text", "text": {"content": text}}],
                "language": "plain_text"
            }
        })
    
    def rewrite_resource_url_to_graph(site_id: str, href: str) -> Optional[str]:
        """OneNote Resource-URL zu Graph API URL umschreiben oder korrigieren.
        
        Unterstützt verschiedene URL-Formate:
        1. siteCollections-Format: https://graph.microsoft.com/v1.0/siteCollections/.../$value
           → wird zu /sites/...//content umgeschrieben
        2. Relative URLs: /onenote/resources/{id} → Graph API URL
        3. Bereits korrekte /sites/ URLs: werden direkt zurückgegeben
        """
        # Fall 1: siteCollections-Format (MUSS umgeschrieben werden!)
        if href.startswith("https://graph.microsoft.com/") and "/siteCollections/" in href:
            # Extrahiere Resource-ID aus URL
            m = re.search(r"/onenote/resources/([^/$?]+)", href)
            if m:
                res_id = m.group(1)
                # Korrigiere URL: siteCollections → sites, $value → content
                return f"https://graph.microsoft.com/v1.0/sites/{site_id}/onenote/resources/{res_id}/content"
            return None
        
        # Fall 2: Bereits korrekte /sites/ URL
        if href.startswith("https://graph.microsoft.com/") and "/sites/" in href:
            if "/onenote/resources/" in href:
                # URL ist bereits korrekt formatiert
                return href
            return None
        
        # Fall 3: Relative OneNote Resource-URL
        m = re.search(r"/onenote/resources/([^/?]+)", href)
        if not m:
            return None
        res_id = m.group(1)
        return f"https://graph.microsoft.com/v1.0/sites/{site_id}/onenote/resources/{res_id}/content"
    
    def fetch_resource(url: str) -> Tuple[Optional[bytes], Optional[str], str]:
        """Resource von OneNote herunterladen."""
        if not url:
            return None, None, "file"
        
        orig_url = url
        
        # OneNote Resource-URLs umschreiben
        if "/onenote/resources/" in url:
            fixed = rewrite_resource_url_to_graph(site_id, url)
            if fixed:
                url = fixed
        
        try:
            # MS Graph Auth Headers (Web-kompatibel via _get_headers)
            headers = ms_graph_client._get_headers()
            r = requests.get(url, headers=headers)
            r.raise_for_status()
            
            raw = r.content
            header_ct = r.headers.get("Content-Type", "").split(";")[0].strip() or None
            
            # Content-Type Detection (aus core.utils)
            from core.utils import detect_content_type_and_filename
            final_ct, safe_name = detect_content_type_and_filename(raw, header_ct, orig_url)
            
            return raw, final_ct, safe_name
        except Exception as e:
            print(f"[⚠] Media fetch failed: {e}")
            return None, None, "file"
    
    def handle_images_with_split(el: Tag, create_paragraph=True):
        """
        WORKAROUND: Paragraphen aufbrechen und Bilder dazwischen einfügen!
        
        Sammelt Text vor/nach Bildern und erstellt separate Blöcke:
        - Text vor Bild → Paragraph 1
        - Bild → Image Block  
        - Text nach Bild → Paragraph 2
        """
        # Finde alle Bilder (auch verschachtelte)
        imgs = el.find_all("img")
        
        if not imgs:
            return False  # Keine Bilder gefunden
        
        # Clone des Elements für Text-Extraktion
        import copy
        el_copy = copy.copy(el)
        
        # Sammle alle Text-Teile und Bilder in korrekter Reihenfolge
        parts = []
        current_text = []
        
        for child in el.children:
            if isinstance(child, Tag) and child.name == "img":
                # Text vor dem Bild speichern
                if current_text:
                    text_content = ''.join(str(t) for t in current_text).strip()
                    if text_content:
                        # Erstelle temporäres Element für rich_text
                        temp = BeautifulSoup(f'<span>{text_content}</span>', 'html.parser').span
                        parts.append(('text', build_rich_text(temp)))
                    current_text = []
                
                # Bild verarbeiten
                img_id = id(child)
                if img_id not in processed_imgs:
                    processed_imgs.add(img_id)
                    src = child.get("data-fullres-src") or child.get("data-src") or child.get("src")
                    if src:
                        parts.append(('image', src))
            else:
                # Text sammeln
                current_text.append(child)
        
        # Restlichen Text nach dem letzten Bild
        if current_text:
            text_content = ''.join(str(t) for t in current_text).strip()
            if text_content:
                temp = BeautifulSoup(f'<span>{text_content}</span>', 'html.parser').span
                parts.append(('text', build_rich_text(temp)))
        
        # Wenn nur Text (keine Bilder in direkten Kindern), prüfe verschachtelte
        if all(p[0] == 'text' for p in parts) or not parts:
            # Fallback: Bilder sind tiefer verschachtelt — Text trotzdem extrahieren
            el_text = build_rich_text(el)
            has_text = any(
                rt.get("text", {}).get("content", "").strip()
                for rt in el_text if rt.get("type") == "text"
            )
            if has_text and create_paragraph:
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": el_text}
                })
            for img in imgs:
                img_id = id(img)
                if img_id not in processed_imgs:
                    processed_imgs.add(img_id)
                    src = img.get("data-fullres-src") or img.get("data-src") or img.get("src")
                    if src:
                        print(f"[📸] Bild gefunden: {src[:100]}")
                        data, ctype, fname = fetch_resource(src)
                        if data:
                            print(f"[📥] Bild heruntergeladen: {fname} ({len(data)} bytes, {ctype})")
                            upload_id = notion_client.upload_file(fname, data, ctype)
                            if upload_id:
                                print(f"[✅] Bild hochgeladen: {upload_id}")
                                blocks.append(notion_client.create_image_block(upload_id))
                            else:
                                print(f"[❌] Bild-Upload fehlgeschlagen: {fname}")
                        else:
                            print(f"[❌] Bild-Download fehlgeschlagen: {src[:100]}")
            return len(imgs) > 0
        
        # Erstelle Blöcke in korrekter Reihenfolge
        for part_type, content in parts:
            if part_type == 'text' and create_paragraph:
                # Text als Paragraph
                if content:  # content ist bereits rich_text
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": content}
                    })
            elif part_type == 'image':
                # Bild hochladen und einfügen
                src = content
                print(f"[📸] Bild gefunden: {src[:100]}")
                data, ctype, fname = fetch_resource(src)
                if data:
                    print(f"[📥] Bild heruntergeladen: {fname} ({len(data)} bytes, {ctype})")
                    upload_id = notion_client.upload_file(fname, data, ctype)
                    if upload_id:
                        print(f"[✅] Bild hochgeladen: {upload_id}")
                        blocks.append(notion_client.create_image_block(upload_id))
                    else:
                        print(f"[❌] Bild-Upload fehlgeschlagen: {fname}")
                else:
                    print(f"[❌] Bild-Download fehlgeschlagen: {src[:100]}")
        
        return True  # Bilder wurden verarbeitet
    
    # Checkbox-Unicode-Zeichen
    checkbox_unicode_true = ("☑", "✅", "✓", "✔")
    checkbox_unicode_false = ("☐", "⬜", "☒", "◻")
    
    body = soup.body or soup
    
    # Track bereits verarbeitete Bilder (um Duplikate zu vermeiden)
    processed_imgs = set()
    
    # Hauptloop: Alle Elemente durchgehen
    for el in body.descendants:
        if not isinstance(el, Tag):
            continue
        
        name = el.name.lower()
        
        # Headings
        if name in ("h1", "h2", "h3"):
            add_heading(int(name[1]), el)
        
        # Blockquote
        elif name == "blockquote":
            add_quote(el)
        
        # Code-Blöcke
        elif name == "pre":
            code_el = el.find("code")
            txt = code_el.get_text() if code_el else el.get_text()
            add_code(txt.strip())
        
        # Listen - mit Nested List Support (max. 3 Ebenen)
        elif name in ("ul", "ol"):
            # Nur top-level Listen verarbeiten (nicht verschachtelte)
            if el.parent and el.parent.name == "li":
                continue  # Überspringe - wird von Parent verarbeitet
            
            list_blocks = process_list_recursive(
                el, 
                depth=0, 
                max_depth=3,
                checkbox_unicode_true=checkbox_unicode_true,
                checkbox_unicode_false=checkbox_unicode_false,
                handle_images_fn=handle_images_with_split,
                blocks_ref=blocks
            )
            blocks.extend(list_blocks)
        
        # Paragraphen
        elif name == "p":
            # WORKAROUND: Paragraphen mit Bildern aufbrechen!
            has_images = handle_images_with_split(el, create_paragraph=True)
            
            if not has_images:
                # Keine Bilder - normale Verarbeitung
                # To-Do Detection in Paragraphen
                is_todo = False
                checked = False
                
                if el.get("data-tag") and "to-do" in el.get("data-tag", "").lower():
                    is_todo = True
                
                txt = el.get_text(" ", strip=True)
                if txt.startswith(checkbox_unicode_true):
                    is_todo = True
                    checked = True
                elif txt.startswith(checkbox_unicode_false):
                    is_todo = True
                    checked = False
                elif re.match(r"^\s*\[(x|X)\]\s+", txt):
                    is_todo = True
                    checked = True
                elif re.match(r"^\s*\[\s\]\s+", txt):
                    is_todo = True
                    checked = False
                
                if is_todo:
                    add_todo(el, checked=checked)
                elif el.get_text(strip=True):
                    add_paragraph_rich(el)
        
        # Tabellen
        elif name == "table":
            rows = []
            for tr in el.find_all("tr", recursive=True):
                # Überspringe <tr> aus verschachtelten Sub-Tabellen
                if tr.find_parent("table") != el:
                    continue
                cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"], recursive=False)]
                if cells:
                    rows.append(cells)
            if rows:
                tables.append(rows)
        
        # WICHTIG: Direkte <img>-Tags (nicht in <p>) verarbeiten!
        elif name == "img":
            img_id = id(el)
            if img_id not in processed_imgs:
                processed_imgs.add(img_id)
                src = el.get("data-fullres-src") or el.get("data-src") or el.get("src")
                if src:
                    print(f"[📸] Direktes Bild gefunden: {src[:80]}...")
                    data, ctype, fname = fetch_resource(src)
                    if data:
                        print(f"[📥] Bild heruntergeladen: {fname} ({len(data)} bytes, {ctype})")
                        upload_id = notion_client.upload_file(fname, data, ctype)
                        if upload_id:
                            print(f"[✅] Bild hochgeladen: {upload_id}")
                            blocks.append(notion_client.create_image_block(upload_id))
                        else:
                            print(f"[❌] Bild-Upload fehlgeschlagen: {fname}")
                    else:
                        print(f"[❌] Bild-Download fehlgeschlagen: {src[:80]}...")
        
        # Links mit Dateien
        elif name == "a":
            href = el.get("href", "")
            if "/onenote/resources/" in href:
                data, ctype, fname = fetch_resource(href)
                if data:
                    upload_id = notion_client.upload_file(fname, data, ctype)
                    if upload_id:
                        blocks.append(notion_client.create_file_block(upload_id))

        # Fallback: Block-Elemente mit direktem Text (div, span, section, etc.)
        elif name in ("div", "section", "article", "main", "aside", "header", "footer", "figcaption"):
            has_direct_text = any(
                isinstance(child, NavigableString) and child.strip()
                for child in el.children
            )
            if has_direct_text and not el.find(["p", "h1", "h2", "h3", "ul", "ol", "table", "pre", "blockquote"]):
                if el.get_text(strip=True):
                    add_paragraph_rich(el)

    # Fallback: Wenn keine Blöcke erstellt wurden
    if not blocks and soup.get_text(strip=True):
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": soup.get_text(' ', strip=True)}}]
            }
        })
    
    return blocks, tables


def append_table(notion_client, parent_block_id: str, rows: List[List[str]]):
    """
    Tabelle als echte Table-Blöcke zu Notion hinzufügen.
    
    WICHTIG: Notion API erfordert, dass Tabellen MIT ihren Zeilen (children) 
    erstellt werden. Leere Tabellen sind nicht erlaubt!
    
    Args:
        notion_client: NotionClient-Instanz
        parent_block_id: Parent-Block-ID (Page oder Block)
        rows: Tabellenzeilen
    """
    if not rows:
        return
    
    # Berechne Tabellenbreite (max. Spalten in allen Zeilen)
    table_width = max(len(r) for r in rows) if rows else 1
    
    # Erstelle Row-Blöcke als children
    row_children = []
    for r in rows:
        # Padding: Jede Zeile muss gleich viele Zellen haben
        padded_row = r + [""] * (table_width - len(r))
        cells = [[{"type": "text", "text": {"content": str(c)[:2000]}}] for c in padded_row]
        row_children.append({
            "object": "block",
            "type": "table_row",
            "table_row": {"cells": cells}
        })
    
    # Table-Block MIT children erstellen (Notion API Requirement!)
    table_block = {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": table_width,
            "has_column_header": len(rows) > 1,  # Erste Zeile als Header wenn > 1 Zeile
            "has_row_header": False,
            "children": row_children
        }
    }
    
    # Table mit allen Zeilen auf einmal erstellen
    try:
        notion_client.append_blocks(parent_block_id, [table_block])
        time.sleep(0.12)  # Rate limiting
    except Exception as e:
        print(f"[⚠] Table creation failed: {e}")


# Backward compatibility
def parse_onenote_html(html: str) -> Tuple[List[Dict[str, Any]], List[List[List[str]]]]:
    """
    Legacy-Funktion für Kompatibilität.
    
    WARNUNG: Diese Funktion kann KEINE Bilder verarbeiten!
    Nutze stattdessen html_to_blocks_and_tables() mit den nötigen Clients.
    """
    print("[⚠] WARNING: parse_onenote_html() kann keine Bilder verarbeiten!")
    print("[⚠] Nutze html_to_blocks_and_tables() mit ms_graph_client und notion_client!")
    
    # Dummy-Parser ohne Bild-Support
    soup = BeautifulSoup(html, "html.parser")
    blocks = []
    tables = []
    
    # Sehr vereinfacht...
    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if text:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": text[:2000]}}]}
            })
    
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            rows.append(cells)
        if rows:
            tables.append(rows)
    
    return blocks, tables
