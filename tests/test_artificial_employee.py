"""Tests for ArtificialEmployee and related domain objects."""

import pytest
from unittest.mock import Mock, AsyncMock
from datetime import datetime

from ai_kanban.domain.artificial_employee import (
    ArtificialEmployee, EmployeeRegistry, EmployeeReaction, TaskProcessingResult
)
from ai_kanban.domain.events import NotionTask, TaskStatus
from ai_kanban.domain.event_checks import AssignmentCheck, KeywordCheck
from ai_kanban.domain.repositories import MemoryRepository


class TestEmployeeReaction:
    """Test cases for EmployeeReaction."""
    
    def test_employee_reaction_creation(self):
        """Test creating an EmployeeReaction."""
        event_check = AssignmentCheck()
        reaction = EmployeeReaction(
            event_check=event_check,
            workflow_type="test_workflow",
            priority=5
        )
        
        assert reaction.event_check == event_check
        assert reaction.workflow_type == "test_workflow"
        assert reaction.priority == 5


class TestTaskProcessingResult:
    """Test cases for TaskProcessingResult."""
    
    def test_task_processing_result_success(self):
        """Test successful task processing result."""
        result = TaskProcessingResult(
            task_id="task-123",
            employee_id="emp-456",
            workflow_type="specification",
            success=True,
            results=["Great specification created"],
            errors=[],
            execution_time=2.5,
            model_used="claude-3-sonnet"
        )
        
        assert result.task_id == "task-123"
        assert result.employee_id == "emp-456"
        assert result.success is True
        assert len(result.results) == 1
        assert len(result.errors) == 0
        assert result.execution_time == 2.5
    
    def test_task_processing_result_failure(self):
        """Test failed task processing result."""
        result = TaskProcessingResult(
            task_id="task-123",
            employee_id="emp-456",
            workflow_type="research",
            success=False,
            results=[],
            errors=["Network timeout", "API limit exceeded"],
            execution_time=10.0
        )
        
        assert result.success is False
        assert len(result.results) == 0
        assert len(result.errors) == 2


