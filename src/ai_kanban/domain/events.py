"""Domain events for the AI Kanban system."""

from abc import ABC
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from uuid import UUID, uuid4
from enum import Enum


class Event(ABC):
    """Base domain event - immutable record of something that happened."""
    
    def __init__(self, event_id: UUID = None, timestamp: datetime = None, metadata: Dict[str, Any] = None):
        self.event_id = event_id or uuid4()
        self.timestamp = timestamp or datetime.utcnow()
        self.metadata = metadata or {}


class TaskStatus(Enum):
    """Task status enumeration matching Notion values."""
    TO_DO = "To Do"
    IN_PROGRESS = "In Progress"
    DONE = "Done"
    CANCELLED = "Cancelled"


@dataclass(frozen=True)
class NotionTask(Event):
    """Domain event representing a task from Notion with AI employee assignment."""
    
    # Core required properties
    notion_id: str
    title: str
    status: TaskStatus
    created_by: str
    
    # Optional properties with defaults
    description: str = ""
    content: str = ""
    ai_employee: Optional[str] = None  # This drives task routing
    assigned_to: Optional[str] = None
    github_url: Optional[str] = None
    notion_url: str = ""
    last_edited_time: Optional[datetime] = None
    created_time: Optional[datetime] = None
    
    # Event properties (inherited)
    event_id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        # Business invariants
        if not self.notion_id:
            raise ValueError("NotionTask must have notion_id")
        if not self.title.strip():
            raise ValueError("NotionTask must have non-empty title")
    
    # Domain logic
    def has_ai_employee_assigned(self) -> bool:
        """Business rule: Check if AI employee is assigned via column."""
        return self.ai_employee is not None and self.ai_employee.strip() != ""
    
    def is_assigned_to_employee(self, employee_name: str) -> bool:
        """Business rule: Check if task is assigned to specific employee by name."""
        if not self.has_ai_employee_assigned():
            return False
        return self.ai_employee.lower().strip() == employee_name.lower().strip()
    
    def can_be_processed(self) -> bool:
        """Business rule: Task processability."""
        return (self.status in [TaskStatus.TO_DO, TaskStatus.IN_PROGRESS] and 
                self.has_ai_employee_assigned())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_id": str(self.event_id),
            "timestamp": self.timestamp.isoformat(),
            "notion_id": self.notion_id,
            "title": self.title,
            "status": self.status.value,
            "description": self.description,
            "content": self.content,
            "ai_employee": self.ai_employee,
            "assigned_to": self.assigned_to,
            "created_by": self.created_by,
            "github_url": self.github_url,
            "notion_url": self.notion_url,
            "last_edited_time": self.last_edited_time.isoformat() if self.last_edited_time else None,
            "created_time": self.created_time.isoformat() if self.created_time else None,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_notion_data(cls, notion_task_data: Dict[str, Any]) -> 'NotionTask':
        """Create NotionTask from raw Notion API data."""
        from ..infrastructure.notion_mapper import NotionTaskMapper
        return NotionTaskMapper.map_to_domain(notion_task_data)
    
    def with_content(self, new_content: str) -> 'NotionTask':
        """Create a new NotionTask with updated content."""
        task_dict = self.to_dict()
        task_dict['content'] = new_content
        
        # Convert datetime strings back to datetime objects
        from datetime import datetime
        if isinstance(task_dict.get('timestamp'), str):
            task_dict['timestamp'] = datetime.fromisoformat(task_dict['timestamp'])
        if isinstance(task_dict.get('last_edited_time'), str):
            task_dict['last_edited_time'] = datetime.fromisoformat(task_dict['last_edited_time'])
        if isinstance(task_dict.get('created_time'), str):
            task_dict['created_time'] = datetime.fromisoformat(task_dict['created_time'])
        
        # Convert status string back to enum
        if isinstance(task_dict.get('status'), str):
            task_dict['status'] = TaskStatus(task_dict['status'])
        
        # Remove fields that aren't in the NotionTask constructor
        constructor_fields = {f.name for f in self.__dataclass_fields__.values()}
        filtered_dict = {k: v for k, v in task_dict.items() if k in constructor_fields}
        return NotionTask(**filtered_dict)


@dataclass(frozen=True)
class TaskProcessedEvent(Event):
    """Event fired when a task is successfully processed by an AI employee."""
    employee_id: str
    task_id: str
    result_summary: str
    
    # Event properties (inherited)
    event_id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TaskProcessingFailedEvent(Event):
    """Event fired when task processing fails."""
    employee_id: str
    task_id: str
    error_message: str
    
    # Event properties (inherited)
    event_id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EmployeeActivatedEvent(Event):
    """Event fired when an AI employee is activated."""
    employee_id: str
    
    # Event properties (inherited)
    event_id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EmployeeDeactivatedEvent(Event):
    """Event fired when an AI employee is deactivated."""
    employee_id: str
    
    # Event properties (inherited)
    event_id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TaskStatusChangedEvent(Event):
    """Event fired when a task status changes."""
    task_id: str
    old_status: TaskStatus
    new_status: TaskStatus
    changed_by: str
    
    # Event properties (inherited)
    event_id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)