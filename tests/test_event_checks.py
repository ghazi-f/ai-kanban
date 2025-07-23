"""Tests for event check system."""

import pytest
from unittest.mock import Mock

from ai_kanban.domain.events import NotionTask, TaskStatus
from ai_kanban.domain.event_checks import (
    AssignmentCheck, KeywordCheck, StatusCheck, CompositeCheck, ContentLengthCheck
)


class TestAssignmentCheck:
    """Test cases for AssignmentCheck."""
    
    def test_assignment_check_matches(self):
        """Test assignment check matching."""
        check = AssignmentCheck()
        employee = Mock()
        employee.name = "TestEmployee"
        
        # Task assigned to employee
        assigned_task = NotionTask(
            notion_id="test-123",
            title="Test Task",
            status=TaskStatus.TO_DO,
            ai_employee="TestEmployee",
            created_by="user123"
        )
        assert check.matches(assigned_task, employee)
        
        # Task not assigned to employee
        not_assigned_task = NotionTask(
            notion_id="test-123",
            title="Test Task",
            status=TaskStatus.TO_DO,
            ai_employee="OtherEmployee",
            created_by="user123"
        )
        assert not check.matches(not_assigned_task, employee)
        
        # Task with no assignment
        no_assignment_task = NotionTask(
            notion_id="test-123",
            title="Test Task",
            status=TaskStatus.TO_DO,
            ai_employee=None,
            created_by="user123"
        )
        assert not check.matches(no_assignment_task, employee)


class TestKeywordCheck:
    """Test cases for KeywordCheck."""
    
    def test_keyword_check_in_title(self):
        """Test keyword check in title."""
        check = KeywordCheck(["research", "investigate"])
        employee = Mock()
        
        task = NotionTask(
            notion_id="test-123",
            title="Research the new technology",
            status=TaskStatus.TO_DO,
            ai_employee="TestEmployee",
            created_by="user123"
        )
        assert check.matches(task, employee)
    
    def test_keyword_check_in_description(self):
        """Test keyword check in description."""
        check = KeywordCheck(["documentation"])
        employee = Mock()
        
        task = NotionTask(
            notion_id="test-123",
            title="Code Task",
            status=TaskStatus.TO_DO,
            description="Create documentation for the API",
            ai_employee="TestEmployee",
            created_by="user123"
        )
        assert check.matches(task, employee)
    
    def test_keyword_check_in_content(self):
        """Test keyword check in content."""
        check = KeywordCheck(["python", "code"])
        employee = Mock()
        
        task = NotionTask(
            notion_id="test-123",
            title="Development Task",
            status=TaskStatus.TO_DO,
            content="```python\ndef hello_world():\n    print('Hello')\n```",
            ai_employee="TestEmployee",
            created_by="user123"
        )
        assert check.matches(task, employee)
    
    def test_keyword_check_case_insensitive(self):
        """Test keyword check is case insensitive."""
        check = KeywordCheck(["SPEC", "Architecture"])
        employee = Mock()
        
        task = NotionTask(
            notion_id="test-123",
            title="Create spec for the architecture",
            status=TaskStatus.TO_DO,
            ai_employee="TestEmployee",
            created_by="user123"
        )
        assert check.matches(task, employee)
    
    def test_keyword_check_no_match(self):
        """Test keyword check with no matches."""
        check = KeywordCheck(["database", "sql"])
        employee = Mock()
        
        task = NotionTask(
            notion_id="test-123",
            title="Frontend development task",
            status=TaskStatus.TO_DO,
            description="Create React components",
            ai_employee="TestEmployee",
            created_by="user123"
        )
        assert not check.matches(task, employee)
    
    def test_keyword_check_custom_fields(self):
        """Test keyword check with custom fields."""
        check = KeywordCheck(["urgent"], check_fields=["title"])
        employee = Mock()
        
        # Keyword in title - should match
        task1 = NotionTask(
            notion_id="test-123",
            title="Urgent task",
            status=TaskStatus.TO_DO,
            description="Not urgent at all",
            ai_employee="TestEmployee",
            created_by="user123"
        )
        assert check.matches(task1, employee)
        
        # Keyword only in description - should not match
        task2 = NotionTask(
            notion_id="test-123",
            title="Regular task",
            status=TaskStatus.TO_DO,
            description="This is urgent",
            ai_employee="TestEmployee",
            created_by="user123"
        )
        assert not check.matches(task2, employee)


class TestStatusCheck:
    """Test cases for StatusCheck."""
    
    def test_status_check_matches(self):
        """Test status check matching."""
        check = StatusCheck(["To Do", "In Progress"])
        employee = Mock()
        
        # TO_DO status
        todo_task = NotionTask(
            notion_id="test-123",
            title="Test Task",
            status=TaskStatus.TO_DO,
            ai_employee="TestEmployee",
            created_by="user123"
        )
        assert check.matches(todo_task, employee)
        
        # IN_PROGRESS status
        in_progress_task = NotionTask(
            notion_id="test-123",
            title="Test Task",
            status=TaskStatus.IN_PROGRESS,
            ai_employee="TestEmployee",
            created_by="user123"
        )
        assert check.matches(in_progress_task, employee)
        
        # DONE status (not in check list)
        done_task = NotionTask(
            notion_id="test-123",
            title="Test Task",
            status=TaskStatus.DONE,
            ai_employee="TestEmployee",
            created_by="user123"
        )
        assert not check.matches(done_task, employee)
    
    def test_status_check_invalid_status(self):
        """Test status check with invalid status string."""
        # Invalid status strings are ignored
        check = StatusCheck(["Invalid Status", "To Do"])
        assert len(check.statuses) == 1  # Only "To Do" should be valid


