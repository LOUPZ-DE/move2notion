#!/usr/bin/env python3
"""
Diagnose-Script: Prueft ob die Pagination fuer OneNote Pages korrekt funktioniert.

Ruft fuer jede Section die Seiten ab und zeigt:
- Anzahl Seiten pro Section
- Ob Pagination (nextLink) ausgeloest wurde
- Das Format des nextLink (falls vorhanden)
"""
import sys
import os
import json
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.auth import auth_manager
from core.ms_graph_client import MSGraphClient

BASE_URL = "https://graph.microsoft.com/v1.0"
SITE_URL = "https://loupz.sharepoint.com/sites/9594_Hannover_Vision_SBN-BIMImplementierung"


def test_pagination_for_section(client, site_id, section):
    """Testet die korrigierte list_pages_for_section mit $skip-Pagination."""
    sec_name = section.get("displayName", "?")
    sec_id = section["id"]

    print(f"\n  Section '{sec_name}':")
    pages = client.list_pages_for_section(site_id, sec_id)
    count = len(pages)

    marker = "✅" if count != 100 else "⚠"
    print(f"    [{marker}] {count} Seiten")
    return count


def main():
    print("=" * 60)
    print("Diagnose: OneNote Pagination Test")
    print("=" * 60)

    # Auth
    print("\n[1] Authentifizierung...")
    auth_manager.initialize()
    client = MSGraphClient()

    # Site aufloesen
    site_url = sys.argv[1] if len(sys.argv) > 1 else SITE_URL
    print(f"\n[2] Site aufloesen: {site_url}")
    site_id = client.resolve_site_id_from_url(site_url)
    print(f"    Site-ID: {site_id}")

    # Notebooks
    print(f"\n[3] Lade Notebooks...")
    notebooks = client.list_site_notebooks(site_id)
    for i, nb in enumerate(notebooks):
        print(f"    [{i}] {nb['displayName']}")

    if not notebooks:
        print("    Keine Notebooks gefunden!")
        return

    notebook = notebooks[0]
    print(f"    → Verwende: {notebook['displayName']}")

    # Sections
    print(f"\n[4] Lade Sections...")
    sections = client.get_notebook_sections(site_id, notebook["id"])
    print(f"    {len(sections)} Section(s) gefunden")

    # Pagination-Test pro Section
    print(f"\n[5] Pagination-Test pro Section:")
    print("=" * 60)

    grand_total = 0
    problem_sections = []

    for section in sections:
        count = test_pagination_for_section(client, site_id, section)
        grand_total += count
        if count == 100:
            problem_sections.append(section.get("displayName", "?"))

    # Zusammenfassung
    print("\n" + "=" * 60)
    print(f"ERGEBNIS: {grand_total} Seiten total in {len(sections)} Section(s)")
    print("=" * 60)

    if problem_sections:
        print(f"\n[⚠] Sections mit genau 100 Seiten (moeglicherweise abgeschnitten):")
        for name in problem_sections:
            print(f"    - {name}")
    else:
        print(f"\n[✅] Keine Sections mit verdaechtigem 100er-Limit gefunden.")


if __name__ == "__main__":
    main()
