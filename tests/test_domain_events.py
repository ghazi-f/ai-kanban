"""Tests for domain events."""

import pytest
from datetime import datetime
from uuid import uuid4

from ai_kanban.domain.events import (
    NotionTask, TaskStatus, TaskProcessedEvent, TaskProcessingFailedEvent
)


class TestNotionTask:
    """Test cases for NotionTask domain event."""
    
    def test_notion_task_creation(self):
        """Test creating a valid NotionTask."""
        task = NotionTask(
            notion_id="test-123",
            title="Test Task",
            status=TaskStatus.TO_DO,
            description="Test description",
            ai_employee="TestEmployee",
            created_by="user123"
        )
        
        assert task.notion_id == "test-123"
        assert task.title == "Test Task"
        assert task.status == TaskStatus.TO_DO
        assert task.ai_employee == "TestEmployee"
        assert task.event_id is not None
        assert task.timestamp is not None
    
    def test_notion_task_validation(self):
        """Test NotionTask validation rules."""
        # Empty notion_id should raise error
        with pytest.raises(ValueError, match="must have notion_id"):
            NotionTask(
                notion_id="",
                title="Test",
                status=TaskStatus.TO_DO,
                created_by="user123"
            )
        
        # Empty title should raise error
        with pytest.raises(ValueError, match="must have non-empty title"):
            NotionTask(
                notion_id="test-123",
                title="   ",  # whitespace only
                status=TaskStatus.TO_DO,
                created_by="user123"
            )
    
    def test_has_ai_employee_assigned(self):
        """Test AI employee assignment check."""
        # With AI employee
        task_with_employee = NotionTask(
            notion_id="test-123",
            title="Test Task",
            status=TaskStatus.TO_DO,
            ai_employee="TestEmployee",
            created_by="user123"
        )
        assert task_with_employee.has_ai_employee_assigned()
        
        # Without AI employee
        task_without_employee = NotionTask(
            notion_id="test-123",
            title="Test Task",
            status=TaskStatus.TO_DO,
            ai_employee=None,
            created_by="user123"
        )
        assert not task_without_employee.has_ai_employee_assigned()
        
        # With empty string
        task_empty_employee = NotionTask(
            notion_id="test-123",
            title="Test Task",
            status=TaskStatus.TO_DO,
            ai_employee="   ",
            created_by="user123"
        )
        assert not task_empty_employee.has_ai_employee_assigned()
    
    def test_is_assigned_to_employee(self):
        """Test employee assignment check."""
        task = NotionTask(
            notion_id="test-123",
            title="Test Task",
            status=TaskStatus.TO_DO,
            ai_employee="TestEmployee",
            created_by="user123"
        )
        
        assert task.is_assigned_to_employee("TestEmployee")
        assert task.is_assigned_to_employee("testemployee")  # case insensitive
        assert not task.is_assigned_to_employee("OtherEmployee")
    
    def test_can_be_processed(self):
        """Test task processability rules."""
        # TO_DO with AI employee - can be processed
        todo_task = NotionTask(
            notion_id="test-123",
            title="Test Task",
            status=TaskStatus.TO_DO,
            ai_employee="TestEmployee",
            created_by="user123"
        )
        assert todo_task.can_be_processed()
        
        # IN_PROGRESS with AI employee - can be processed
        in_progress_task = NotionTask(
            notion_id="test-123",
            title="Test Task",
            status=TaskStatus.IN_PROGRESS,
            ai_employee="TestEmployee",
            created_by="user123"
        )
        assert in_progress_task.can_be_processed()
        
        # DONE with AI employee - cannot be processed
        done_task = NotionTask(
            notion_id="test-123",
            title="Test Task",
            status=TaskStatus.DONE,
            ai_employee="TestEmployee",
            created_by="user123"
        )
        assert not done_task.can_be_processed()
        
        # TO_DO without AI employee - cannot be processed
        no_employee_task = NotionTask(
            notion_id="test-123",
            title="Test Task",
            status=TaskStatus.TO_DO,
            ai_employee=None,
            created_by="user123"
        )
        assert not no_employee_task.can_be_processed()
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        task = NotionTask(
            notion_id="test-123",
            title="Test Task",
            status=TaskStatus.TO_DO,
            description="Test description",
            ai_employee="TestEmployee",
            created_by="user123"
        )
        
        task_dict = task.to_dict()
        
        assert task_dict["notion_id"] == "test-123"
        assert task_dict["title"] == "Test Task"
        assert task_dict["status"] == "To Do"
        assert task_dict["ai_employee"] == "TestEmployee"
        assert "event_id" in task_dict
        assert "timestamp" in task_dict
    
    def test_with_content(self):
        """Test creating task with updated content."""
        original_task = NotionTask(
            notion_id="test-123",
            title="Test Task",
            status=TaskStatus.TO_DO,
            content="",
            ai_employee="TestEmployee",
            created_by="user123"
        )
        
        updated_task = original_task.with_content("New content here")
        
        assert updated_task.content == "New content here"
        assert updated_task.notion_id == original_task.notion_id
        assert updated_task.title == original_task.title
        assert updated_task != original_task  # Different objects


class TestDomainEvents:
    """Test cases for other domain events."""
    
    def test_task_processed_event(self):
        """Test TaskProcessedEvent creation."""
        event = TaskProcessedEvent(
            employee_id="emp-123",
            task_id="task-456",
            result_summary="Successfully processed"
        )
        
        assert event.employee_id == "emp-123"
        assert event.task_id == "task-456"
        assert event.result_summary == "Successfully processed"
        assert event.event_id is not None
        assert event.timestamp is not None
    
    def test_task_processing_failed_event(self):
        """Test TaskProcessingFailedEvent creation."""
        event = TaskProcessingFailedEvent(
            employee_id="emp-123",
            task_id="task-456",
            error_message="Processing failed due to timeout"
        )
        
        assert event.employee_id == "emp-123"
        assert event.task_id == "task-456"
        assert event.error_message == "Processing failed due to timeout"
        assert event.event_id is not None
        assert event.timestamp is not None


class TestTaskStatus:
    """Test TaskStatus enum."""
    
    def test_task_status_values(self):
        """Test TaskStatus enum values."""
        assert TaskStatus.TO_DO.value == "To Do"
        assert TaskStatus.IN_PROGRESS.value == "In Progress"
        assert TaskStatus.DONE.value == "Done"
        assert TaskStatus.CANCELLED.value == "Cancelled"
    
    def test_task_status_from_string(self):
        """Test creating TaskStatus from string."""
        assert TaskStatus("To Do") == TaskStatus.TO_DO
        assert TaskStatus("In Progress") == TaskStatus.IN_PROGRESS
        assert TaskStatus("Done") == TaskStatus.DONE
        assert TaskStatus("Cancelled") == TaskStatus.CANCELLED
        
        with pytest.raises(ValueError):
            TaskStatus("Invalid Status")