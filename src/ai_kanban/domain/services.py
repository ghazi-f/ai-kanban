"""Domain services for business logic that doesn't belong to a single entity."""

from typing import List, Optional, TYPE_CHECKING
import logging

from .events import NotionTask, TaskStatus
from .repositories import TaskRepository

if TYPE_CHECKING:
    from .artificial_employee import ArtificialEmployee, EmployeeRegistry


class TaskAssignmentService:
    """Domain service for task assignment based on AI Employee column."""
    
    def __init__(self, employee_registry: 'EmployeeRegistry'):
        self.employee_registry = employee_registry
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
    
    def find_assigned_employee(self, task: NotionTask) -> Optional['ArtificialEmployee']:
        """Find the employee assigned via AI Employee column."""
        if not task.has_ai_employee_assigned():
            return None
        
        return self.employee_registry.get_employee_by_name(task.ai_employee)
    
    def can_employee_handle_task(self, employee: 'ArtificialEmployee', task: NotionTask) -> bool:
        """Check if assigned employee can actually handle the task type."""
        if not task.is_assigned_to_employee(employee.name):
            return False
        
        # Use EventCheck system to validate capability
        return employee.can_handle_task_type(task)
    
    def validate_assignment(self, task: NotionTask) -> bool:
        """Validate the complete assignment chain with detailed error reporting."""
        
        # Check if task can be processed at all
        if not task.can_be_processed():
            reasons = []
            if not task.has_ai_employee_assigned():
                reasons.append(f"No AI Employee assigned (current value: '{task.ai_employee}')")
            if task.status not in ["To Do", "In Progress"]:
                reasons.append(f"Invalid status for processing (current: '{task.status}', expected: 'To Do' or 'In Progress')")
            if not task.title or len(task.title.strip()) == 0:
                reasons.append("Task has no title")
            
            self.logger.warning(f"Task {task.notion_id} '{task.title}' cannot be processed: {', '.join(reasons)}")
            return False
        
        # Check if assigned employee exists
        employee = self.find_assigned_employee(task)
        if not employee:
            available_employees = [emp.name for emp in self.employee_registry.get_active_employees()]
            self.logger.warning(f"No employee found for assignment '{task.ai_employee}' on task {task.notion_id} '{task.title}'. Available employees: {available_employees}")
            return False
        
        # Check if employee can handle this task type
        can_handle = self.can_employee_handle_task(employee, task)
        if not can_handle:
            # Get detailed capability information
            reactions = employee.get_available_workflow_types()
            failure_reasons = self._analyze_capability_failure(employee, task)
            
            self.logger.warning(f"Employee '{employee.name}' cannot handle task {task.notion_id} '{task.title}'. "
                              f"Employee capabilities: {reactions}. "
                              f"Failure reasons: {failure_reasons}")
        
        return can_handle
    
    def _analyze_capability_failure(self, employee: 'ArtificialEmployee', task: NotionTask) -> str:
        """Analyze why an employee cannot handle a task and provide detailed feedback."""
        failure_reasons = []
        
        # Check if employee is active
        if not employee.is_active:
            failure_reasons.append("Employee is inactive")
        
        # Analyze each reaction/capability
        for reaction in employee.reactions:
            check_result = reaction.event_check.matches(task, employee)
            if not check_result:
                # Analyze specific check failures
                check_details = self._analyze_check_failure(reaction.event_check, task, employee)
                failure_reasons.append(f"Reaction '{reaction.workflow_type}' failed: {check_details}")
        
        if not failure_reasons:
            failure_reasons.append("No matching reactions found for this task type")
        
        return "; ".join(failure_reasons)
    
    def _analyze_check_failure(self, event_check, task: NotionTask, employee: 'ArtificialEmployee') -> str:
        """Analyze why a specific EventCheck failed."""
        from .event_checks import AssignmentCheck, KeywordCheck, CompositeCheck, StatusCheck, ContentLengthCheck
        
        if isinstance(event_check, AssignmentCheck):
            if not task.is_assigned_to_employee(employee.name):
                return f"Task not assigned to {employee.name} (assigned to: '{task.ai_employee}')"
            return "Assignment check passed but overall check failed"
        
        elif isinstance(event_check, KeywordCheck):
            search_text = f"{task.title} {task.description} {task.content}".lower()
            matched_keywords = [kw for kw in event_check.keywords if kw.lower() in search_text]
            missing_keywords = [kw for kw in event_check.keywords if kw.lower() not in search_text]
            return f"Missing keywords: {missing_keywords} (found: {matched_keywords}, searched in: title='{task.title}', description='{task.description[:50]}...', content length={len(task.content or '')})"
        
        elif isinstance(event_check, StatusCheck):
            return f"Status '{task.status}' not in required statuses: {event_check.required_statuses}"
        
        elif isinstance(event_check, ContentLengthCheck):
            content_length = len(f"{task.title} {task.description} {task.content}".strip())
            return f"Content too short: {content_length} chars < {event_check.min_length} required"
        
        elif isinstance(event_check, CompositeCheck):
            sub_failures = []
            for sub_check in event_check.checks:
                if not sub_check.matches(task, employee):
                    sub_detail = self._analyze_check_failure(sub_check, task, employee)
                    sub_failures.append(f"{sub_check.__class__.__name__}: {sub_detail}")
            
            return f"Composite {event_check.operator} failed: [{'; '.join(sub_failures)}]"
        
        return f"Unknown check type: {type(event_check).__name__}"
    
    def get_processing_candidates(self, task: NotionTask) -> List['ArtificialEmployee']:
        """Get all employees that could potentially process this task."""
        candidates = []
        
        # Primary candidate: assigned employee
        assigned_employee = self.find_assigned_employee(task)
        if assigned_employee and self.can_employee_handle_task(assigned_employee, task):
            candidates.append(assigned_employee)
        
        return candidates


