# AI Kanban System - Domain Driven Architecture Specification v2 (Corrected)

## Overview

This document specifies a redesigned AI Kanban system using Domain Driven Design (DDD) principles with LangGraph for AI agent workflow orchestration. The system routes tasks to AI employees based on the "AI Employee" column assignment, validates capability through EventCheck patterns, then executes sophisticated workflows.

## Core Flow

```
Notion Task (AI Employee = "ResearchAgent")
    ↓
Task Assignment Service finds employee by name
    ↓
EventCheck validates employee can handle task type
    ↓
LangGraph workflow executes the task
    ↓
Result posted back to Notion
```

## Domain Model (DDD-Compliant)

### Core Domain Entities

#### 1. Event (Base Domain Event)

```python
from abc import ABC
from datetime import datetime
from typing import Dict, Any
from dataclasses import dataclass
from uuid import UUID, uuid4

@dataclass
class Event(ABC):
    """Base domain event - immutable record of something that happened."""
    event_id: UUID
    timestamp: datetime
    metadata: Dict[str, Any]
    
    def __post_init__(self):
        object.__setattr__(self, 'event_id', self.event_id or uuid4())
        object.__setattr__(self, 'timestamp', self.timestamp or datetime.utcnow())
        object.__setattr__(self, 'metadata', self.metadata or {})
```

#### 2. NotionTask (Domain Event)

```python
from enum import Enum
from typing import Optional

class TaskStatus(Enum):
    TO_DO = "To Do"
    IN_PROGRESS = "In Progress" 
    DONE = "Done"
    CANCELLED = "Cancelled"

@dataclass(frozen=True)
class NotionTask(Event):
    """Domain event representing a task from Notion with AI employee assignment."""
    
    # Core task properties
    notion_id: str
    title: str
    status: TaskStatus
    description: str
    content: str
    
    # Assignment and ownership (KEY: AI Employee column value)
    ai_employee: Optional[str]  # This drives task routing
    assigned_to: Optional[str]
    created_by: str
    
    # Integration fields
    github_url: Optional[str]
    
    # Notion metadata
    notion_url: str
    last_edited_time: datetime
    created_time: datetime
    
    def __post_init__(self):
        super().__post_init__()
        # Business invariants
        if not self.notion_id:
            raise ValueError("NotionTask must have notion_id")
        if not self.title.strip():
            raise ValueError("NotionTask must have non-empty title")
        if not self.created_by:
            raise ValueError("NotionTask must have created_by")
    
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
```

### Domain Services

#### 1. Memory Repository (Repository Pattern)

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any

class MemoryRepository(ABC):
    """Repository for AI employee memory persistence."""
    
    @abstractmethod
    async def store_memory(self, employee_name: str, memory_text: str, 
                          metadata: Dict[str, Any] = None) -> None:
        pass
    
    @abstractmethod
    async def get_memories(self, employee_name: str, query: str, limit: int = 10) -> List[str]:
        pass

class VectorMemoryRepository(MemoryRepository):
    """Concrete implementation using vector database."""
    
    def __init__(self, vector_db_connection):
        self.vector_db = vector_db_connection
    
    async def store_memory(self, employee_name: str, memory_text: str, 
                          metadata: Dict[str, Any] = None) -> None:
        # Vector DB implementation
        pass
    
    async def get_memories(self, employee_name: str, query: str, limit: int = 10) -> List[str]:
        # Semantic search implementation
        pass
```

#### 2. Task Assignment Service (Domain Service)

```python
class TaskAssignmentService:
    """Domain service for task assignment based on AI Employee column."""
    
    def __init__(self, employee_registry: 'EmployeeRegistry'):
        self.employee_registry = employee_registry
    
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
        """Validate the complete assignment chain."""
        if not task.can_be_processed():
            return False
        
        employee = self.find_assigned_employee(task)
        if not employee:
            return False
        
        return self.can_employee_handle_task(employee, task)
