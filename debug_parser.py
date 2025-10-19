#!/usr/bin/env python3
"""Debug: HTML-Parser für 'Allgemein' testen."""

from bs4 import BeautifulSoup
from tools.onenote_migration.html_parser import build_rich_text

# Das HTML aus dem OneNote (simplified)
html = '''
<p style="margin-top:0pt;margin-bottom:0pt">
    <span style="font-weight:bold">Allgemein</span>
</p>
'''

soup = BeautifulSoup(html, 'html.parser')
p_tag = soup.find('p')

print("=== HTML ===")
print(p_tag.prettify())
print()

print("=== build_rich_text() Ergebnis ===")
result = build_rich_text(p_tag)
print(result)
print()

print("=== Annotations ===")
for part in result:
    if 'annotations' in part:
        print(f"Text: '{part['text']['content']}'")
        print(f"Bold: {part['annotations']['bold']}")
        print(f"Full annotations: {part['annotations']}")
