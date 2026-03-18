"""
Task-Manager fuer Background-Migrationen mit SSE-Progress-Streaming.
"""
import uuid
import queue
import threading
import json
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class MigrationTask:
    """Zustand einer laufenden Migration."""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_type: str = ""
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0
    phase: str = ""
    message: str = ""
    total_items: int = 0
    success_count: int = 0
    error_count: int = 0
    errors: List[Dict[str, str]] = field(default_factory=list)
    event_queue: queue.Queue = field(default_factory=queue.Queue)
    thread: Optional[threading.Thread] = None
    cancelled: threading.Event = field(default_factory=threading.Event)


class TaskManager:
    """Verwaltet aktive Background-Tasks."""

    def __init__(self):
        self._tasks: Dict[str, MigrationTask] = {}
        self._lock = threading.Lock()

    def create_task(self, task_type: str) -> MigrationTask:
        task = MigrationTask(task_type=task_type)
        with self._lock:
            self._tasks[task.task_id] = task
        return task

    def get_task(self, task_id: str) -> Optional[MigrationTask]:
        return self._tasks.get(task_id)

    def get_active_count(self) -> Dict[str, int]:
        """Anzahl laufender Migrationen nach Typ."""
        with self._lock:
            running = [t for t in self._tasks.values() if t.status == TaskStatus.RUNNING]
        return {
            "total": len(running),
            "onenote": sum(1 for t in running if t.task_type == "onenote"),
            "planner": sum(1 for t in running if t.task_type == "planner"),
        }

    def cancel_task(self, task_id: str) -> bool:
        """Task zum Abbrechen markieren. Gibt True zurueck wenn Task gefunden."""
        task = self._tasks.get(task_id)
        if task and task.status == TaskStatus.RUNNING:
            task.cancelled.set()
            return True
        return False


# Modul-Singleton
task_manager = TaskManager()


def emit_progress(
    task: MigrationTask,
    progress: int,
    message: str,
    log_type: str = "info",
    phase: Optional[str] = None
):
    """Progress-Event in die Task-Queue schreiben."""
    if phase:
        task.phase = phase
    task.progress = progress
    task.message = message
    event = {
        "type": "progress",
        "progress": progress,
        "message": message,
        "log_type": log_type,
        "phase": phase or task.phase,
        "success_count": task.success_count,
        "error_count": task.error_count,
        "total_items": task.total_items,
    }
    task.event_queue.put(event)


def emit_cancelled(task: MigrationTask):
    """Abbruch-Event in die Task-Queue schreiben."""
    task.status = TaskStatus.CANCELLED
    event = {
        "type": "complete",
        "status": "cancelled",
        "success_count": task.success_count,
        "error_count": task.error_count,
        "total_items": task.total_items,
        "errors": task.errors[:20],
    }
    task.event_queue.put(event)


def emit_complete(task: MigrationTask, success: bool = True):
    """Abschluss-Event in die Task-Queue schreiben."""
    task.status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
    task.progress = 100 if success else task.progress
    event = {
        "type": "complete",
        "status": task.status.value,
        "success_count": task.success_count,
        "error_count": task.error_count,
        "total_items": task.total_items,
        "errors": task.errors[:20],
    }
    task.event_queue.put(event)