```

### EventCheck System (Preserved and Enhanced)

```python
from abc import ABC, abstractmethod
from typing import List

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

class CompositeCheck(EventCheck):
    """Combine multiple checks with AND/OR logic."""
    
    def __init__(self, checks: List[EventCheck], operator: str = "AND"):
        self.checks = checks
        self.operator = operator.upper()
    
    def matches(self, event: Event, employee: 'ArtificialEmployee') -> bool:
        if self.operator == "AND":
            return all(check.matches(event, employee) for check in self.checks)
        elif self.operator == "OR":
            return any(check.matches(event, employee) for check in self.checks)
        else:
            raise ValueError(f"Unsupported operator: {self.operator}")
```

### Access and Action Framework

```python
from enum import Enum
from abc import ABC, abstractmethod

class Access(Enum):
    NOTION_READ = "notion_read"
    NOTION_WRITE = "notion_write"
    GITHUB_READ = "github_read"
    GITHUB_WRITE = "github_write"
    INTERNET_ACCESS = "internet_access"
    EXCALIDRAW_GENERATION = "excalidraw_generation"

class ArtificialEmployeeAction(ABC):
    """Abstract base class for actions that AI employees can perform."""
    
    def __init__(self, action_system_prompt: str, requires: List[Access] = None):
        self.action_system_prompt = action_system_prompt
        self.requires = requires or []
    
    @abstractmethod
    def get_action_name(self) -> str:
        """Get the human-readable name of this action."""
        pass
```

### Aggregate Root: ArtificialEmployee

```python
from typing import Optional, List
import logging

@dataclass
class EmployeeReaction:
    """Represents a condition-action pair for an AI employee."""
    event_check: EventCheck
    workflow_type: str  # Maps to LangGraph workflow
    priority: int = 0

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
    
    def add_reaction(self, event_check: EventCheck, workflow_type: str, priority: int = 0) -> None:
        """Add a reaction pattern that maps to a LangGraph workflow."""
        reaction = EmployeeReaction(event_check, workflow_type, priority)
        self._reactions.append(reaction)
        # Sort by priority (highest first)
        self._reactions.sort(key=lambda r: r.priority, reverse=True)
    
    def add_workflow(self, workflow_type: str, workflow: 'EmployeeWorkflowGraph') -> None:
        """Register a LangGraph workflow for this employee."""
        self._workflows[workflow_type] = workflow
    
    def can_handle_task_type(self, task: NotionTask) -> bool:
        """Check if employee can handle this type of task (via EventCheck system)."""
        if not self._is_active:
            return False
        
        # Must be assigned AND pass at least one EventCheck
        if not task.is_assigned_to_employee(self.name):
            return False
        
        return any(reaction.event_check.matches(task, self) for reaction in self._reactions)
    
    def get_applicable_workflow(self, task: NotionTask) -> Optional['EmployeeWorkflowGraph']:
        """Get the workflow that should handle this task."""
        for reaction in self._reactions:
            if reaction.event_check.matches(task, self):
                workflow = self._workflows.get(reaction.workflow_type)
                if workflow:
                    return workflow
        return None
    
    async def process_task(self, task: NotionTask) -> 'TaskProcessingResult':
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
        
        try:
            result = await workflow.execute(task, self)
            self._add_domain_event(TaskProcessedEvent(self.employee_id, task.notion_id, result))
            return result
        except Exception as e:
            self.logger.error(f"Failed to process task {task.notion_id}: {e}")
            self._add_domain_event(TaskProcessingFailedEvent(self.employee_id, task.notion_id, str(e)))
            raise
    
    def _add_domain_event(self, event: Event) -> None:
        self._domain_events.append(event)
    
    def get_domain_events(self) -> List[Event]:
        events = self._domain_events.copy()
        self._domain_events.clear()
        return events
```

## LangGraph Workflow Integration

### Employee Workflow Graph

```python
from langgraph import StateGraph, END
from langgraph.prebuilt import ToolExecutor
from typing import TypedDict, Dict

