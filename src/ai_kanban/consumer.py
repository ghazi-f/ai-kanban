"""New DDD-based consumer service for processing tasks with AI employees."""

import asyncio
import json
import signal
import logging
from typing import List, Dict, Any

import aio_pika
from dotenv import load_dotenv

from .domain.events import NotionTask, TaskStatus
from .domain.artificial_employee import EmployeeRegistry, ArtificialEmployee
from .domain.services import TaskAssignmentService, TaskStatusService, TaskContentService
from .infrastructure.repositories import RepositoryFactory
from .infrastructure.notion_mapper import NotionTaskMapper
from .factories.employee_factory import EmployeeFactory

load_dotenv()


class TaskConsumer:
    """Task consumer using AI employees and LangGraph workflows."""
    
    def __init__(
        self,
        employee_registry: EmployeeRegistry,
        rabbitmq_url: str = "amqp://guest:guest@localhost:5672/",
        queue_name: str = "task_notifications",
        max_concurrent_tasks: int = 3
    ):
        self.employee_registry = employee_registry
        self.rabbitmq_url = rabbitmq_url
        self.queue_name = queue_name
        self.max_concurrent_tasks = max_concurrent_tasks
        
        # Initialize repositories
        self.memory_repository = RepositoryFactory.create_memory_repository()
        self.task_repository = RepositoryFactory.create_task_repository()
        self.event_repository = RepositoryFactory.create_event_repository()
        
        # Initialize domain services
        self.assignment_service = TaskAssignmentService(employee_registry)
        self.status_service = TaskStatusService(self.task_repository)
        self.content_service = TaskContentService(self.task_repository)
        
        # Connection objects
        self.connection: aio_pika.abc.AbstractConnection | None = None
        self.channel: aio_pika.abc.AbstractChannel | None = None
        self.queue: aio_pika.abc.AbstractQueue | None = None
        
        # Control flags
        self.running = False
        self.semaphore = asyncio.Semaphore(max_concurrent_tasks)
        
        self.logger = logging.getLogger(__name__)
    
    async def connect(self):
        """Establish connection to RabbitMQ."""
        try:
            self.connection = await aio_pika.connect_robust(self.rabbitmq_url)
            self.channel = await self.connection.channel()
            
            # Set QoS to limit concurrent processing
            await self.channel.set_qos(prefetch_count=self.max_concurrent_tasks)
            
            # Declare queue
            self.queue = await self.channel.declare_queue(
                self.queue_name,
                durable=True
            )
            
            self.logger.info(f"Connected to RabbitMQ queue: {self.queue_name}")
        
        except Exception as e:
            self.logger.error(f"Failed to connect to RabbitMQ: {e}")
            raise
    
    async def disconnect(self):
        """Close RabbitMQ connection."""
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
            self.logger.info("Disconnected from RabbitMQ")
    
    async def process_message(self, message: aio_pika.abc.AbstractIncomingMessage) -> None:
        """Process a single task message using domain-driven approach."""
        async with self.semaphore:
            try:
                async with message.process():
                    # Parse task data and convert to domain object
                    task_data = json.loads(message.body.decode())
                    task = NotionTask.from_notion_data(task_data)
                    
                    self.logger.info(f"Processing task: {task.title} (ID: {task.notion_id})")
                    
                    # Validate assignment and find capable employee
                    if not self.assignment_service.validate_assignment(task):
                        self.logger.warning(f"Task {task.notion_id} assignment validation failed")
                        return
                    
                    assigned_employee = self.assignment_service.find_assigned_employee(task)
                    if not assigned_employee:
                        self.logger.warning(f"No employee found for assignment: {task.ai_employee}")
                        return
                    
                    # Get full task content if needed
                    if not task.content:
                        full_content = await self.content_service.get_full_task_content(task)
                        if full_content:
                            task = task.with_content(full_content)
                    
                    # Update status to "In Progress"
                    success = await self.status_service.transition_to_in_progress(task)
                    if not success:
                        self.logger.warning(f"Failed to transition task {task.notion_id} to In Progress")
                        return
                    
                    # Update task object with new status for subsequent transitions
                    task_dict = task.to_dict()
                    task_dict['status'] = "In Progress"
                    
                    # Convert datetime strings back to datetime objects
                    from datetime import datetime
                    if isinstance(task_dict.get('timestamp'), str):
                        task_dict['timestamp'] = datetime.fromisoformat(task_dict['timestamp'])
                    if isinstance(task_dict.get('last_edited_time'), str):
                        task_dict['last_edited_time'] = datetime.fromisoformat(task_dict['last_edited_time'])
                    if isinstance(task_dict.get('created_time'), str):
                        task_dict['created_time'] = datetime.fromisoformat(task_dict['created_time'])
                    
                    # Convert status string back to enum
                    task_dict['status'] = TaskStatus(task_dict['status'])
                    
                    # Remove Event fields for reconstruction
                    task_dict.pop('event_id', None)
                    task_dict.pop('timestamp', None)
                    task_dict.pop('metadata', None)
                    task = NotionTask(**task_dict)
                    
                    # Process with assigned employee
                    try:
                        result = await assigned_employee.process_task(task)
                        
                        if result.success:
                            # Post result as comment to Notion
                            await self._post_result_to_notion(task, result, assigned_employee)
                            
                            # Update status to "Done"
                            await self.status_service.transition_to_done(task)
                            
                            # Mark as AI processed
                            await self.task_repository.update_ai_processed(task.notion_id, True)
                            
                            self.logger.info(f"Successfully processed task {task.title} with {assigned_employee.name}")
                        else:
                            # Handle failure
                            self.logger.error(f"Task processing failed: {result.errors}")
                            await self.status_service.revert_to_todo(task)
                    
                    except Exception as e:
                        self.logger.error(f"Error processing task with employee {assigned_employee.name}: {e}")
                        await self.status_service.revert_to_todo(task)
                    
                    # Store domain events
                    await self._store_domain_events(assigned_employee)
            
            except json.JSONDecodeError:
                self.logger.error(f"Invalid JSON in message: {message.body}")
            except Exception as e:
                self.logger.error(f"Error processing message: {e}")
    
    async def _post_result_to_notion(self, task: NotionTask, result, employee) -> None:
        """Post processing result as a comment to the Notion task."""
        try:
            if not result.results:
                self.logger.warning(f"No results to post for task {task.notion_id}")
                return
            
            ai_response = result.results[0]  # Take the main result
            model_used = result.model_used or "claude-3-5-sonnet-20241022"
            
            # Create comment blocks using mapper
            comment_blocks = NotionTaskMapper.create_comment_blocks(
                ai_response, employee.name, model_used
            )
            
            # Post comment
            success = await self.task_repository.post_comment_to_task(
                task.notion_id, comment_blocks
            )
            
            if success:
                self.logger.info(f"Posted comment to task {task.notion_id}")
            else:
                self.logger.error(f"Failed to post comment to task {task.notion_id}")
        
        except Exception as e:
            self.logger.error(f"Error posting result to Notion: {e}")
    
    async def _store_domain_events(self, employee: ArtificialEmployee) -> None:
        """Store domain events from the employee."""
        try:
            events = employee.get_domain_events()
            for event in events:
                await self.event_repository.store_event(event)
        except Exception as e:
            self.logger.error(f"Error storing domain events: {e}")
    
    async def start_consuming(self):
        """Start consuming messages from the queue."""
        if not self.connection:
            await self.connect()
        
        self.running = True
        active_employees = self.employee_registry.get_active_employees()
        self.logger.info(f"Starting task consumer with {len(active_employees)} active employees")
        
        for employee in active_employees:
            self.logger.info(f"  - {employee.name}: {employee.get_available_workflow_types()}")
        
        try:
            # Start consuming messages
            await self.queue.consume(self.process_message)
            
            # Keep the consumer running
            while self.running:
                await asyncio.sleep(1)
        
        except Exception as e:
            self.logger.error(f"Error in consumer loop: {e}")
            raise
        finally:
            await self.disconnect()
    
    def stop(self):
        """Stop the consumer."""
        self.running = False
        self.logger.info("Stopping domain-driven task consumer...")
    
    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            self.logger.info(f"Received signal {signum}, shutting down...")
            self.stop()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def get_consumer_stats(self) -> Dict[str, Any]:
        """Get consumer statistics."""
        return {
            "running": self.running,
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "queue_name": self.queue_name,
            "employee_registry_stats": self.employee_registry.get_registry_stats()
        }


