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
        self.category_descriptions: Dict[str, str] = {}  # category_id -> description

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

    def set_category_descriptions(self, category_descriptions: Dict[str, str]) -> None:
        """Category-Descriptions (Tags) zwischenspeichern für späteres Mapping."""
        self.category_descriptions = category_descriptions or {}

    def map_task_to_row(self, task: Dict[str, Any], task_details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Planner-Task zu CSV-ähnlichem Row-Format konvertieren.
        
        Kompatibel mit dem bestehenden notion_mapper.py.
        """
        row: Dict[str, Any] = {}

        # ===== Basis-Felder =====
        row["Name"] = task.get("title", "Unbenannte Aufgabe")
        
        # ===== Bucket (Kategorie) =====
        bucket_id = task.get("bucketId")
        bucket_name = None
        if bucket_id and bucket_id in self.buckets_cache:
            bucket_name = self.buckets_cache[bucket_id]
        else:
            bucket_name = "Kein Bucket"

        if isinstance(bucket_name, str):
            bucket_name = bucket_name.strip()
            if bucket_name.lower().startswith("leistungsphase "):
                suffix = bucket_name.replace("Leistungsphase ", "", 1).strip()
                if suffix.isdigit() and len(suffix) == 2:
                    bucket_name = f"LPH {int(suffix)}"
            elif bucket_name.lower().startswith("lp ") and not bucket_name.lower().startswith("lph "):
                bucket_name = "LPH " + bucket_name[3:]

        row["LPH/Aufgabentyp"] = bucket_name

        # ===== Fortschritt (Status) =====
        percent_complete = task.get("percentComplete", 0)

        # Status ableiten
        if percent_complete == 100:
            row["Status"] = "erledigt"
        elif percent_complete > 0:
            row["Status"] = "in Arbeit"
        else:
            row["Status"] = "Aufgabenpool"

        # ===== Priorität =====
        priority = task.get("priority")
        priority_map = {
            0: "Dringend",
            1: "Dringend",
            2: "Dringend",
            3: "Hoch",
            4: "Hoch",
            5: "Mittel",
            6: "Niedrig",
            7: "Niedrig",
            8: "Niedrig",
            9: "Niedrig",
            10: "Niedrig"
        }
        priority_key = priority if priority is not None else 5
        row["Priorität"] = priority_map.get(priority_key, "Mittel")

        # ===== Zuweisungen =====
        assignments = task.get("assignments", {})
        assigned_emails = []
        
        for user_id in assignments.keys():
            if user_id in self.users_cache:
                user_info = self.users_cache[user_id]
                email = user_info.get("mail")
                # Nur gültige E-Mails hinzufügen
                if email:
                    assigned_emails.append(email)
        
        # Für direktes Notion People-Mapping via E-Mail
        if assigned_emails:
            row["verantwortlich (Emails)"] = assigned_emails

        # ===== Fachdisziplin (aus appliedCategories) =====
        applied_categories = task.get("appliedCategories", {})
        tags = []
        for category_id in applied_categories.keys():
            if category_id in self.category_descriptions:
                tag_name = self.category_descriptions[category_id]
                if tag_name:  # Nur nicht-leere Tags
                    tags.append(tag_name)
        
        if tags:
            row["Fachdisziplin"] = ", ".join(tags)

        # ===== Datumsfelder =====
        # Fälligkeitsdatum
        due_date = task.get("dueDateTime")
        if due_date:
            try:
                row["Fälligkeitsdatum"] = self._parse_iso_date(due_date)
            except:
                row["Fälligkeitsdatum"] = None
        else:
            row["Fälligkeitsdatum"] = None

        # ===== Beschreibung & Checklisten (aus task_details) =====
        if task_details:
            # Beschreibung (nur als Inhalt, nicht als Property)
            description = task_details.get("description", "")
            if description:
                row["Beschreibung"] = description
            
            # Checklisten - als strukturierte Liste für To-Do-Blöcke
            checklist = task_details.get("checklist", {})
            if checklist:
                checklist_items = []
                for item_id, item in checklist.items():
                    title = item.get("title", "")
                    is_checked = item.get("isChecked", False)
                    checklist_items.append({
                        "title": title,
                        "checked": is_checked
                    })
                
                if checklist_items:
                    # Sortiere nach orderHint falls vorhanden
                    row["Checkliste_structured"] = checklist_items
                    # Behalte auch Text-Version für Kompatibilität
                    text_items = [f"{'✅' if item['checked'] else '☐'} {item['title']}" for item in checklist_items]
                    row["Checkliste"] = "\n".join(text_items)

            # Referenzen/Anhänge
            references = task_details.get("references", {})
            if references:
                ref_items = []
                for ref_id, ref in references.items():
                    alias = ref.get("alias", "")
                    url = ref.get("url", "")
                    if alias and url:
                        ref_items.append({"title": alias, "url": url})
                    elif url:
                        ref_items.append({"title": url, "url": url})
                
                if ref_items:
                    row["Referenzen"] = ref_items

        # ===== Planner-spezifische IDs (für Tracking) =====
        row["Plan ID"] = task.get("planId", "")

        return row

    def _parse_iso_date(self, iso_string: str) -> str:
        """ISO-8601-Datum zu Notion-kompatiblem Format (YYYY-MM-DD) konvertieren."""
        # Planner verwendet ISO-8601 Format: 2024-01-15T00:00:00Z
        # Notion erwartet: YYYY-MM-DD
        try:
            dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
        except:
            # Fallback: Nur Datumsteil extrahieren (ohne Zeit)
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
