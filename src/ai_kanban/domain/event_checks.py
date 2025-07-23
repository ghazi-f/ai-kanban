"""Event check system for AI employee capability validation."""

from abc import ABC, abstractmethod
from typing import List, TYPE_CHECKING

from .events import Event, NotionTask

if TYPE_CHECKING:
    from .artificial_employee import ArtificialEmployee


class EventCheck(ABC):
    """Abstract base for checking if an event matches certain criteria."""
    
    @abstractmethod
    def matches(self, event: Event, employee: 'ArtificialEmployee') -> bool:
        """Check if the event matches this check's criteria for the given employee."""
        pass


class AssignmentCheck(EventCheck):
    """Check if task is assigned to the specific employee via AI Employee column."""
    
    def matches(self, event: Event, employee: 'ArtificialEmployee') -> bool:
        if not isinstance(event, NotionTask):
            return False
        return event.is_assigned_to_employee(employee.name)


class KeywordCheck(EventCheck):
    """Check if task contains specific keywords indicating task type."""
    
    def __init__(self, keywords: List[str], check_fields: List[str] = None):
        self.keywords = [kw.lower() for kw in keywords]
        self.check_fields = check_fields or ['title', 'description', 'content']
    
    def matches(self, event: Event, employee: 'ArtificialEmployee') -> bool:
        if not isinstance(event, NotionTask):
            return False
        
        text_to_check = ""
        for field in self.check_fields:
            if hasattr(event, field):
                field_value = getattr(event, field) or ""
                text_to_check += f" {field_value}"
        
        text_to_check = text_to_check.lower()
        return any(keyword in text_to_check for keyword in self.keywords)


class StatusCheck(EventCheck):
    """Check if task has specific status."""
    
    def __init__(self, statuses: List[str]):
        from .events import TaskStatus
        self.statuses = []
        for status in statuses:
            try:
                self.statuses.append(TaskStatus(status))
            except ValueError:
                # Handle case where status string doesn't match enum
                continue
    
    def matches(self, event: Event, employee: 'ArtificialEmployee') -> bool:
        if not isinstance(event, NotionTask):
            return False
        return event.status in self.statuses


class CompositeCheck(EventCheck):
    """Combine multiple checks with AND/OR logic."""
    
    def __init__(self, checks: List[EventCheck], operator: str = "AND"):
        self.checks = checks
        self.operator = operator.upper()
        if self.operator not in ["AND", "OR"]:
            raise ValueError(f"Unsupported operator: {self.operator}")
    
    def matches(self, event: Event, employee: 'ArtificialEmployee') -> bool:
        if not self.checks:
            return False
        
        if self.operator == "AND":
            return all(check.matches(event, employee) for check in self.checks)
        elif self.operator == "OR":
            return any(check.matches(event, employee) for check in self.checks)
        
        return False


class ContentLengthCheck(EventCheck):
    """Check if task content meets minimum length requirements."""
    
    def __init__(self, min_length: int = 10):
        self.min_length = min_length
    
    def matches(self, event: Event, employee: 'ArtificialEmployee') -> bool:
        if not isinstance(event, NotionTask):
            return False
        
        total_content = f"{event.title} {event.description} {event.content}".strip()
        return len(total_content) >= self.min_length