async def create_default_consumer() -> TaskConsumer:
    """Create a consumer with default configuration."""
    import os
    
    # Create repositories
    memory_repository = RepositoryFactory.create_memory_repository()
    
    # Create employee factory and registry
    employee_factory = EmployeeFactory(memory_repository)
    employee_registry = employee_factory.create_default_employee_registry()
    
    # Configure RabbitMQ connection
    rabbitmq_url = (
        f"amqp://{os.getenv('RABBITMQ_USERNAME', 'guest')}:"
        f"{os.getenv('RABBITMQ_PASSWORD', 'guest')}@"
        f"{os.getenv('RABBITMQ_HOST', 'localhost')}:"
        f"{os.getenv('RABBITMQ_PORT', '5672')}/"
    )
    queue_name = os.getenv('RABBITMQ_QUEUE', 'task_notifications')
    
    # Create consumer
    consumer = TaskConsumer(
        employee_registry=employee_registry,
        rabbitmq_url=rabbitmq_url,
        queue_name=queue_name,
        max_concurrent_tasks=3
    )
    
    return consumer


async def main():
    """Main entry point for the domain-driven consumer service."""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    consumer = await create_default_consumer()
    consumer.setup_signal_handlers()
    
    try:
        await consumer.start_consuming()
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
    except Exception as e:
        print(f"Consumer error: {e}")
    finally:
        consumer.stop()


if __name__ == "__main__":
    asyncio.run(main())