class TaskStatusService:
    """Domain service for managing task status transitions."""
    
    def __init__(self, task_repository: TaskRepository):
        self.task_repository = task_repository
        self.logger = logging.getLogger(__name__)
    
    async def transition_to_in_progress(self, task: NotionTask) -> bool:
        """Transition task to In Progress status."""
        current_status = self._normalize_status(task.status)
        
        if current_status == TaskStatus.IN_PROGRESS.value:
            return True
        
        if current_status not in [TaskStatus.TO_DO.value]:
            self.logger.warning(f"Invalid status transition: {task.status} -> IN_PROGRESS for task {task.notion_id}")
            return False
        
        success = await self.task_repository.update_task_status(task.notion_id, TaskStatus.IN_PROGRESS.value)
        if success:
            self.logger.info(f"Task {task.notion_id} transitioned to In Progress")
        return success
    
    async def transition_to_done(self, task: NotionTask) -> bool:
        """Transition task to Done status."""
        current_status = self._normalize_status(task.status)
        
        if current_status == TaskStatus.DONE.value:
            return True
        
        if current_status not in [TaskStatus.IN_PROGRESS.value]:
            self.logger.warning(f"Invalid status transition: {task.status} -> DONE for task {task.notion_id}")
            return False
        
        success = await self.task_repository.update_task_status(task.notion_id, TaskStatus.DONE.value)
        if success:
            self.logger.info(f"Task {task.notion_id} transitioned to Done")
        return success
    
    def _normalize_status(self, status) -> str:
        """Normalize status to string value, handling both enum and string inputs."""
        if isinstance(status, TaskStatus):
            return status.value
        return str(status)
    
    async def revert_to_todo(self, task: NotionTask) -> bool:
        """Revert task back to To Do status (on failure)."""
        success = await self.task_repository.update_task_status(task.notion_id, TaskStatus.TO_DO.value)
        if success:
            self.logger.info(f"Task {task.notion_id} reverted to To Do")
        return success
    
class TaskContentService:
    """Domain service for extracting and managing task content."""
    
    def __init__(self, task_repository: TaskRepository):
        self.task_repository = task_repository
    
    async def get_full_task_content(self, task: NotionTask) -> str:
        """Get the complete content of a task including page content."""
        # If we already have content, use it
        if task.content:
            return task.content
        
        # Otherwise, fetch from repository
        content = await self.task_repository.get_task_content(task.notion_id)
        return content or ""
    