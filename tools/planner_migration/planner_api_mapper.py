#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Planner-API-zu-Notion Mapper.

Konvertiert Planner-API-JSON-Daten direkt zu Notion-kompatiblem Format.
"""
from typing import Dict, List, Any, Optional
from datetime import datetime


class PlannerAPIMapper:
    """Mapper für Planner-API-Daten zu Notion-Format."""

    def __init__(self):
        self.buckets_cache: Dict[str, str] = {}  # bucket_id -> bucket_name
        self.users_cache: Dict[str, Dict[str, str]] = {}  # user_id -> {displayName, mail}

    def set_buckets(self, buckets: List[Dict[str, Any]]) -> None:
        """Buckets zwischenspeichern für späteres Mapping."""
        for bucket in buckets:
            self.buckets_cache[bucket["id"]] = bucket["name"]

    def set_users(self, users: List[Dict[str, Any]]) -> None:
        """Benutzer zwischenspeichern für späteres Mapping."""
        for user in users:
            self.users_cache[user["id"]] = {
                "displayName": user.get("displayName", ""),
                "mail": user.get("mail") or user.get("userPrincipalName", "")
            }

    def map_task_to_row(self, task: Dict[str, Any], task_details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Planner-Task zu CSV-ähnlichem Row-Format konvertieren.
        
        Kompatibel mit dem bestehenden notion_mapper.py.
        """
        row: Dict[str, Any] = {}

        # ===== Basis-Felder =====
        row["id"] = task.get("id", "")
        row["Name"] = task.get("title", "Unbenannte Aufgabe")
        
        # ===== Bucket (Kategorie) =====
        bucket_id = task.get("bucketId")
        if bucket_id and bucket_id in self.buckets_cache:
            row["Bucket"] = self.buckets_cache[bucket_id]
        else:
            row["Bucket"] = "Kein Bucket"

        # ===== Fortschritt =====
        percent_complete = task.get("percentComplete", 0)
        row["% Abgeschlossen"] = percent_complete
        
        # Status ableiten
        if percent_complete == 100:
            row["Status"] = "Abgeschlossen"
        elif percent_complete > 0:
            row["Status"] = "In Bearbeitung"
        else:
            row["Status"] = "Nicht begonnen"

        # ===== Priorität =====
        priority = task.get("priority")
        priority_map = {
            0: "Dringend",
            1: "Dringend",
            2: "Dringend",
            3: "Wichtig",
            4: "Wichtig",
            5: "Mittel",
            6: "Niedrig",
            7: "Niedrig",
            8: "Niedrig",
            9: "Niedrig",
            10: "Niedrig"
        }
        row["Priorität"] = priority_map.get(priority, "Mittel")

        # ===== Zuweisungen =====
        assignments = task.get("assignments", {})
        assigned_users = []
        for user_id in assignments.keys():
            if user_id in self.users_cache:
                user_info = self.users_cache[user_id]
                assigned_users.append(user_info["displayName"])
        
        row["Zugewiesen an"] = ", ".join(assigned_users) if assigned_users else ""

        # ===== Datumsfelder =====
        # Startdatum
        start_date = task.get("startDateTime")
        if start_date:
            try:
                row["Startdatum"] = self._parse_iso_date(start_date)
            except:
                row["Startdatum"] = None
        else:
            row["Startdatum"] = None

        # Fälligkeitsdatum
        due_date = task.get("dueDateTime")
        if due_date:
            try:
                row["Fälligkeitsdatum"] = self._parse_iso_date(due_date)
            except:
                row["Fälligkeitsdatum"] = None
        else:
            row["Fälligkeitsdatum"] = None

        # Abschlussdatum
        completed_date = task.get("completedDateTime")
        if completed_date:
            try:
                row["Abgeschlossen am"] = self._parse_iso_date(completed_date)
            except:
                row["Abgeschlossen am"] = None
        else:
            row["Abgeschlossen am"] = None

        # Erstellungsdatum
        created_date = task.get("createdDateTime")
        if created_date:
            try:
                row["Erstellt am"] = self._parse_iso_date(created_date)
            except:
                row["Erstellt am"] = None
        else:
            row["Erstellt am"] = None

        # ===== Beschreibung & Checklisten (aus task_details) =====
        if task_details:
            # Beschreibung
            description = task_details.get("description", "")
            if description:
                row["Beschreibung"] = description
            
            # Checklisten
            checklist = task_details.get("checklist", {})
            if checklist:
                checklist_items = []
                for item_id, item in checklist.items():
                    title = item.get("title", "")
                    is_checked = item.get("isChecked", False)
                    status = "✅" if is_checked else "☐"
                    checklist_items.append(f"{status} {title}")
                
                if checklist_items:
                    row["Checkliste"] = "\n".join(checklist_items)

            # Referenzen/Anhänge
            references = task_details.get("references", {})
            if references:
                ref_items = []
                for ref_id, ref in references.items():
                    alias = ref.get("alias", "")
                    url = ref.get("url", "")
                    if alias and url:
                        ref_items.append(f"[{alias}]({url})")
                    elif url:
                        ref_items.append(url)
                
                if ref_items:
                    row["Referenzen"] = "\n".join(ref_items)

        # ===== Planner-spezifische IDs (für Tracking) =====
        row["Vorgangsnummer (Planner)"] = task.get("id", "")
        row["Plan ID"] = task.get("planId", "")

        return row

    def _parse_iso_date(self, iso_string: str) -> str:
        """ISO-8601-Datum zu deutschem Format konvertieren."""
        # Planner verwendet ISO-8601 Format: 2024-01-15T00:00:00Z
        try:
            dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
            return dt.strftime("%d.%m.%Y")
        except:
            # Fallback: Original-String zurückgeben
            return iso_string.split("T")[0] if "T" in iso_string else iso_string

    def map_tasks_to_rows(
        self,
        tasks: List[Dict[str, Any]],
        tasks_details: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Mehrere Tasks konvertieren.
        
        Args:
            tasks: Liste von Planner-Tasks
            tasks_details: Optional - Dict[task_id -> task_details]
        
        Returns:
            Liste von Row-Dicts (kompatibel mit notion_mapper)
        """
        rows = []
        
        for task in tasks:
            task_id = task.get("id")
            details = None
            
            if tasks_details and task_id in tasks_details:
                details = tasks_details[task_id]
            
            row = self.map_task_to_row(task, details)
            rows.append(row)
        
        return rows


def create_planner_api_mapper() -> PlannerAPIMapper:
    """Factory-Funktion für PlannerAPIMapper."""
    return PlannerAPIMapper()
