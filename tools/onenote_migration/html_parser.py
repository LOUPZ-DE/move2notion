#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTML-Parser für OneNote-zu-Notion Migration.

Dieses Modul behandelt:
- OneNote-HTML-Parsing
- Konvertierung in Notion-Blöcke
- To-Do-Erkennung
- Rich-Text-Generierung
"""
import re
from typing import List, Dict, Any, Tuple
from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString


class OneNoteHTMLParser:
    """Parst OneNote-HTML und konvertiert zu Notion-Blöcken."""

    # Checkbox-Unicode-Zeichen
    CHECKBOX_TRUE = ("☑", "✅", "✓", "✔")
    CHECKBOX_FALSE = ("☐", "⬜", "☒", "◻")

    def __init__(self):
        self.blocks: List[Dict[str, Any]] = []
        self.tables: List[List[List[str]]] = []

    def parse(self, html: str) -> Tuple[List[Dict[str, Any]], List[List[List[str]]]]:
        """HTML parsen und Blöcke + Tabellen extrahieren."""
        self.blocks = []
        self.tables = []

        soup = BeautifulSoup(html, "html.parser")
        body = soup.body or soup

        self._process_element(body)

        # Fallback: Wenn keine Blöcke gefunden wurden, Text extrahieren
        if not self.blocks and soup.get_text(strip=True):
            text = soup.get_text(' ', strip=True)
            self.blocks.append(self._create_paragraph([{"type": "text", "text": {"content": text}}]))

        return self.blocks[:150], self.tables  # Notion-Limit: 150 Blöcke

    def _process_element(self, element: Tag) -> None:
        """Element rekursiv verarbeiten."""
        for child in element.children:
            if not isinstance(child, Tag):
                continue

            name = child.name.lower()

            if name in ("h1", "h2", "h3"):
                self._add_heading(int(name[1]), child)
            elif name == "blockquote":
                self._add_quote(child)
            elif name == "pre":
                self._add_code(child)
            elif name in ("ul", "ol"):
                self._add_list(child, ordered=(name == "ol"))
            elif name == "p":
                self._add_paragraph_or_todo(child)
            elif name == "table":
                self._add_table(child)

    def _build_rich_text(self, element: Tag) -> List[Dict[str, Any]]:
        """Rich-Text aus HTML-Element erstellen."""
        parts: List[Dict[str, Any]] = []

        for child in element.children:
            if isinstance(child, NavigableString):
                text = str(child).strip()
                if text:
                    parts.append({"type": "text", "text": {"content": text}})
            elif isinstance(child, Tag):
                if child.name.lower() == "a":
                    href = child.get("href", "")
                    text = child.get_text()
                    parts.append({
                        "type": "text",
                        "text": {"content": text, "link": {"url": href}}
                    })
                else:
                    # Rekursiv für verschachtelte Tags
                    parts.extend(self._build_rich_text(child))

        # Text auf 2000 Zeichen begrenzen (Notion-Limit)
        result = []
        for part in parts:
            if part["type"] == "text":
                content = part["text"]["content"]
                # Teile lange Texte auf
                if len(content) > 2000:
                    for i in range(0, len(content), 2000):
                        chunk = content[i:i+2000]
                        result.append({"type": "text", "text": {"content": chunk}})
                else:
                    result.append(part)
            else:
                result.append(part)

        return result or [{"type": "text", "text": {"content": ""}}]

    def _create_paragraph(self, rich_text: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Paragraph-Block erstellen."""
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": rich_text}
        }

    def _split_into_multiple_paragraphs(self, rich_text: List[Dict[str, Any]]) -> None:
        """Lange rich_text-Arrays in mehrere Paragraph-Blöcke aufteilen."""
        current_block = []
        current_length = 0
        
        for rt in rich_text:
            content = rt.get("text", {}).get("content", "")
            content_length = len(content)
            
            # Wenn dieses Element allein schon zu groß ist, teile es
            if content_length > 2000:
                # Speichere aktuellen Block falls vorhanden
                if current_block:
                    self.blocks.append(self._create_paragraph(current_block))
                    current_block = []
                    current_length = 0
                
                # Teile großes Element in Chunks
                for i in range(0, content_length, 2000):
                    chunk = content[i:i+2000]
                    chunk_rt = {"type": "text", "text": {"content": chunk}}
                    self.blocks.append(self._create_paragraph([chunk_rt]))
            
            # Wenn Hinzufügen dieses Elements die Grenze überschreitet
            elif current_length + content_length > 2000:
                # Speichere aktuellen Block
                if current_block:
                    self.blocks.append(self._create_paragraph(current_block))
                # Starte neuen Block mit diesem Element
                current_block = [rt]
                current_length = content_length
            else:
                # Füge zu aktuellem Block hinzu
                current_block.append(rt)
                current_length += content_length
        
        # Speichere letzten Block
        if current_block:
            self.blocks.append(self._create_paragraph(current_block))

    def _add_heading(self, level: int, element: Tag) -> None:
        """Überschrift hinzufügen."""
        heading_type = f"heading_{level}"
        self.blocks.append({
            "object": "block",
            "type": heading_type,
            heading_type: {"rich_text": self._build_rich_text(element)}
        })

    def _add_quote(self, element: Tag) -> None:
        """Zitat hinzufügen."""
        self.blocks.append({
            "object": "block",
            "type": "quote",
            "quote": {"rich_text": self._build_rich_text(element)}
        })

    def _add_code(self, element: Tag) -> None:
        """Code-Block hinzufügen."""
        code_el = element.find("code")
        text = code_el.get_text() if code_el else element.get_text()
        self.blocks.append({
            "object": "block",
            "type": "code",
            "code": {
                "rich_text": [{"type": "text", "text": {"content": text.strip()}}],
                "language": "text"
            }
        })

    def _add_list(self, element: Tag, ordered: bool = False) -> None:
        """Liste hinzufügen."""
        list_type = "numbered_list_item" if ordered else "bulleted_list_item"

        for li in element.find_all("li", recursive=False):
            # Prüfen ob To-Do
            is_todo, checked = self._is_todo_item(li)

            if is_todo:
                self.blocks.append({
                    "object": "block",
                    "type": "to_do",
                    "to_do": {
                        "rich_text": self._build_rich_text(li),
                        "checked": checked
                    }
                })
            else:
                self.blocks.append({
                    "object": "block",
                    "type": list_type,
                    list_type: {"rich_text": self._build_rich_text(li)}
                })

    def _add_paragraph_or_todo(self, element: Tag) -> None:
        """Paragraph oder To-Do hinzufügen."""
        # Prüfen ob To-Do
        is_todo, checked = self._is_todo_item(element)

        if is_todo:
            self.blocks.append({
                "object": "block",
                "type": "to_do",
                "to_do": {
                    "rich_text": self._build_rich_text(element),
                    "checked": checked
                }
            })
        elif element.get_text(strip=True):
            rich_text = self._build_rich_text(element)
            
            # Prüfe Gesamt-Länge aller rich_text-Elemente
            total_length = sum(len(rt.get("text", {}).get("content", "")) for rt in rich_text)
            
            if total_length <= 2000:
                # Normal: Ein Block
                self.blocks.append(self._create_paragraph(rich_text))
            else:
                # Zu lang: In mehrere Blöcke aufteilen
                self._split_into_multiple_paragraphs(rich_text)

    def _is_todo_item(self, element: Tag) -> Tuple[bool, bool]:
        """Prüfen ob Element ein To-Do ist."""
        # 1. Checkbox-Input
        checkbox = element.find("input", {"type": "checkbox"})
        if checkbox:
            return True, checkbox.has_attr("checked")

        # 2. Data-Tag-Attribut
        data_tag = str(element.get("data-tag", "")).lower()
        if "to-do" in data_tag:
            return True, False

        # 3. Bild mit Alt-Text
        img = element.find("img")
        if img:
            alt = str(img.get("alt", "")).lower()
            if any(keyword in alt for keyword in ["to do", "todo", "checked", "unchecked"]):
                return True, "check" in alt

        # 4. Unicode-Checkboxen im Text
        text = element.get_text(" ", strip=True)
        if text.startswith(self.CHECKBOX_TRUE):
            return True, True
        elif text.startswith(self.CHECKBOX_FALSE):
            return True, False

        # 5. Markdown-Style Checkboxen
        if re.match(r"^\s*\[(x|X)\]\s+", text):
            return True, True
        elif re.match(r"^\s*\[\s\]\s+", text):
            return True, False

        return False, False

    def _add_table(self, element: Tag) -> None:
        """Tabelle extrahieren."""
        rows = []
        for tr in element.find_all("tr", recursive=False):
            cells = [
                td.get_text(" ", strip=True)
                for td in tr.find_all(["td", "th"], recursive=False)
            ]
            if cells:
                rows.append(cells)

        if rows:
            self.tables.append(rows)


def parse_onenote_html(html: str) -> Tuple[List[Dict[str, Any]], List[List[List[str]]]]:
    """Convenience-Funktion zum HTML-Parsing."""
    parser = OneNoteHTMLParser()
    return parser.parse(html)
