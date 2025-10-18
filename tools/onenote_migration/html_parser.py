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


def build_rich_text(node: Tag) -> List[Dict[str, Any]]:
    """Rich-Text aus HTML-Element erstellen."""
    parts: List[Dict[str, Any]] = []
    
    def push_text(text: str):
        if text:
            parts.append({"type": "text", "text": {"content": text}})
    
    for child in node.children:
        if isinstance(child, NavigableString):
            push_text(str(child))
        elif isinstance(child, Tag) and child.name.lower() == "a":
            href = child.get("href")
            txt = child.get_text()
            parts.append({"type": "text", "text": {"content": txt, "link": {"url": href}}})
        elif isinstance(child, Tag):
            parts.extend(build_rich_text(child))
    
    # Notion-Limit: 2000 Zeichen pro rich_text Element
    for p in parts:
        if p["type"] == "text" and len(p["text"]["content"]) > 2000:
            p["text"]["content"] = p["text"]["content"][:2000]
    
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
        """OneNote Resource-URL zu Graph API URL umschreiben."""
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
            # MS Graph Auth Headers
            headers = ms_graph_client.auth.microsoft.headers
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
    
    def handle_images(el: Tag):
        """Bilder INLINE verarbeiten - direkt während des Parsens!"""
        # <img> Tags - Nur direkte Kinder um Duplikate zu vermeiden
        imgs = el.find_all("img", recursive=False)
        for img in imgs:
            # Prüfe ob bereits verarbeitet (um Duplikate zu vermeiden)
            img_id = id(img)
            if img_id in processed_imgs:
                continue
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
        
        # <object> Tags (können auch Bilder oder Dateien sein)
        for obj in el.find_all("object"):  # Default ist recursive=True
            data_url = obj.get("data") or obj.get("data-fullres-src")
            t = (obj.get("type") or "").lower() or None
            if data_url:
                data, ctype, fname = fetch_resource(data_url)
                if data:
                    upload_id = notion_client.upload_file(fname, data, ctype or t)
                    if upload_id:
                        if ((t or ctype) or "").startswith("image/"):
                            blocks.append(notion_client.create_image_block(upload_id))
                        else:
                            blocks.append(notion_client.create_file_block(upload_id))
    
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
        
        # Listen
        elif name in ("ul", "ol"):
            ordered = (name == "ol")
            for li in el.find_all("li", recursive=False):
                # WICHTIG: Bilder in Listen verarbeiten!
                handle_images(li)
                
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
                
                if is_todo:
                    add_todo(li, checked=checked)
                else:
                    t = "numbered_list_item" if ordered else "bulleted_list_item"
                    blocks.append({
                        "object": "block",
                        "type": t,
                        t: {"rich_text": build_rich_text(li)}
                    })
        
        # Paragraphen
        elif name == "p":
            # WICHTIG: Bilder HIER verarbeiten, INLINE!
            handle_images(el)
            
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
            for tr in el.find_all("tr", recursive=False):
                cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"], recursive=False)]
                rows.append(cells)
            if rows:
                tables.append(rows)
        
        # Links mit Dateien
        elif name == "a":
            href = el.get("href", "")
            if "/onenote/resources/" in href:
                data, ctype, fname = fetch_resource(href)
                if data:
                    upload_id = notion_client.upload_file(fname, data, ctype)
                    if upload_id:
                        blocks.append(notion_client.create_file_block(upload_id))
    
    # Fallback: Wenn keine Blöcke erstellt wurden
    if not blocks and soup.get_text(strip=True):
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": soup.get_text(' ', strip=True)}}]
            }
        })
    
    # Notion-Limit: Max 150 Blöcke pro Request
    return blocks[:150], tables


def append_table(notion_client, parent_block_id: str, rows: List[List[str]]):
    """
    Tabelle als echte Table-Blöcke zu Notion hinzufügen.
    
    Args:
        notion_client: NotionClient-Instanz
        parent_block_id: Parent-Block-ID (Page oder Block)
        rows: Tabellenzeilen
    """
    if not rows:
        return
    
    # Table-Block erstellen
    table_block = {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": max(len(r) for r in rows),
            "has_column_header": False,
            "has_row_header": False
        }
    }
    
    # Table erstellen und ID holen
    res = notion_client.append_blocks(parent_block_id, [table_block])
    created = res.get("results", [])
    if not created:
        print("[⚠] Table creation failed")
        return
    
    table_id = created[-1].get("id")
    
    # Table-Row Blöcke erstellen
    row_blocks = []
    for r in rows:
        cells = [[{"type": "text", "text": {"content": c[:2000]}}] for c in r]
        row_blocks.append({
            "object": "block",
            "type": "table_row",
            "table_row": {"cells": cells}
        })
    
    # Rows hinzufügen
    notion_client.append_blocks(table_id, row_blocks)
    time.sleep(0.12)  # Rate limiting


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