class TestContentLengthCheck:
    """Test cases for ContentLengthCheck."""
    
    def test_content_length_check_passes(self):
        """Test content length check passes with sufficient content."""
        check = ContentLengthCheck(min_length=20)
        employee = Mock()
        
        task = NotionTask(
            notion_id="test-123",
            title="Test Task with Long Title",
            status=TaskStatus.TO_DO,
            description="This is a detailed description",
            ai_employee="TestEmployee",
            created_by="user123"
        )
        assert check.matches(task, employee)
    
    def test_content_length_check_fails(self):
        """Test content length check fails with insufficient content."""
        check = ContentLengthCheck(min_length=50)
        employee = Mock()
        
        task = NotionTask(
            notion_id="test-123",
            title="Short",
            status=TaskStatus.TO_DO,
            description="",
            ai_employee="TestEmployee",
            created_by="user123"
        )
        assert not check.matches(task, employee)
    
    def test_content_length_check_default(self):
        """Test content length check with default minimum."""
        check = ContentLengthCheck()  # Default min_length=10
        employee = Mock()
        
        # Should pass - has enough content in title
        task1 = NotionTask(
            notion_id="test-123",
            title="Test Task With Enough Content",
            status=TaskStatus.TO_DO,
            ai_employee="TestEmployee",
            created_by="user123"
        )
        assert check.matches(task1, employee)
        
        # Should fail - short content
        task2 = NotionTask(
            notion_id="test-123",
            title="Short",  # Only 5 chars
            status=TaskStatus.TO_DO,
            description="",
            content="",
            ai_employee="TestEmployee",
            created_by="user123"
        )
        assert not check.matches(task2, employee)


class TestCompositeCheck:
    """Test cases for CompositeCheck."""
    
    def test_composite_check_and_all_pass(self):
        """Test composite check with AND operator - all checks pass."""
        assignment_check = AssignmentCheck()
        keyword_check = KeywordCheck(["research"])
        content_check = ContentLengthCheck(min_length=10)
        
        composite = CompositeCheck([assignment_check, keyword_check, content_check], "AND")
        
        employee = Mock()
        employee.name = "TestEmployee"
        
        task = NotionTask(
            notion_id="test-123",
            title="Research the new technology",
            status=TaskStatus.TO_DO,
            ai_employee="TestEmployee",
            created_by="user123"
        )
        
        assert composite.matches(task, employee)
    
    def test_composite_check_and_one_fails(self):
        """Test composite check with AND operator - one check fails."""
        assignment_check = AssignmentCheck()
        keyword_check = KeywordCheck(["database"])  # Won't match the task
        content_check = ContentLengthCheck(min_length=10)
        
        composite = CompositeCheck([assignment_check, keyword_check, content_check], "AND")
        
        employee = Mock()
        employee.name = "TestEmployee"
        
        task = NotionTask(
            notion_id="test-123",
            title="Research the new technology",
            status=TaskStatus.TO_DO,
            ai_employee="TestEmployee",
            created_by="user123"
        )
        
        assert not composite.matches(task, employee)
    
    def test_composite_check_or_one_passes(self):
        """Test composite check with OR operator - one check passes."""
        assignment_check = AssignmentCheck()
        keyword_check = KeywordCheck(["database"])  # Won't match
        
        composite = CompositeCheck([assignment_check, keyword_check], "OR")
        
        employee = Mock()
        employee.name = "TestEmployee"
        
        task = NotionTask(
            notion_id="test-123",
            title="Research the new technology",
            status=TaskStatus.TO_DO,
            ai_employee="TestEmployee",
            created_by="user123"
        )
        
        assert composite.matches(task, employee)
    
    def test_composite_check_or_none_pass(self):
        """Test composite check with OR operator - no checks pass."""
        assignment_check = AssignmentCheck()
        keyword_check = KeywordCheck(["database"])
        
        composite = CompositeCheck([assignment_check, keyword_check], "OR")
        
        employee = Mock()
        employee.name = "DifferentEmployee"
        
        task = NotionTask(
            notion_id="test-123",
            title="Research the new technology",
            status=TaskStatus.TO_DO,
            ai_employee="TestEmployee",
            created_by="user123"
        )
        
        assert not composite.matches(task, employee)
    
    def test_composite_check_invalid_operator(self):
        """Test composite check with invalid operator."""
        assignment_check = AssignmentCheck()
        
        with pytest.raises(ValueError, match="Unsupported operator"):
            CompositeCheck([assignment_check], "XOR")
    
    def test_composite_check_empty_checks(self):
        """Test composite check with no checks."""
        composite = CompositeCheck([], "AND")
        employee = Mock()
        task = Mock()
        
        assert not composite.matches(task, employee)