class WorkflowState(TypedDict):
    """State passed through the workflow graph."""
    task: NotionTask
    employee: ArtificialEmployee
    results: List[str]
    errors: List[str]
    context: Dict[str, Any]
    retry_count: int

class EmployeeWorkflowGraph:
    """LangGraph-based workflow for specific employee task types."""
    
    def __init__(self, workflow_type: str, memory_repository: MemoryRepository,
                 tool_executor: ToolExecutor):
        self.workflow_type = workflow_type
        self.memory_repository = memory_repository
        self.tool_executor = tool_executor
        self.graph = self._build_workflow_graph()
    
    def _build_workflow_graph(self) -> StateGraph:
        """Build workflow graph based on type."""
        workflow = StateGraph(WorkflowState)
        
        # Common nodes
        workflow.add_node("gather_context", self._gather_context)
        workflow.add_node("execute_llm_action", self._execute_llm_action)
        workflow.add_node("validate_result", self._validate_result)
        workflow.add_node("store_memory", self._store_memory)
        workflow.add_node("handle_error", self._handle_error)
        
        # Workflow-specific nodes and edges
        if self.workflow_type == "specification":
            self._add_specification_workflow(workflow)
        elif self.workflow_type == "research":
            self._add_research_workflow(workflow)
        elif self.workflow_type == "documentation":
            self._add_documentation_workflow(workflow)
        
        return workflow.compile()
    
    def _add_specification_workflow(self, workflow: StateGraph):
        """Engineering Manager specification workflow."""
        # Entry point
        workflow.set_entry_point("gather_context")
        
        # Linear flow with retry capability
        workflow.add_edge("gather_context", "execute_llm_action")
        
        workflow.add_conditional_edges(
            "execute_llm_action",
            self._should_retry_action,
            {
                "retry": "gather_context",
                "validate": "validate_result",
                "error": "handle_error"
            }
        )
        
        workflow.add_conditional_edges(
            "validate_result",
            self._is_spec_complete,
            {
                "complete": "store_memory",
                "incomplete": "execute_llm_action",
                "error": "handle_error"
            }
        )
        
        workflow.add_edge("store_memory", END)
        workflow.add_edge("handle_error", END)
    
    def _add_research_workflow(self, workflow: StateGraph):
        """Research Agent workflow with web search."""
        workflow.add_node("search_web", self._search_web)
        workflow.add_node("analyze_sources", self._analyze_sources)
        
        workflow.set_entry_point("gather_context")
        workflow.add_edge("gather_context", "search_web")
        workflow.add_edge("search_web", "analyze_sources")
        workflow.add_edge("analyze_sources", "execute_llm_action")
        
        workflow.add_conditional_edges(
            "execute_llm_action",
            self._needs_more_research,
            {
                "continue": "search_web",
                "validate": "validate_result",
                "error": "handle_error"
            }
        )
        
        workflow.add_edge("validate_result", "store_memory")
        workflow.add_edge("store_memory", END)
        workflow.add_edge("handle_error", END)
    
    def _add_documentation_workflow(self, workflow: StateGraph):
        """Documentation Specialist workflow with diagram generation."""
        workflow.add_node("analyze_code", self._analyze_code)
        workflow.add_node("generate_diagrams", self._generate_diagrams)
        
        workflow.set_entry_point("gather_context")
        workflow.add_edge("gather_context", "analyze_code")
        workflow.add_edge("analyze_code", "execute_llm_action")
        
        workflow.add_conditional_edges(
            "execute_llm_action",
            self._needs_diagrams,
            {
                "generate": "generate_diagrams",
                "validate": "validate_result",
                "error": "handle_error"
            }
        )
        
        workflow.add_edge("generate_diagrams", "validate_result")
        workflow.add_edge("validate_result", "store_memory")
        workflow.add_edge("store_memory", END)
        workflow.add_edge("handle_error", END)
    
    async def execute(self, task: NotionTask, employee: ArtificialEmployee) -> 'TaskProcessingResult':
        """Execute the workflow for the given task."""
        initial_state = WorkflowState(
            task=task,
            employee=employee,
            results=[],
            errors=[],
            context={},
            retry_count=0
        )
        
        final_state = await self.graph.ainvoke(initial_state)
        
        return TaskProcessingResult(
            task_id=task.notion_id,
            employee_id=employee.employee_id,
            workflow_type=self.workflow_type,
            success=len(final_state["errors"]) == 0,
            results=final_state["results"],
            errors=final_state["errors"]
        )
    
    # Workflow implementation methods
    async def _gather_context(self, state: WorkflowState) -> WorkflowState:
        """Gather memories and context for the task."""
        employee = state["employee"]
        task = state["task"]
        
        query = f"{task.title} {task.description}"
        memories = await self.memory_repository.get_memories(employee.name, query, limit=5)
        
        state["context"]["memories"] = memories
        return state
    
    async def _execute_llm_action(self, state: WorkflowState) -> WorkflowState:
        """Execute main LLM action with employee persona and workflow-specific prompt."""
        employee = state["employee"]
        task = state["task"]
        context = state["context"]
        
        # Build composite prompt
        prompt = self._build_composite_prompt(employee, task, context)
        
        try:
            # Execute with tools via tool executor
            result = await self._call_llm_with_tools(prompt, state)
            state["results"].append(result)
        except Exception as e:
            state["errors"].append(str(e))
        
        return state
    
    def _build_composite_prompt(self, employee: ArtificialEmployee, task: NotionTask, 
                               context: Dict[str, Any]) -> str:
        """Build the complete prompt combining persona and action instructions."""
        
        # Get workflow-specific action prompt
        action_prompt = self._get_action_prompt_for_workflow()
        
        # Build memories section
        memories_section = ""
        if context.get("memories"):
            memories_section = f"""
## Relevant Memories
These are relevant memories from your previous work:
{chr(10).join(f"- {memory}" for memory in context["memories"])}
"""
        
        return f"""{employee.persona_system_prompt}

{action_prompt}

## Task Details
Title: {task.title}
Description: {task.description}
Content: {task.content}
GitHub: {task.github_url or 'Not specified'}

{memories_section}

Provide your response:"""
    
    def _get_action_prompt_for_workflow(self) -> str:
        """Get workflow-specific action instructions."""
        if self.workflow_type == "specification":
            return """
Create a detailed technical specification including:
- Clear problem statement
- Functional requirements
- Non-functional requirements
- Technical approach and architecture
- Implementation milestones
- Success criteria
"""
        elif self.workflow_type == "research":
            return """
Conduct thorough research and provide:
- Key findings from multiple sources
- Analysis and synthesis of information
- Actionable recommendations
- Proper source citations
"""
        elif self.workflow_type == "documentation":
            return """
Create comprehensive documentation including:
- Clear explanation of code functionality
- API documentation where applicable
- Usage examples
- Architecture diagrams using Excalidraw when helpful
"""
        return "Analyze and respond to the task appropriately."
