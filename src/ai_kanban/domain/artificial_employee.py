"""Artificial Employee aggregate root and related domain objects."""

from typing import List, Dict, Optional, Any, TYPE_CHECKING
from dataclasses import dataclass
import logging
from datetime import datetime

from .events import (
    Event, NotionTask, TaskProcessedEvent, TaskProcessingFailedEvent,
    EmployeeActivatedEvent, EmployeeDeactivatedEvent
)
from .event_checks import EventCheck
from .repositories import MemoryRepository

if TYPE_CHECKING:
    from ..workflows.employee_workflow import EmployeeWorkflowGraph


@dataclass
class EmployeeReaction:
    """Represents a condition-action pair for an AI employee."""
    event_check: EventCheck
    workflow_type: str  # Maps to LangGraph workflow
    priority: int = 0  # Higher priority reactions execute first


@dataclass
class TaskProcessingResult:
    """Result of task processing by an AI employee."""
    task_id: str
    employee_id: str
    workflow_type: str
    success: bool
    results: List[str]
    errors: List[str]
    execution_time: float
    model_used: Optional[str] = None


class ArtificialEmployee:
    """Aggregate root for AI employee domain."""
    
    def __init__(self, employee_id: str, name: str, persona_system_prompt: str, 
                 memory_repository: MemoryRepository):
        # Identity
        self._employee_id = employee_id
        self._name = name
        
        # Business properties
        self._persona_system_prompt = persona_system_prompt
        self._memory_repository = memory_repository
        self._is_active = True
        
        # EventCheck system for capability validation
        self._reactions: List[EmployeeReaction] = []
        
        # LangGraph workflows (injected)
        self._workflows: Dict[str, 'EmployeeWorkflowGraph'] = {}
        
        # Domain events
        self._domain_events: List[Event] = []
        
        # Performance tracking
        self._tasks_processed = 0
        self._success_count = 0
        self._last_activity = None
        
        self.logger = logging.getLogger(f"ai_employee.{name}")
    
    @property
    def employee_id(self) -> str:
        return self._employee_id
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def persona_system_prompt(self) -> str:
        return self._persona_system_prompt
    
    @property
    def is_active(self) -> bool:
        return self._is_active
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate for this employee."""
        if self._tasks_processed == 0:
            return 0.0
        return self._success_count / self._tasks_processed
    
    def activate(self) -> None:
        """Business operation: Activate employee."""
        if self._is_active:
            raise ValueError(f"Employee {self.name} is already active")
        
        self._is_active = True
        self._add_domain_event(EmployeeActivatedEvent(employee_id=self.employee_id))
    
    def deactivate(self) -> None:
        """Business operation: Deactivate employee."""
        if not self._is_active:
            raise ValueError(f"Employee {self.name} is already inactive")
        
        self._is_active = False
        self._add_domain_event(EmployeeDeactivatedEvent(employee_id=self.employee_id))
    
    def add_reaction(self, event_check: EventCheck, workflow_type: str, priority: int = 0) -> None:
        """Add a reaction pattern that maps to a LangGraph workflow."""
        reaction = EmployeeReaction(event_check, workflow_type, priority)
        self._reactions.append(reaction)
        # Sort by priority (highest first)
        self._reactions.sort(key=lambda r: r.priority, reverse=True)
        
        self.logger.debug(f"Added reaction: {workflow_type} with priority {priority}")
    
    def add_workflow(self, workflow_type: str, workflow: 'EmployeeWorkflowGraph') -> None:
        """Register a LangGraph workflow for this employee."""
        self._workflows[workflow_type] = workflow
        self.logger.debug(f"Registered workflow: {workflow_type}")
    
    def can_handle_task_type(self, task: NotionTask) -> bool:
        """Check if employee can handle this type of task (via EventCheck system)."""
        if not self._is_active:
            self.logger.debug(f"Employee {self.name} is inactive")
            return False
        
        # Must be assigned AND pass at least one EventCheck
        if not task.is_assigned_to_employee(self.name):
            self.logger.debug(f"Task {task.notion_id} not assigned to {self.name}")
            return False
        
        has_matching_reaction = any(reaction.event_check.matches(task, self) for reaction in self._reactions)
        if not has_matching_reaction:
            self.logger.debug(f"No matching reactions for task {task.notion_id}")
        
        return has_matching_reaction
    
    def get_applicable_workflow(self, task: NotionTask) -> Optional['EmployeeWorkflowGraph']:
        """Get the workflow that should handle this task."""
        for reaction in self._reactions:  # Already sorted by priority
            if reaction.event_check.matches(task, self):
                workflow = self._workflows.get(reaction.workflow_type)
                if workflow:
                    self.logger.debug(f"Selected workflow {reaction.workflow_type} for task {task.notion_id}")
                    return workflow
                else:
                    self.logger.warning(f"Workflow {reaction.workflow_type} not registered for employee {self.name}")
        return None
    
    def get_available_workflow_types(self) -> List[str]:
        """Get list of available workflow types for this employee."""
        return list(self._workflows.keys())
    
    async def process_task(self, task: NotionTask) -> TaskProcessingResult:
        """Main business operation: Process assigned task if capable."""
        
        # Validate assignment
        if not task.is_assigned_to_employee(self.name):
            raise ValueError(f"Task {task.notion_id} is not assigned to {self.name}")
        
        # Validate capability
        if not self.can_handle_task_type(task):
            raise ValueError(f"Employee {self.name} cannot handle task type for {task.notion_id}")
        
        # Get appropriate workflow
        workflow = self.get_applicable_workflow(task)
        if not workflow:
            raise ValueError(f"No workflow available for task {task.notion_id}")
        
        self.logger.info(f"Processing task {task.title} with workflow {workflow.workflow_type}")
        
        start_time = datetime.utcnow()
        try:
            result = await workflow.execute(task, self)
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            
            # Update performance tracking
            self._tasks_processed += 1
            if result.success:
                self._success_count += 1
            self._last_activity = datetime.utcnow()
            
            # Add execution time to result
            result.execution_time = execution_time
            
            self._add_domain_event(TaskProcessedEvent(
                employee_id=self.employee_id,
                task_id=task.notion_id,
                result_summary=f"Processed with {workflow.workflow_type}: {result.success}"
            ))
            
            self.logger.info(f"Successfully processed task {task.notion_id} in {execution_time:.2f}s")
            return result
            
        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            self._tasks_processed += 1
            self._last_activity = datetime.utcnow()
            
            error_msg = str(e)
            self.logger.error(f"Failed to process task {task.notion_id}: {error_msg}")
            
            self._add_domain_event(TaskProcessingFailedEvent(
                employee_id=self.employee_id,
                task_id=task.notion_id,
                error_message=error_msg
            ))
            
            # Return failed result instead of raising
            return TaskProcessingResult(
                task_id=task.notion_id,
                employee_id=self.employee_id,
                workflow_type=workflow.workflow_type if workflow else "unknown",
                success=False,
                results=[],
                errors=[error_msg],
                execution_time=execution_time
            )
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for this employee."""
        return {
            "employee_id": self.employee_id,
            "name": self.name,
            "is_active": self.is_active,
            "tasks_processed": self._tasks_processed,
            "success_count": self._success_count,
            "success_rate": self.success_rate,
            "last_activity": self._last_activity.isoformat() if self._last_activity else None,
            "available_workflows": self.get_available_workflow_types()
        }
    
    def _add_domain_event(self, event: Event) -> None:
        """Add domain event for publishing."""
        self._domain_events.append(event)
    
    def get_domain_events(self) -> List[Event]:
        """Get and clear domain events."""
        events = self._domain_events.copy()
        self._domain_events.clear()
        return events
    
    def __str__(self) -> str:
        return f"ArtificialEmployee({self.name}, active={self.is_active}, workflows={len(self._workflows)})"
    
    def __repr__(self) -> str:
        return self.__str__()


