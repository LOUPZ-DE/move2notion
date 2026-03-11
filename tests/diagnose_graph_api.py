#!/usr/bin/env python3
"""
Diagnose-Script: Prüft welche Properties die Microsoft Graph API
für OneNote Pages tatsächlich zurückgibt.

Testet verschiedene $select-Varianten um herauszufinden, ob level/order
verfügbar sind.
"""
import sys
import os
import json
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.auth import auth_manager
from core.ms_graph_client import MSGraphClient

BASE_URL = "https://graph.microsoft.com/v1.0"


def main():
    print("=" * 60)
    print("Diagnose: Graph API OneNote Page Properties")
    print("=" * 60)

    # Auth initialisieren (Device Code Flow)
    print("\n[1] Authentifizierung...")
    auth_manager.initialize()
    client = MSGraphClient()

    # Site-URL vom Benutzer oder als Argument
    if len(sys.argv) > 1:
        site_url = sys.argv[1]
    else:
        site_url = input("SharePoint Site-URL eingeben: ").strip()

    # Site auflösen
    print(f"\n[2] Löse Site auf: {site_url}")
    site_id = client.resolve_site_id_from_url(site_url)
    print(f"    Site-ID: {site_id}")

    # Notebooks laden
    print(f"\n[3] Lade Notebooks...")
    notebooks = client.list_site_notebooks(site_id)
    for i, nb in enumerate(notebooks):
        print(f"    [{i}] {nb['displayName']}")

    if not notebooks:
        print("    Keine Notebooks gefunden!")
        return

    # Erstes Notebook verwenden (oder Auswahl)
    nb_idx = 0
    if len(notebooks) > 1:
        nb_idx = int(input(f"Notebook auswählen [0-{len(notebooks)-1}]: ") or "0")
    notebook = notebooks[nb_idx]
    print(f"    Verwende: {notebook['displayName']}")

    # Sections laden
    print(f"\n[4] Lade Sections...")
    sections = client.get_notebook_sections(site_id, notebook["id"])
    for i, sec in enumerate(sections):
        group = sec.get("_groupName", "")
        name = sec.get("displayName", "?")
        label = f"{group}/{name}" if group else name
        print(f"    [{i}] {label}")

    if not sections:
        print("    Keine Sections gefunden!")
        return

    # Section mit Unterseiten finden (oder erste verwenden)
    sec_idx = 0
    if len(sections) > 1:
        sec_idx = int(input(f"Section auswählen [0-{len(sections)-1}]: ") or "0")
    section = sections[sec_idx]
    section_id = section["id"]
    print(f"    Verwende: {section.get('displayName')}")

    # pagesUrl ermitteln
    print(f"\n[5] Hole Section-Details für pagesUrl...")
    sec_detail = client._make_request("GET", f"/sites/{site_id}/onenote/sections/{section_id}")
    pages_url = sec_detail.get("pagesUrl", "")
    print(f"    pagesUrl: {pages_url}")

    headers = client._get_headers()

    # Test 1: Standard-Request (ohne $select)
    print(f"\n{'='*60}")
    print("[Test 1] Standard-Request OHNE $select")
    print(f"{'='*60}")
    url = f"{pages_url}?$top=5"
    resp = requests.get(url, headers=headers)
    print(f"    Status: {resp.status_code}")
    if resp.ok:
        data = resp.json()
        pages = data.get("value", [])
        if pages:
            print(f"    Erste Seite - alle Keys: {sorted(pages[0].keys())}")
            print(f"    title: {pages[0].get('title')}")
            print(f"    level: {pages[0].get('level', '<<FEHLT>>')}")
            print(f"    order: {pages[0].get('order', '<<FEHLT>>')}")
            print(f"    Vollständige erste Seite:")
            print(f"    {json.dumps(pages[0], indent=4, default=str)}")
    else:
        print(f"    Fehler: {resp.text[:500]}")

    # Test 2: Mit $select=level,order
    print(f"\n{'='*60}")
    print("[Test 2] Mit $select=id,title,level,order")
    print(f"{'='*60}")
    url = f"{pages_url}?$top=5&$select=id,title,level,order"
    resp = requests.get(url, headers=headers)
    print(f"    Status: {resp.status_code}")
    if resp.ok:
        data = resp.json()
        pages = data.get("value", [])
        if pages:
            print(f"    Erste Seite - alle Keys: {sorted(pages[0].keys())}")
            for p in pages:
                print(f"    title={p.get('title')}, level={p.get('level', '<<FEHLT>>')}, order={p.get('order', '<<FEHLT>>')}")
    else:
        print(f"    Fehler: {resp.text[:500]}")

    # Test 3: Mit $orderby=order
    print(f"\n{'='*60}")
    print("[Test 3] Mit $orderby=order")
    print(f"{'='*60}")
    url = f"{pages_url}?$top=5&$orderby=order"
    resp = requests.get(url, headers=headers)
    print(f"    Status: {resp.status_code}")
    if resp.ok:
        data = resp.json()
        pages = data.get("value", [])
        if pages:
            for p in pages:
                print(f"    title={p.get('title')}, level={p.get('level', '<<FEHLT>>')}, order={p.get('order', '<<FEHLT>>')}")
    else:
        print(f"    Fehler: {resp.text[:500]}")

    # Test 4: Beta-API (v1.0 → beta), die hat oft mehr Properties
    print(f"\n{'='*60}")
    print("[Test 4] BETA API (graph.microsoft.com/beta)")
    print(f"{'='*60}")
    beta_pages_url = pages_url.replace("graph.microsoft.com/v1.0", "graph.microsoft.com/beta")
    url = f"{beta_pages_url}?$top=5"
    resp = requests.get(url, headers=headers)
    print(f"    Status: {resp.status_code}")
    if resp.ok:
        data = resp.json()
        pages = data.get("value", [])
        if pages:
            print(f"    Erste Seite - alle Keys: {sorted(pages[0].keys())}")
            print(f"    title: {pages[0].get('title')}")
            print(f"    level: {pages[0].get('level', '<<FEHLT>>')}")
            print(f"    order: {pages[0].get('order', '<<FEHLT>>')}")
    else:
        print(f"    Fehler: {resp.text[:500]}")

    # Test 5: Beta API mit $select
    print(f"\n{'='*60}")
    print("[Test 5] BETA API mit $select=id,title,level,order")
    print(f"{'='*60}")
    url = f"{beta_pages_url}?$top=5&$select=id,title,level,order"
    resp = requests.get(url, headers=headers)
    print(f"    Status: {resp.status_code}")
    if resp.ok:
        data = resp.json()
        pages = data.get("value", [])
        if pages:
            print(f"    Erste Seite - alle Keys: {sorted(pages[0].keys())}")
            for p in pages:
                print(f"    title={p.get('title')}, level={p.get('level', '<<FEHLT>>')}, order={p.get('order', '<<FEHLT>>')}")
    else:
        print(f"    Fehler: {resp.text[:500]}")

    print(f"\n{'='*60}")
    print("Diagnose abgeschlossen.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
