import json
import threading
import time
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

import pytest

from ai_kanban.task_tracker import TaskTracker


class TestTaskTracker:

    def test_init_new_file(self, temp_dir):
        """Test initialization with new storage file"""
        storage_file = temp_dir / "test_tasks.json"

        tracker = TaskTracker(storage_file=str(storage_file))

        assert tracker.storage_file == storage_file
        assert tracker.processed_tasks == set()
        assert isinstance(tracker._lock, type(threading.Lock()))

    def test_init_existing_file(self, temp_dir):
        """Test initialization with existing storage file"""
        storage_file = temp_dir / "test_tasks.json"
        test_data = {"processed_tasks": ["task1", "task2"]}

        with open(storage_file, "w") as f:
            json.dump(test_data, f)

        tracker = TaskTracker(storage_file=str(storage_file))

        assert tracker.processed_tasks == {"task1", "task2"}

    def test_init_corrupted_file(self, temp_dir):
        """Test initialization with corrupted storage file"""
        storage_file = temp_dir / "test_tasks.json"

        with open(storage_file, "w") as f:
            f.write("invalid json")

        tracker = TaskTracker(storage_file=str(storage_file))

        assert tracker.processed_tasks == set()

    @patch("fcntl.flock")
    def test_save_processed_tasks(self, mock_flock, temp_dir):
        """Test saving processed tasks"""
        storage_file = temp_dir / "test_tasks.json"

        tracker = TaskTracker(storage_file=str(storage_file))
        tracker.processed_tasks = {"task1", "task2"}

        tracker.save_processed_tasks()

        # Check file was created
        assert storage_file.exists()

        # Check content
        with open(storage_file) as f:
            data = json.load(f)

        assert set(data["processed_tasks"]) == {"task1", "task2"}

    @patch("fcntl.flock")
    def test_save_processed_tasks_error(self, mock_flock, temp_dir):
        """Test error handling in save_processed_tasks"""
        storage_file = temp_dir / "readonly" / "test_tasks.json"

        tracker = TaskTracker(storage_file=str(storage_file))
        tracker.processed_tasks = {"task1"}

        # Should not raise exception, just handle gracefully
        tracker.save_processed_tasks()

    def test_is_task_processed(self, temp_dir):
        """Test checking if task is processed"""
        storage_file = temp_dir / "test_tasks.json"

        tracker = TaskTracker(storage_file=str(storage_file))
        tracker.processed_tasks = {"task1", "task2"}

        assert tracker.is_task_processed("task1") is True
        assert tracker.is_task_processed("task3") is False

    @patch("fcntl.flock")
    def test_mark_task_processed(self, mock_flock, temp_dir):
        """Test marking task as processed"""
        storage_file = temp_dir / "test_tasks.json"

        tracker = TaskTracker(storage_file=str(storage_file))

        tracker.mark_task_processed("task1")

        assert "task1" in tracker.processed_tasks
        assert storage_file.exists()

    def test_get_new_tasks(self, temp_dir):
        """Test filtering new tasks"""
        storage_file = temp_dir / "test_tasks.json"

        tracker = TaskTracker(storage_file=str(storage_file))
        tracker.processed_tasks = {"task1", "task2"}

        all_tasks = [
            {"id": "task1", "name": "Task 1"},
            {"id": "task2", "name": "Task 2"},
            {"id": "task3", "name": "Task 3"},
            {"id": "task4", "name": "Task 4"},
        ]

        new_tasks = tracker.get_new_tasks(all_tasks)

        assert len(new_tasks) == 2
        assert new_tasks[0]["id"] == "task3"
        assert new_tasks[1]["id"] == "task4"

    def test_get_new_tasks_empty(self, temp_dir):
        """Test getting new tasks when all are processed"""
        storage_file = temp_dir / "test_tasks.json"

        tracker = TaskTracker(storage_file=str(storage_file))
        tracker.processed_tasks = {"task1", "task2"}

        all_tasks = [
            {"id": "task1", "name": "Task 1"},
            {"id": "task2", "name": "Task 2"},
        ]

        new_tasks = tracker.get_new_tasks(all_tasks)

        assert len(new_tasks) == 0

    def test_get_new_tasks_no_id(self, temp_dir):
        """Test getting new tasks with missing IDs"""
        storage_file = temp_dir / "test_tasks.json"

        tracker = TaskTracker(storage_file=str(storage_file))

        all_tasks = [{"name": "Task without ID"}, {"id": "task1", "name": "Task 1"}]

        new_tasks = tracker.get_new_tasks(all_tasks)

        assert len(new_tasks) == 1
        assert new_tasks[0]["id"] == "task1"

    @patch("fcntl.flock")
    def test_clear_processed_tasks(self, mock_flock, temp_dir):
        """Test clearing processed tasks"""
        storage_file = temp_dir / "test_tasks.json"

        tracker = TaskTracker(storage_file=str(storage_file))
        tracker.processed_tasks = {"task1", "task2"}

        tracker.clear_processed_tasks()

        assert tracker.processed_tasks == set()
        assert storage_file.exists()

    def test_thread_safety(self, temp_dir):
        """Test thread safety of operations"""
        storage_file = temp_dir / "test_tasks.json"
        tracker = TaskTracker(storage_file=str(storage_file))

        def add_tasks(start_id, count):
            for i in range(count):
                task_id = f"task{start_id + i}"
                tracker.mark_task_processed(task_id)

        # Create multiple threads that add tasks concurrently
        threads = []
        for i in range(3):
            thread = threading.Thread(target=add_tasks, args=(i * 10, 10))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Should have 30 tasks total
        assert len(tracker.processed_tasks) == 30

        # Verify all tasks are present
        expected_tasks = {f"task{i}" for i in range(30)}
        assert tracker.processed_tasks == expected_tasks
