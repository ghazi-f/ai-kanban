"""Repository interfaces for the domain layer."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

from .events import Event


class MemoryRepository(ABC):
    """Repository for AI employee memory persistence."""
    
    @abstractmethod
    async def store_memory(self, employee_name: str, memory_text: str, 
                          metadata: Dict[str, Any] = None) -> None:
        """Store a memory for an AI employee."""
        pass
    
    @abstractmethod
    async def get_memories(self, employee_name: str, query: str, limit: int = 10) -> List[str]:
        """Retrieve relevant memories using semantic search."""
        pass
    
    @abstractmethod
    async def get_employee_memory_count(self, employee_name: str) -> int:
        """Get total memory count for an employee."""
        pass


class EventRepository(ABC):
    """Repository for domain events."""
    
    @abstractmethod
    async def store_event(self, event: Event) -> None:
        """Store a domain event."""
        pass
    
    @abstractmethod
    async def get_events_by_type(self, event_type: str, limit: int = 100) -> List[Event]:
        """Get events of a specific type."""
        pass
    
    @abstractmethod
    async def get_events_for_entity(self, entity_id: str, limit: int = 100) -> List[Event]:
        """Get events related to a specific entity."""
        pass


class TaskRepository(ABC):
    """Repository for task-related operations.

    This interface is used to model tasks and how they are handled no matter the external system.
    This interface is to be reworked when external sources other than Notion are added.
    """
    
    @abstractmethod
    async def update_task_status(self, task_id: str, new_status: str) -> bool:
        """Update the status of a task in the external system (Notion)."""
        pass
    
    @abstractmethod
    async def post_comment_to_task(self, task_id: str, comment_content: List[Dict[str, Any]]) -> bool:
        """Post a comment to a task in the external system."""
        pass
    
    @abstractmethod
    async def get_task_content(self, task_id: str) -> Optional[str]:
        """Get the full content of a task page."""
        pass