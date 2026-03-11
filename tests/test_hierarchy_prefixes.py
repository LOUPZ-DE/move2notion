#!/usr/bin/env python3
"""
Test für compute_hierarchy_prefixes — Hierarchische Nummerierung von OneNote-Seiten.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.onenote_migration.cli import compute_hierarchy_prefixes


def test_basic_hierarchy():
    """Test: Einfache 3-Level-Hierarchie (wie Skaylink-Beispiel)."""
    pages = [
        {"id": "p1", "title": "2025-03-24 Abstimmung LOUPZ x Skaylink", "level": 0, "order": 100},
        {"id": "p2", "title": "2025-03-17 ProAktivTag", "level": 0, "order": 200},
        {"id": "p3", "title": "Obere Ebene", "level": 0, "order": 300},
        {"id": "p4", "title": "Untere Ebene", "level": 1, "order": 400},
        {"id": "p5", "title": "Untere untere Ebene", "level": 2, "order": 500},
        {"id": "p6", "title": "2025-03-31 Einführung Apple Handys", "level": 0, "order": 600},
    ]

    result = compute_hierarchy_prefixes(pages)

    print(f"\n=== Ergebnis ===")
    for p in pages:
        prefix = result.get(p["id"], "(kein Prefix)")
        print(f"  Level {p['level']}: [{prefix}] {p['title']}")

    # Level-0 ohne Kinder → kein Prefix
    assert "p1" not in result, f"p1 sollte KEIN Prefix haben, hat aber: '{result.get('p1')}'"
    assert "p2" not in result, f"p2 sollte KEIN Prefix haben, hat aber: '{result.get('p2')}'"
    assert "p6" not in result, f"p6 sollte KEIN Prefix haben, hat aber: '{result.get('p6')}'"

    # Level-0 mit Kindern → Prefix "1  "
    assert "p3" in result, "p3 (Obere Ebene) sollte Prefix haben"
    assert result["p3"].strip() == "1.", f"p3 Prefix sollte '1.' sein, ist aber '{result['p3'].strip()}'"

    # Level-1 → Prefix "1.1.  "
    assert "p4" in result, "p4 (Untere Ebene) sollte Prefix haben"
    assert result["p4"].strip() == "1.1.", f"p4 Prefix sollte '1.1.' sein, ist aber '{result['p4'].strip()}'"

    # Level-2 → Prefix "1.1.1.  "
    assert "p5" in result, "p5 (Untere untere Ebene) sollte Prefix haben"
    assert result["p5"].strip() == "1.1.1.", f"p5 Prefix sollte '1.1.1.' sein, ist aber '{result['p5'].strip()}'"

    print("\n✅ test_basic_hierarchy BESTANDEN")


def test_no_hierarchy():
    """Test: Alle Seiten auf Level 0 → keine Prefixe."""
    pages = [
        {"id": "p1", "title": "Seite A", "level": 0},
        {"id": "p2", "title": "Seite B", "level": 0},
        {"id": "p3", "title": "Seite C", "level": 0},
    ]

    result = compute_hierarchy_prefixes(pages)
    assert result == {}, f"Sollte leer sein, ist aber: {result}"
    print("\n✅ test_no_hierarchy BESTANDEN")


def test_missing_level_property():
    """Test: Level-Property fehlt komplett → Default 0, keine Prefixe."""
    pages = [
        {"id": "p1", "title": "Seite A"},
        {"id": "p2", "title": "Seite B"},
        {"id": "p3", "title": "Seite C"},
    ]

    result = compute_hierarchy_prefixes(pages)
    assert result == {}, f"Sollte leer sein wenn level fehlt, ist aber: {result}"
    print("\n✅ test_missing_level_property BESTANDEN")


def test_multiple_groups():
    """Test: Mehrere Level-0 mit Kindern."""
    pages = [
        {"id": "p1", "title": "Gruppe A", "level": 0},
        {"id": "p2", "title": "Kind A1", "level": 1},
        {"id": "p3", "title": "Kind A2", "level": 1},
        {"id": "p4", "title": "Einzeln", "level": 0},  # ohne Kinder
        {"id": "p5", "title": "Gruppe B", "level": 0},
        {"id": "p6", "title": "Kind B1", "level": 1},
        {"id": "p7", "title": "Enkel B1a", "level": 2},
    ]

    result = compute_hierarchy_prefixes(pages)

    print(f"\n=== Ergebnis ===")
    for p in pages:
        prefix = result.get(p["id"], "(kein Prefix)")
        print(f"  Level {p['level']}: [{prefix}] {p['title']}")

    assert result["p1"].strip() == "1."
    assert result["p2"].strip() == "1.1."
    assert result["p3"].strip() == "1.2."
    assert "p4" not in result  # Einzeln, kein Prefix
    assert result["p5"].strip() == "2."
    assert result["p6"].strip() == "2.1."
    assert result["p7"].strip() == "2.1.1."

    print("\n✅ test_multiple_groups BESTANDEN")


def test_zero_padding():
    """Test: Zero-Padding bei >9 Einträgen."""
    pages = []
    # 1 Level-0 mit 12 Level-1 Kindern
    pages.append({"id": "parent", "title": "Eltern", "level": 0})
    for i in range(1, 13):
        pages.append({"id": f"child_{i}", "title": f"Kind {i}", "level": 1})

    result = compute_hierarchy_prefixes(pages)

    print(f"\n=== Zero-Padding Ergebnis ===")
    for p in pages:
        prefix = result.get(p["id"], "(kein Prefix)")
        print(f"  [{prefix}] {p['title']}")

    # Bei 12 Kindern → 2-stellig: 01, 02, ..., 12
    assert "01." in result["child_1"], f"Erwartet '01.' in '{result['child_1']}'"
    assert "12." in result["child_12"], f"Erwartet '12.' in '{result['child_12']}'"

    print("\n✅ test_zero_padding BESTANDEN")


if __name__ == "__main__":
    print("=" * 60)
    print("Tests für compute_hierarchy_prefixes")
    print("=" * 60)

    test_basic_hierarchy()
    test_no_hierarchy()
    test_missing_level_property()
    test_multiple_groups()
    test_zero_padding()

    print("\n" + "=" * 60)
    print("✅ ALLE TESTS BESTANDEN")
    print("=" * 60)