class EmployeeRegistry:
    """Registry for managing AI employees."""
    
    def __init__(self):
        self._employees: Dict[str, ArtificialEmployee] = {}
        self._employees_by_name: Dict[str, ArtificialEmployee] = {}
        self.logger = logging.getLogger(__name__)
    
    def register_employee(self, employee: ArtificialEmployee) -> None:
        """Register an AI employee."""
        if employee.employee_id in self._employees:
            raise ValueError(f"Employee with ID {employee.employee_id} already registered")
        
        if employee.name.lower() in self._employees_by_name:
            raise ValueError(f"Employee with name {employee.name} already registered")
        
        self._employees[employee.employee_id] = employee
        self._employees_by_name[employee.name.lower()] = employee
        
        self.logger.info(f"Registered employee: {employee.name} ({employee.employee_id})")
    
    def get_employee(self, employee_id: str) -> Optional[ArtificialEmployee]:
        """Get employee by ID."""
        return self._employees.get(employee_id)
    
    def get_employee_by_name(self, name: str) -> Optional[ArtificialEmployee]:
        """Get employee by name (case-insensitive)."""
        return self._employees_by_name.get(name.lower())
    
    def get_all_employees(self) -> List[ArtificialEmployee]:
        """Get all registered employees."""
        return list(self._employees.values())
    
    def get_active_employees(self) -> List[ArtificialEmployee]:
        """Get all active employees."""
        return [emp for emp in self._employees.values() if emp.is_active]
    
    def remove_employee(self, employee_id: str) -> bool:
        """Remove an employee from the registry."""
        employee = self._employees.get(employee_id)
        if not employee:
            return False
        
        del self._employees[employee_id]
        del self._employees_by_name[employee.name.lower()]
        
        self.logger.info(f"Removed employee: {employee.name} ({employee_id})")
        return True
    
    def get_employees_for_task(self, task: NotionTask) -> List[ArtificialEmployee]:
        """Get all employees that can handle the given task."""
        candidates = []
        
        for employee in self.get_active_employees():
            if employee.can_handle_task_type(task):
                candidates.append(employee)
        
        return candidates
    
    def get_registry_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        employees = self.get_all_employees()
        active_employees = self.get_active_employees()
        
        return {
            "total_employees": len(employees),
            "active_employees": len(active_employees),
            "inactive_employees": len(employees) - len(active_employees),
            "employees": [emp.get_performance_stats() for emp in employees]
        }