class TestArtificialEmployee:
    """Test cases for ArtificialEmployee."""
    
    @pytest.fixture
    def mock_memory_repository(self):
        """Create a mock memory repository."""
        mock_repo = AsyncMock(spec=MemoryRepository)
        return mock_repo
    
    @pytest.fixture
    def sample_employee(self, mock_memory_repository):
        """Create a sample employee for testing."""
        return ArtificialEmployee(
            employee_id="emp-123",
            name="TestEmployee",
            persona_system_prompt="You are a test employee.",
            memory_repository=mock_memory_repository
        )
    
    @pytest.fixture
    def sample_task(self):
        """Create a sample task for testing."""
        return NotionTask(
            notion_id="task-456",
            title="Test Task",
            status=TaskStatus.TO_DO,
            description="Test description",
            ai_employee="TestEmployee",
            created_by="user123"
        )
    
    def test_employee_creation(self, mock_memory_repository):
        """Test creating an ArtificialEmployee."""
        employee = ArtificialEmployee(
            employee_id="emp-123",
            name="TestEmployee",
            persona_system_prompt="You are a helpful assistant.",
            memory_repository=mock_memory_repository
        )
        
        assert employee.employee_id == "emp-123"
        assert employee.name == "TestEmployee"
        assert employee.is_active is True
        assert employee.success_rate == 0.0
        assert len(employee._reactions) == 0
        assert len(employee._workflows) == 0
    
    def test_employee_activation_deactivation(self, sample_employee):
        """Test employee activation and deactivation."""
        # Initially active
        assert sample_employee.is_active
        
        # Deactivate
        sample_employee.deactivate()
        assert not sample_employee.is_active
        
        # Check domain event was created
        events = sample_employee.get_domain_events()
        assert len(events) == 1
        assert events[0].__class__.__name__ == "EmployeeDeactivatedEvent"
        
        # Activate again
        sample_employee.activate()
        assert sample_employee.is_active
        
        events = sample_employee.get_domain_events()
        assert len(events) == 1
        assert events[0].__class__.__name__ == "EmployeeActivatedEvent"
    
    def test_employee_activation_error(self, sample_employee):
        """Test error when activating already active employee."""
        assert sample_employee.is_active
        
        with pytest.raises(ValueError, match="already active"):
            sample_employee.activate()
    
    def test_employee_deactivation_error(self, sample_employee):
        """Test error when deactivating already inactive employee."""
        sample_employee.deactivate()
        
        with pytest.raises(ValueError, match="already inactive"):
            sample_employee.deactivate()
    
    def test_add_reaction(self, sample_employee):
        """Test adding reactions to employee."""
        event_check = AssignmentCheck()
        
        sample_employee.add_reaction(event_check, "test_workflow", priority=10)
        
        assert len(sample_employee._reactions) == 1
        assert sample_employee._reactions[0].workflow_type == "test_workflow"
        assert sample_employee._reactions[0].priority == 10
    
    def test_reaction_priority_sorting(self, sample_employee):
        """Test that reactions are sorted by priority."""
        check1 = AssignmentCheck()
        check2 = KeywordCheck(["test"])
        
        # Add reactions in wrong order
        sample_employee.add_reaction(check1, "low_priority", priority=1)
        sample_employee.add_reaction(check2, "high_priority", priority=10)
        
        # Should be sorted by priority (highest first)
        assert sample_employee._reactions[0].workflow_type == "high_priority"
        assert sample_employee._reactions[1].workflow_type == "low_priority"
    
    def test_add_workflow(self, sample_employee):
        """Test adding workflows to employee."""
        mock_workflow = Mock()
        mock_workflow.workflow_type = "test_workflow"
        
        sample_employee.add_workflow("test_workflow", mock_workflow)
        
        assert "test_workflow" in sample_employee._workflows
        assert sample_employee._workflows["test_workflow"] == mock_workflow
    
    def test_can_handle_task_type_assigned_and_matches(self, sample_employee, sample_task):
        """Test employee can handle task when assigned and reactions match."""
        # Add reaction that will match
        assignment_check = AssignmentCheck()
        sample_employee.add_reaction(assignment_check, "test_workflow")
        
        assert sample_employee.can_handle_task_type(sample_task)
    
    def test_can_handle_task_type_not_assigned(self, sample_employee):
        """Test employee cannot handle task when not assigned."""
        # Task assigned to different employee
        task = NotionTask(
            notion_id="task-456",
            title="Test Task",
            status=TaskStatus.TO_DO,
            ai_employee="DifferentEmployee",
            created_by="user123"
        )
        
        assignment_check = AssignmentCheck()
        sample_employee.add_reaction(assignment_check, "test_workflow")
        
        assert not sample_employee.can_handle_task_type(task)
    
    def test_can_handle_task_type_inactive_employee(self, sample_employee, sample_task):
        """Test inactive employee cannot handle tasks."""
        # Deactivate employee
        sample_employee.deactivate()
        sample_employee.get_domain_events()  # Clear events
        
        # Add reaction
        assignment_check = AssignmentCheck()
        sample_employee.add_reaction(assignment_check, "test_workflow")
        
        assert not sample_employee.can_handle_task_type(sample_task)
    
    def test_can_handle_task_type_no_matching_reactions(self, sample_employee, sample_task):
        """Test employee cannot handle task with no matching reactions."""
        # Add reaction that won't match
        keyword_check = KeywordCheck(["database"])  # Task doesn't contain "database"
        sample_employee.add_reaction(keyword_check, "test_workflow")
        
        assert not sample_employee.can_handle_task_type(sample_task)
    
    def test_get_applicable_workflow(self, sample_employee, sample_task):
        """Test getting applicable workflow for task."""
        # Add reaction and workflow
        assignment_check = AssignmentCheck()
        sample_employee.add_reaction(assignment_check, "test_workflow")
        
        mock_workflow = Mock()
        mock_workflow.workflow_type = "test_workflow"
        sample_employee.add_workflow("test_workflow", mock_workflow)
        
        workflow = sample_employee.get_applicable_workflow(sample_task)
        assert workflow == mock_workflow
    
    def test_get_applicable_workflow_no_match(self, sample_employee, sample_task):
        """Test getting workflow when no reactions match."""
        # Add reaction that won't match
        keyword_check = KeywordCheck(["database"])
        sample_employee.add_reaction(keyword_check, "test_workflow")
        
        workflow = sample_employee.get_applicable_workflow(sample_task)
        assert workflow is None
    
    def test_get_applicable_workflow_missing_workflow(self, sample_employee, sample_task):
        """Test getting workflow when reaction matches but workflow not registered."""
        # Add reaction without corresponding workflow
        assignment_check = AssignmentCheck()
        sample_employee.add_reaction(assignment_check, "missing_workflow")
        
        workflow = sample_employee.get_applicable_workflow(sample_task)
        assert workflow is None
    
    def test_get_available_workflow_types(self, sample_employee):
        """Test getting available workflow types."""
        mock_workflow1 = Mock()
        mock_workflow2 = Mock()
        
        sample_employee.add_workflow("workflow1", mock_workflow1)
        sample_employee.add_workflow("workflow2", mock_workflow2)
        
        workflow_types = sample_employee.get_available_workflow_types()
        assert set(workflow_types) == {"workflow1", "workflow2"}
    
    @pytest.mark.asyncio
    async def test_process_task_success(self, sample_employee, sample_task):
        """Test successful task processing."""
        # Setup employee with reaction and workflow
        assignment_check = AssignmentCheck()
        sample_employee.add_reaction(assignment_check, "test_workflow")
        
        mock_workflow = AsyncMock()
        mock_workflow.workflow_type = "test_workflow"
        mock_workflow.execute.return_value = TaskProcessingResult(
            task_id=sample_task.notion_id,
            employee_id=sample_employee.employee_id,
            workflow_type="test_workflow",
            success=True,
            results=["Test result"],
            errors=[],
            execution_time=1.0
        )
        sample_employee.add_workflow("test_workflow", mock_workflow)
        
        result = await sample_employee.process_task(sample_task)
        
        assert result.success
        assert result.results == ["Test result"]
        assert sample_employee._tasks_processed == 1
        assert sample_employee._success_count == 1
        assert sample_employee.success_rate == 1.0
        
        # Check domain event
        events = sample_employee.get_domain_events()
        assert len(events) == 1
        assert events[0].__class__.__name__ == "TaskProcessedEvent"
    
    @pytest.mark.asyncio
    async def test_process_task_not_assigned(self, sample_employee):
        """Test processing task not assigned to employee."""
        task = NotionTask(
            notion_id="task-456",
            title="Test Task",
            status=TaskStatus.TO_DO,
            ai_employee="DifferentEmployee",
            created_by="user123"
        )
        
        with pytest.raises(ValueError, match="not assigned"):
            await sample_employee.process_task(task)
    
    @pytest.mark.asyncio
    async def test_process_task_cannot_handle_type(self, sample_employee, sample_task):
        """Test processing task employee cannot handle."""
        # No reactions added, so employee cannot handle task
        
        with pytest.raises(ValueError, match="cannot handle task type"):
            await sample_employee.process_task(sample_task)
    
    @pytest.mark.asyncio
    async def test_process_task_no_workflow(self, sample_employee, sample_task):
        """Test processing task with no available workflow."""
        # Add reaction but no workflow
        assignment_check = AssignmentCheck()
        sample_employee.add_reaction(assignment_check, "missing_workflow")
        
        with pytest.raises(ValueError, match="No workflow available"):
            await sample_employee.process_task(sample_task)
    
    def test_get_performance_stats(self, sample_employee):
        """Test getting employee performance statistics."""
        stats = sample_employee.get_performance_stats()
        
        assert stats["employee_id"] == "emp-123"
        assert stats["name"] == "TestEmployee"
        assert stats["is_active"] is True
        assert stats["tasks_processed"] == 0
        assert stats["success_count"] == 0
        assert stats["success_rate"] == 0.0
        assert stats["last_activity"] is None
        assert stats["available_workflows"] == []