```

## Employee Factory with Complete Setup

```python
class EmployeeFactory:
    """Factory for creating fully configured AI employees."""
    
    def __init__(self, memory_repository: MemoryRepository):
        self.memory_repository = memory_repository
    
    def create_engineering_manager(self) -> ArtificialEmployee:
        """Create Engineering Manager with specification capabilities."""
        
        employee = ArtificialEmployee(
            employee_id="eng_mgr_001",
            name="EngineeringManager",
            persona_system_prompt="""
            You are a Senior Engineering Manager with 10+ years of experience.
            You excel at breaking down complex problems into clear, actionable specifications.
            You consider scalability, maintainability, and team capabilities.
            """,
            memory_repository=self.memory_repository
        )
        
        # Add reaction: Assigned + specification keywords → specification workflow
        employee.add_reaction(
            CompositeCheck([
                AssignmentCheck(),  # Must be assigned to this employee
                KeywordCheck(["specification", "requirements", "architecture", "design"])
            ], "AND"),
            workflow_type="specification",
            priority=10
        )
        
        # Create and add workflow
        tool_executor = create_tool_executor(["notion_write", "github_read"])
        spec_workflow = EmployeeWorkflowGraph("specification", self.memory_repository, tool_executor)
        employee.add_workflow("specification", spec_workflow)
        
        return employee
    
    def create_research_agent(self) -> ArtificialEmployee:
        """Create Research Agent with investigation capabilities."""
        
        employee = ArtificialEmployee(
            employee_id="research_001",
            name="ResearchAgent",
            persona_system_prompt="""
            You are a Research Specialist with expertise in gathering and analyzing information.
            You excel at finding credible sources and synthesizing complex information.
            You present findings objectively with actionable recommendations.
            """,
            memory_repository=self.memory_repository
        )
        
        # Add reaction: Assigned + research keywords → research workflow
        employee.add_reaction(
            CompositeCheck([
                AssignmentCheck(),
                KeywordCheck(["research", "investigate", "analyze", "study", "explore"])
            ], "AND"),
            workflow_type="research",
            priority=10
        )
        
        # Create and add workflow
        tool_executor = create_tool_executor(["notion_write", "internet_access"])
        research_workflow = EmployeeWorkflowGraph("research", self.memory_repository, tool_executor)
        employee.add_workflow("research", research_workflow)
        
        return employee
    
    def create_documentation_specialist(self) -> ArtificialEmployee:
        """Create Documentation Specialist with documentation capabilities."""
        
        employee = ArtificialEmployee(
            employee_id="doc_spec_001",
            name="DocSpecialist",
            persona_system_prompt="""
            You are a Technical Documentation Specialist who creates clear documentation.
            You excel at explaining complex code in simple terms.
            You create visual diagrams to illustrate architecture and data flow.
            """,
            memory_repository=self.memory_repository
        )
        
        # Add reaction: Assigned + documentation/code keywords → documentation workflow
        employee.add_reaction(
            CompositeCheck([
                AssignmentCheck(),
                KeywordCheck(["documentation", "document", "code", "python", "```", "readme"])
            ], "AND"),
            workflow_type="documentation",
            priority=10
        )
        
        # Create and add workflow
        tool_executor = create_tool_executor(["notion_write", "excalidraw_generation", "github_read"])
        doc_workflow = EmployeeWorkflowGraph("documentation", self.memory_repository, tool_executor)
        employee.add_workflow("documentation", doc_workflow)
        
        return employee
