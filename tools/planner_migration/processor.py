#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSV-Prozessor für Planner-Daten.

Dieses Modul behandelt:
- CSV-Datei einlesen mit automatischer Delimiter-Erkennung
- Daten transformieren (Datumsformate, Mehrfachwerte, etc.)
- Datenvalidierung und -bereinigung
"""
import re
from pathlib import Path
from typing import Dict, List, Optional, Any
import pandas as pd

# Core-Module importieren
from core.utils import sniff_csv_delimiter, read_csv_file, convert_to_iso_date, split_multi_values


class PlannerCSVProcessor:
    """Verarbeitet Planner-CSV-Dateien."""

    # Standard-Spalten-Mapping
    COLUMN_MAPPING = {
        "Aufgabenname": "Name",
        "Aufgabenname ": "Name",
        "Bucket-Name": "Bucket",
        "Status": "Status",
        "Priorität": "Priorität",
        "Beschreibung": "Beschreibung",
        "Zugewiesen an": "Zugewiesen an",
        "Zugewiesen an ": "Zugewiesen an",
        "Erstellt von": "Erstellt von",
        "Abgeschlossen von": "Abgeschlossen von",
        "Erstellungsdatum": "Erstellungsdatum",
        "Startdatum": "Startdatum",
        "Fälligkeitsdatum": "Fälligkeitsdatum",
        "Abgeschlossen am": "Abgeschlossen am",
        "Ist wiederkehrend": "Ist wiederkehrend",
        "Verspätet": "Verspätet",
        "Bezeichnungen": "Tags",
        "Checklistenpunkte": "Checkliste_raw",
        "Abgeschlossene Checklistenpunkte": "Checkliste_done",
        " Abgeschlossene Checklistenpunkte": "Checkliste_done",
        "Vorgangsnummer": "Vorgangsnummer (Planner)",
        "Vorgangsnummer ": "Vorgangsnummer (Planner)",
    }

    # Datumsspalten
    DATE_COLUMNS = [
        "Erstellungsdatum", "Startdatum", "Fälligkeitsdatum", "Abgeschlossen am"
    ]

    # Boolean-Spalten
    BOOLEAN_COLUMNS = ["Ist wiederkehrend", "Verspätet"]

    # Multi-Value-Spalten (Semikolon-getrennt)
    MULTI_VALUE_COLUMNS = [
        "Zugewiesen an", "Erstellt von", "Abgeschlossen von", "Tags"
    ]

    def __init__(self, csv_path: str, delimiter: Optional[str] = None):
        self.csv_path = Path(csv_path)
        self.delimiter = delimiter or self._detect_delimiter()
        self.raw_data: List[Dict[str, str]] = []
        self.processed_data: List[Dict[str, any]] = []

    def _detect_delimiter(self) -> str:
        """CSV-Delimiter automatisch erkennen."""
        return sniff_csv_delimiter(self.csv_path)

    def load_csv(self) -> None:
        """CSV-Datei laden und Rohdaten speichern."""
        self.raw_data = read_csv_file(self.csv_path, self.delimiter)

        if not self.raw_data:
            raise ValueError("CSV-Datei ist leer oder konnte nicht gelesen werden")

    def _find_column(self, target_name: str) -> Optional[str]:
        """Spalte anhand von Namen finden (case-insensitive)."""
        target_lower = target_name.lower()

        for col_name in self.raw_data[0].keys():
            if col_name.lower() == target_lower:
                return col_name

        return None

    def _get_column_value(self, row: Dict[str, str], column_name: str) -> str:
        """Wert für eine Spalte aus einer Zeile extrahieren."""
        # Direkte Spalte versuchen
        if column_name in row:
            return row[column_name]

        # Mapping versuchen
        mapped_column = self.COLUMN_MAPPING.get(column_name)
        if mapped_column and mapped_column in row:
            return row[mapped_column]

        # Case-insensitive Suche
        actual_column = self._find_column(column_name)
        if actual_column:
            return row[actual_column]

        return ""

    def process_row(self, row: Dict[str, str]) -> Dict[str, any]:
        """Eine CSV-Zeile verarbeiten."""
        processed = {}

        # Name (erforderlich)
        name_col = self._find_column("Aufgabenname") or "Aufgabenname"
        name_value = self._get_column_value(row, name_col)
        if not name_value:
            raise ValueError("Spalte 'Aufgabenname' nicht gefunden oder leer")
        processed["Name"] = name_value

        # Einfache Text-Spalten
        for col in ["Bucket", "Status", "Priorität", "Beschreibung"]:
            value = self._get_column_value(row, col)
            if value:
                processed[col] = value

        # Personen-Spalten (Text-Version für Mapping)
        for col in ["Zugewiesen an", "Erstellt von", "Abgeschlossen von"]:
            value = self._get_column_value(row, col)
            if value:
                # Mehrfachwerte für Personen-Mapping aufbereiten
                multi_values = split_multi_values(value, ";")
                processed[f"{col} (Text)"] = ", ".join(multi_values)

        # Datums-Spalten
        for col in self.DATE_COLUMNS:
            value = self._get_column_value(row, col)
            if value:
                iso_date = convert_to_iso_date(value)
                if iso_date:
                    processed[col] = iso_date

        # Boolean-Spalten
        for col in self.BOOLEAN_COLUMNS:
            value = self._get_column_value(row, col)
            if value:
                processed[col] = value

        # Tags (aus Bezeichnungen)
        tags_value = self._get_column_value(row, "Bezeichnungen")
        if tags_value:
            multi_values = split_multi_values(tags_value, ";")
            processed["Tags"] = ", ".join(multi_values)

        # Checklisten-Daten
        checklist_col = self._find_column("Checklistenpunkte")
        if checklist_col:
            checklist_value = self._get_column_value(row, checklist_col)
            if checklist_value:
                processed["Checkliste_raw"] = checklist_value

        done_col = self._find_column("Abgeschlossene Checklistenpunkte")
        if done_col:
            done_value = self._get_column_value(row, done_col)
            if done_value:
                processed["Checkliste_done"] = done_value

        # Vorgangsnummer
        vnr_col = self._find_column("Vorgangsnummer")
        if vnr_col:
            vnr_value = self._get_column_value(row, vnr_col)
            if vnr_value:
                processed["Vorgangsnummer (Planner)"] = vnr_value

        return processed

    def process_all_rows(self) -> List[Dict[str, any]]:
        """Alle CSV-Zeilen verarbeiten."""
        if not self.raw_data:
            self.load_csv()

        self.processed_data = []

        for i, row in enumerate(self.raw_data):
            try:
                processed_row = self.process_row(row)
                self.processed_data.append(processed_row)
            except Exception as e:
                print(f"[Warning] Zeile {i+1} übersprungen: {e}")
                continue

        return self.processed_data

    def save_clean_csv(self, output_path: Optional[Path] = None) -> Path:
        """Verarbeitete Daten als bereinigte CSV speichern."""
        if not self.processed_data:
            self.process_all_rows()

        if output_path is None:
            output_path = self.csv_path.with_name(self.csv_path.stem + "_clean.csv")

        # DataFrame erstellen und speichern
        df = pd.DataFrame(self.processed_data)
        df.to_csv(output_path, index=False, encoding="utf-8")

        return output_path

    def get_column_names(self) -> List[str]:
        """Spaltennamen der CSV-Datei abrufen."""
        if self.raw_data:
            return list(self.raw_data[0].keys())
        return []

    def get_processed_columns(self) -> List[str]:
        """Verarbeitete Spaltennamen abrufen."""
        if self.processed_data:
            return list(self.processed_data[0].keys())
        return []

    def validate_data(self) -> List[str]:
        """Daten validieren und Warnungen zurückgeben."""
        warnings = []

        if not self.processed_data:
            self.process_all_rows()

        # Prüfen ob Name-Spalte vorhanden ist
        if not any("Name" in row for row in self.processed_data):
            warnings.append("Keine 'Name' Spalte gefunden")

        # Prüfen auf leere Zeilen
        empty_rows = sum(1 for row in self.processed_data if not row.get("Name", "").strip())
        if empty_rows > 0:
            warnings.append(f"{empty_rows} leere Zeilen gefunden")

        return warnings


def create_planner_processor(csv_path: str, delimiter: Optional[str] = None) -> PlannerCSVProcessor:
    """Factory-Funktion für PlannerCSVProcessor."""
    return PlannerCSVProcessor(csv_path, delimiter)
