"""Tests for the new domain-driven consumer."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import json

from ai_kanban.consumer import TaskConsumer
from ai_kanban.domain.artificial_employee import EmployeeRegistry, ArtificialEmployee
from ai_kanban.domain.events import NotionTask, TaskStatus
from ai_kanban.domain.event_checks import AssignmentCheck
from ai_kanban.infrastructure.repositories import InMemoryMemoryRepository


class TestTaskConsumer:
    """Test cases for TaskConsumer."""
    
    @pytest.fixture
    def mock_memory_repository(self):
        """Create a mock memory repository."""
        return InMemoryMemoryRepository()
    
    @pytest.fixture
    def sample_employee(self, mock_memory_repository):
        """Create a sample employee for testing."""
        employee = ArtificialEmployee(
            employee_id="emp-123",
            name="TestEmployee",
            persona_system_prompt="You are a test employee.",
            memory_repository=mock_memory_repository
        )
        
        # Add reaction and mock workflow
        assignment_check = AssignmentCheck()
        employee.add_reaction(assignment_check, "test_workflow")
        
        mock_workflow = AsyncMock()
        mock_workflow.workflow_type = "test_workflow"
        employee.add_workflow("test_workflow", mock_workflow)
        
        return employee
    
    @pytest.fixture
    def employee_registry(self, sample_employee):
        """Create an employee registry with sample employee."""
        registry = EmployeeRegistry()
        registry.register_employee(sample_employee)
        return registry
    
    @pytest.fixture
    def consumer(self, employee_registry):
        """Create a consumer for testing."""
        with patch('ai_kanban.consumer.RepositoryFactory') as mock_factory:
            # Mock the repository factory
            mock_factory.create_memory_repository.return_value = InMemoryMemoryRepository()
            mock_factory.create_task_repository.return_value = AsyncMock()
            mock_factory.create_event_repository.return_value = AsyncMock()
            
            consumer = TaskConsumer(
                employee_registry=employee_registry,
                rabbitmq_url="amqp://test",
                queue_name="test_queue"
            )
            return consumer
    
    def test_consumer_creation(self, consumer, employee_registry):
        """Test creating a TaskConsumer."""
        assert consumer.employee_registry == employee_registry
        assert consumer.queue_name == "test_queue"
        assert consumer.max_concurrent_tasks == 3
        assert not consumer.running
    
    def test_consumer_stats(self, consumer):
        """Test getting consumer statistics."""
        stats = consumer.get_consumer_stats()
        
        assert "running" in stats
        assert "max_concurrent_tasks" in stats
        assert "queue_name" in stats
        assert "employee_registry_stats" in stats
        
        assert stats["running"] is False
        assert stats["max_concurrent_tasks"] == 3
        assert stats["queue_name"] == "test_queue"
    
    @pytest.mark.asyncio
    async def test_process_message_success(self, consumer, sample_employee):
        """Test successful message processing."""
        # Mock the workflow to return success
        workflow = sample_employee._workflows["test_workflow"]
        workflow.execute.return_value = Mock(
            success=True,
            results=["Test result"],
            errors=[],
            model_used="test-model"
        )
        
        # Create test message
        notion_task_data = {
            "id": "task-123",
            "url": "https://notion.so/task-123",
            "created_time": "2024-01-01T00:00:00.000Z",
            "last_edited_time": "2024-01-01T00:00:00.000Z",
            "properties": {
                "Title": {
                    "type": "title",
                    "title": [{"text": {"content": "Test Research Task"}}]
                },
                "Status": {
                    "type": "status",
                    "status": {"name": "To Do"}
                },
                "AI Employee": {
                    "type": "rich_text",
                    "rich_text": [{"text": {"content": "TestEmployee"}}]
                },
                "created by": {
                    "type": "people",
                    "people": [{"name": "user123"}]
                }
            }
        }
        
        message_body = json.dumps(notion_task_data).encode()
        mock_message = Mock()
        mock_message.body = message_body
        mock_message.process.return_value.__aenter__ = AsyncMock()
        mock_message.process.return_value.__aexit__ = AsyncMock()
        
        # Mock the status service methods
        consumer.status_service.transition_to_in_progress = AsyncMock(return_value=True)
        consumer.status_service.transition_to_done = AsyncMock(return_value=True)
        
        # Mock the task repository
        consumer.task_repository.post_comment_to_task = AsyncMock(return_value=True)
        
        # Process the message
        await consumer.process_message(mock_message)
        
        # Verify the workflow was called
        workflow.execute.assert_called_once()
        
        # Verify status transitions
        consumer.status_service.transition_to_in_progress.assert_called_once()
        consumer.status_service.transition_to_done.assert_called_once()
        
        # Verify comment was posted
        consumer.task_repository.post_comment_to_task.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_process_message_no_assignment(self, consumer):
        """Test message processing with no AI employee assignment."""
        # Create test message without AI employee
        notion_task_data = {
            "id": "task-123",
            "url": "https://notion.so/task-123",
            "created_time": "2024-01-01T00:00:00.000Z",
            "last_edited_time": "2024-01-01T00:00:00.000Z",
            "properties": {
                "Title": {
                    "type": "title",
                    "title": [{"text": {"content": "Test Task"}}]
                },
                "Status": {
                    "type": "status",
                    "status": {"name": "To Do"}
                },
                "created by": {
                    "type": "people",
                    "people": [{"name": "user123"}]
                }
                # No AI Employee property
            }
        }
        
        message_body = json.dumps(notion_task_data).encode()
        mock_message = Mock()
        mock_message.body = message_body
        mock_message.process.return_value.__aenter__ = AsyncMock()
        mock_message.process.return_value.__aexit__ = AsyncMock()
        
        # Process the message
        await consumer.process_message(mock_message)
        
        # Should exit early without processing
        # No assertions about workflows being called since they shouldn't be
    
    @pytest.mark.asyncio
    async def test_process_message_invalid_json(self, consumer):
        """Test message processing with invalid JSON."""
        mock_message = Mock()
        mock_message.body = b"invalid json content"
        mock_message.process.return_value.__aenter__ = AsyncMock()
        mock_message.process.return_value.__aexit__ = AsyncMock()
        
        # Should handle gracefully without raising
        await consumer.process_message(mock_message)
    
    @pytest.mark.asyncio 
    async def test_post_result_to_notion(self, consumer):
        """Test posting results to Notion."""
        task = NotionTask(
            notion_id="task-123",
            title="Test Task",
            status=TaskStatus.TO_DO,
            created_by="user123"
        )
        
        result = Mock()
        result.results = ["Test AI response"]
        result.model_used = "claude-3-sonnet"
        
        employee = Mock()
        employee.name = "TestEmployee"
        
        # Mock the task repository
        consumer.task_repository.post_comment_to_task = AsyncMock(return_value=True)
        
        await consumer._post_result_to_notion(task, result, employee)
        
        # Verify comment was posted with correct structure
        consumer.task_repository.post_comment_to_task.assert_called_once()
        call_args = consumer.task_repository.post_comment_to_task.call_args
        assert call_args[0][0] == "task-123"  # task_id
        assert isinstance(call_args[0][1], list)  # comment_blocks


@pytest.mark.asyncio
async def test_create_default_consumer():
    """Test creating a default consumer configuration."""
    from ai_kanban.consumer import create_default_consumer
    from unittest.mock import patch
    
    with patch.dict('os.environ', {
        'RABBITMQ_USERNAME': 'test_user',
        'RABBITMQ_PASSWORD': 'test_pass',
        'RABBITMQ_HOST': 'test_host',
        'RABBITMQ_PORT': '5673',
        'RABBITMQ_QUEUE': 'test_queue'
    }):
        consumer = await create_default_consumer()
        
        assert consumer is not None
        assert consumer.queue_name == "test_queue"
        assert "test_user:test_pass@test_host:5673" in consumer.rabbitmq_url
        
        # Check that default employees are registered
        registry_stats = consumer.employee_registry.get_registry_stats()
        assert registry_stats["total_employees"] == 3  # EngineeringManager, ResearchAgent, DocSpecialist
        assert registry_stats["active_employees"] == 3