```

## Complete System Flow

```
1. Notion Task Created (AI Employee = "ResearchAgent")
    ↓
2. Task Monitor publishes NotionTask event to RabbitMQ
    ↓
3. Employee Consumer receives event
    ↓
4. TaskAssignmentService.find_assigned_employee("ResearchAgent")
    ↓
5. ResearchAgent.can_handle_task_type(task) 
   → Checks: AssignmentCheck + KeywordCheck
    ↓
6. If true: ResearchAgent.process_task(task)
    ↓
7. Gets "research" workflow from reactions
    ↓
8. LangGraph executes: gather_context → search_web → analyze_sources → execute_llm_action
    ↓
9. Result posted to Notion + stored in memory
```

This corrected architecture properly:
- Routes by AI Employee column assignment
- Validates capability through EventCheck patterns  
- Executes via LangGraph workflows
- Maintains DDD principles

<function_calls>
<invoke name="TodoWrite">
<parameter name="todos">[{"id": "1", "content": "Improve DDD compliance with Repository pattern and domain services", "status": "completed", "priority": "high"}, {"id": "2", "content": "Replace reaction system with LangGraph for workflow orchestration", "status": "completed", "priority": "high"}, {"id": "3", "content": "Update architecture specification document", "status": "completed", "priority": "high"}]