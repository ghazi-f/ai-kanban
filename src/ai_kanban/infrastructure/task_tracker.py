import fcntl
import json
import os
import threading
from pathlib import Path


class TaskTracker:
    """
    TaskTracker is used to track the tasks that have been processed.
    It is used to avoid processing the same task multiple times.
    """
    def __init__(self, storage_file: str = "processed_tasks.json"):
        self.storage_file = Path(storage_file)
        self.processed_tasks: set[str] = set()
        self._lock = threading.Lock()
        self.load_processed_tasks()

    def _acquire_file_lock(self, file_handle):
        """Acquire exclusive file lock (Unix/Linux/macOS)"""
        fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX)

    def _release_file_lock(self, file_handle):
        """Release file lock"""
        fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)

    def load_processed_tasks(self):
        """Load previously processed task IDs from storage with file locking"""
        with self._lock:
            if not self.storage_file.exists():
                self.processed_tasks = set()
                return

            try:
                with open(self.storage_file) as f:
                    self._acquire_file_lock(f)
                    try:
                        data = json.load(f)
                        self.processed_tasks = set(data.get("processed_tasks", []))
                    finally:
                        self._release_file_lock(f)
                print(f"Loaded {len(self.processed_tasks)} previously processed tasks")
            except Exception as e:
                print(f"Error loading processed tasks: {e}")
                self.processed_tasks = set()

    def save_processed_tasks(self):
        """Save processed task IDs to storage with file locking"""
        with self._lock:
            try:
                # Create temp file first for atomic write
                temp_file = self.storage_file.with_suffix(".tmp")
                data = {"processed_tasks": list(self.processed_tasks)}

                with open(temp_file, "w") as f:
                    self._acquire_file_lock(f)
                    try:
                        json.dump(data, f, indent=2)
                        f.flush()
                        os.fsync(f.fileno())
                    finally:
                        self._release_file_lock(f)

                # Atomic rename
                temp_file.replace(self.storage_file)

            except Exception as e:
                print(f"Error saving processed tasks: {e}")
                if temp_file.exists():
                    temp_file.unlink()

    def is_task_processed(self, task_id: str) -> bool:
        """Check if a task has already been processed (thread-safe)"""
        with self._lock:
            return task_id in self.processed_tasks

    def mark_task_processed(self, task_id: str):
        """Mark a task as processed (thread-safe)"""
        with self._lock:
            self.processed_tasks.add(task_id)
        self.save_processed_tasks()

    def get_new_tasks(self, all_tasks: list) -> list:
        """Filter out already processed tasks and return only new ones"""
        new_tasks = []
        with self._lock:
            for task in all_tasks:
                task_id = task.get("id")
                if task_id and task_id not in self.processed_tasks:
                    new_tasks.append(task)
        return new_tasks

    def clear_processed_tasks(self):
        """Clear all processed tasks (for testing or reset)"""
        with self._lock:
            self.processed_tasks.clear()
        self.save_processed_tasks()
        print("Cleared all processed tasks")
