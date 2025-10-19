#!/usr/bin/env python3
"""Test script um OneNote HTML Format für Formatierungen zu analysieren."""

from core.auth import AuthManager
from core.ms_graph_client import MSGraphClient

# Auth initialisieren
auth_mgr = AuthManager()
auth_mgr.initialize()

ms = MSGraphClient(auth_mgr)

# Die Seite '25-09-12 Intern JO/DO' laden
# Diese Seite hat laut Screenshot fette Texte
# OneNote Page IDs sind zusammengesetzt: page_id!notebook_id
page_id = '1-53597af752ce05261d53b5eb74df3755!1-22fc3e26-714a-4503-8865-d7032f8cffd6'

# HTML laden mit der bekannten Site-ID
site_id = 'loupz.sharepoint.com,b840ec02-ae30-40e3-beab-3a7aaada7bf1,e579d2e3-11f5-4108-a542-3719dacd4910'
content = ms.get_page_content(site_id, page_id)
html = content.decode('utf-8')

# Suche nach 'Allgemein' - das sollte fett sein
import re

print("=== Suche nach 'Allgemein' (sollte fett sein) ===")
matches = re.findall(r'.{200}Allgemein.{200}', html, re.DOTALL)
if matches:
    print(matches[0])
    print("\n" + "="*80 + "\n")
    
# Suche nach 'Notizen' - sollte auch fett sein  
print("=== Suche nach 'Notizen' (sollte fett sein) ===")
matches2 = re.findall(r'.{200}Notizen.{200}', html, re.DOTALL)
if matches2:
    print(matches2[0])
    print("\n" + "="*80 + "\n")

# Suche nach style-Attributen
print("=== Alle style-Attribute im HTML ===")
styles = re.findall(r'style="([^"]+)"', html)
unique_styles = set(styles)
for style in list(unique_styles)[:10]:
    print(f"- {style}")