class TestEmployeeRegistry:
    """Test cases for EmployeeRegistry."""
    
    @pytest.fixture
    def mock_memory_repository(self):
        """Create a mock memory repository."""
        return AsyncMock(spec=MemoryRepository)
    
    @pytest.fixture
    def sample_employee(self, mock_memory_repository):
        """Create a sample employee for testing."""
        return ArtificialEmployee(
            employee_id="emp-123",
            name="TestEmployee",
            persona_system_prompt="You are a test employee.",
            memory_repository=mock_memory_repository
        )
    
    def test_registry_creation(self):
        """Test creating an empty registry."""
        registry = EmployeeRegistry()
        
        assert len(registry.get_all_employees()) == 0
        assert len(registry.get_active_employees()) == 0
    
    def test_register_employee(self, sample_employee):
        """Test registering an employee."""
        registry = EmployeeRegistry()
        registry.register_employee(sample_employee)
        
        assert len(registry.get_all_employees()) == 1
        assert len(registry.get_active_employees()) == 1
        assert registry.get_employee("emp-123") == sample_employee
        assert registry.get_employee_by_name("TestEmployee") == sample_employee
        assert registry.get_employee_by_name("testemployee") == sample_employee  # case insensitive
    
    def test_register_duplicate_id(self, sample_employee, mock_memory_repository):
        """Test registering employee with duplicate ID."""
        registry = EmployeeRegistry()
        registry.register_employee(sample_employee)
        
        # Try to register another employee with same ID
        duplicate_employee = ArtificialEmployee(
            employee_id="emp-123",  # Same ID
            name="DifferentEmployee",
            persona_system_prompt="Different employee.",
            memory_repository=mock_memory_repository
        )
        
        with pytest.raises(ValueError, match="already registered"):
            registry.register_employee(duplicate_employee)
    
    def test_register_duplicate_name(self, sample_employee, mock_memory_repository):
        """Test registering employee with duplicate name."""
        registry = EmployeeRegistry()
        registry.register_employee(sample_employee)
        
        # Try to register another employee with same name
        duplicate_employee = ArtificialEmployee(
            employee_id="emp-456",
            name="TestEmployee",  # Same name
            persona_system_prompt="Different employee.",
            memory_repository=mock_memory_repository
        )
        
        with pytest.raises(ValueError, match="already registered"):
            registry.register_employee(duplicate_employee)
    
    def test_get_employee_not_found(self):
        """Test getting non-existent employee."""
        registry = EmployeeRegistry()
        
        assert registry.get_employee("non-existent") is None
        assert registry.get_employee_by_name("NonExistent") is None
    
    def test_get_active_vs_all_employees(self, sample_employee):
        """Test difference between active and all employees."""
        registry = EmployeeRegistry()
        registry.register_employee(sample_employee)
        
        # Initially active
        assert len(registry.get_all_employees()) == 1
        assert len(registry.get_active_employees()) == 1
        
        # Deactivate employee
        sample_employee.deactivate()
        
        # Still in all employees, but not in active
        assert len(registry.get_all_employees()) == 1
        assert len(registry.get_active_employees()) == 0
    
    def test_remove_employee(self, sample_employee):
        """Test removing an employee."""
        registry = EmployeeRegistry()
        registry.register_employee(sample_employee)
        
        # Remove employee
        success = registry.remove_employee("emp-123")
        
        assert success
        assert len(registry.get_all_employees()) == 0
        assert registry.get_employee("emp-123") is None
        assert registry.get_employee_by_name("TestEmployee") is None
    
    def test_remove_nonexistent_employee(self):
        """Test removing non-existent employee."""
        registry = EmployeeRegistry()
        
        success = registry.remove_employee("non-existent")
        assert not success
    
    def test_get_employees_for_task(self, sample_employee):
        """Test getting employees that can handle a task."""
        registry = EmployeeRegistry()
        registry.register_employee(sample_employee)
        
        # Add reaction to employee
        assignment_check = AssignmentCheck()
        sample_employee.add_reaction(assignment_check, "test_workflow")
        
        # Task assigned to employee
        task = NotionTask(
            notion_id="task-456",
            title="Test Task",
            status=TaskStatus.TO_DO,
            ai_employee="TestEmployee",
            created_by="user123"
        )
        
        candidates = registry.get_employees_for_task(task)
        assert len(candidates) == 1
        assert candidates[0] == sample_employee
    
    def test_get_employees_for_task_no_candidates(self, sample_employee):
        """Test getting employees for task with no candidates."""
        registry = EmployeeRegistry()
        registry.register_employee(sample_employee)
        
        # Task assigned to different employee
        task = NotionTask(
            notion_id="task-456",
            title="Test Task",
            status=TaskStatus.TO_DO,
            ai_employee="DifferentEmployee",
            created_by="user123"
        )
        
        candidates = registry.get_employees_for_task(task)
        assert len(candidates) == 0
    
    def test_get_registry_stats(self, sample_employee, mock_memory_repository):
        """Test getting registry statistics."""
        registry = EmployeeRegistry()
        registry.register_employee(sample_employee)
        
        # Add another inactive employee
        inactive_employee = ArtificialEmployee(
            employee_id="emp-456",
            name="InactiveEmployee",
            persona_system_prompt="Inactive employee.",
            memory_repository=mock_memory_repository
        )
        inactive_employee.deactivate()
        registry.register_employee(inactive_employee)
        
        stats = registry.get_registry_stats()
        
        assert stats["total_employees"] == 2
        assert stats["active_employees"] == 1
        assert stats["inactive_employees"] == 1
        assert len(stats["employees"]) == 2