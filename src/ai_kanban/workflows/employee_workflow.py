"""LangGraph workflow implementation for AI employees."""

import json
import time
from typing import Dict, List, Any, Optional, TypedDict, TYPE_CHECKING
from datetime import datetime
import logging

from langgraph.graph import StateGraph, END
from langchain_anthropic import ChatAnthropic

from ..domain.events import NotionTask
from ..domain.artificial_employee import TaskProcessingResult
from ..domain.repositories import MemoryRepository

if TYPE_CHECKING:
    from ..domain.artificial_employee import ArtificialEmployee


class WorkflowState(TypedDict):
    """State passed through the workflow graph."""
    task: NotionTask
    employee: Any  # ArtificialEmployee reference
    results: List[str]
    errors: List[str]
    context: Dict[str, Any]
    retry_count: int
    current_step: str
    final_response: str


class EmployeeWorkflowGraph:
    """LangGraph-based workflow for specific employee task types."""
    
    def __init__(self, workflow_type: str, memory_repository: MemoryRepository):
        self.workflow_type = workflow_type
        self.memory_repository = memory_repository
        self.logger = logging.getLogger(f"workflow.{workflow_type}")
        
        # Initialize LLM
        self.llm = ChatAnthropic(
            model="claude-3-5-sonnet-20241022",
            temperature=0.7,
            max_tokens=2000
        )
        
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
        workflow.add_node("finalize_result", self._finalize_result)
        
        # Workflow-specific nodes and edges
        if self.workflow_type == "specification":
            self._add_specification_workflow(workflow)
        elif self.workflow_type == "research":
            self._add_research_workflow(workflow)
        elif self.workflow_type == "documentation":
            self._add_documentation_workflow(workflow)
        else:
            self._add_default_workflow(workflow)
        
        return workflow.compile()
    
    def _add_specification_workflow(self, workflow: StateGraph):
        """Engineering Manager specification workflow."""
        workflow.set_entry_point("gather_context")
        
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
        
        workflow.add_edge("store_memory", "finalize_result")
        workflow.add_edge("finalize_result", END)
        workflow.add_edge("handle_error", END)
    
    def _add_research_workflow(self, workflow: StateGraph):
        """Research Agent workflow."""
        workflow.add_node("analyze_research_scope", self._analyze_research_scope)
        
        workflow.set_entry_point("gather_context")
        workflow.add_edge("gather_context", "analyze_research_scope")
        workflow.add_edge("analyze_research_scope", "execute_llm_action")
        
        workflow.add_conditional_edges(
            "execute_llm_action",
            self._needs_more_research,
            {
                "continue": "analyze_research_scope",
                "validate": "validate_result",
                "error": "handle_error"
            }
        )
        
        workflow.add_edge("validate_result", "store_memory")
        workflow.add_edge("store_memory", "finalize_result")
        workflow.add_edge("finalize_result", END)
        workflow.add_edge("handle_error", END)
    
    def _add_documentation_workflow(self, workflow: StateGraph):
        """Documentation Specialist workflow."""
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
        workflow.add_edge("store_memory", "finalize_result")
        workflow.add_edge("finalize_result", END)
        workflow.add_edge("handle_error", END)
    
    def _add_default_workflow(self, workflow: StateGraph):
        """Default workflow for unspecified types."""
        workflow.set_entry_point("gather_context")
        workflow.add_edge("gather_context", "execute_llm_action")
        workflow.add_edge("execute_llm_action", "validate_result")
        workflow.add_edge("validate_result", "store_memory")
        workflow.add_edge("store_memory", "finalize_result")
        workflow.add_edge("finalize_result", END)
        workflow.add_edge("handle_error", END)
    
    async def execute(self, task: NotionTask, employee: 'ArtificialEmployee') -> TaskProcessingResult:  # type: ignore
        """Execute the workflow for the given task."""
        start_time = time.time()
        
        initial_state = WorkflowState(
            task=task,
            employee=employee,
            results=[],
            errors=[],
            context={},
            retry_count=0,
            current_step="start",
            final_response=""
        )
        
        try:
            final_state = await self.graph.ainvoke(initial_state)
            execution_time = time.time() - start_time
            
            # Extract the final response
            final_response = final_state.get("final_response", "")
            if not final_response and final_state["results"]:
                final_response = final_state["results"][-1]
            
            return TaskProcessingResult(
                task_id=task.notion_id,
                employee_id=employee.employee_id,
                workflow_type=self.workflow_type,
                success=len(final_state["errors"]) == 0 and bool(final_response),
                results=[final_response] if final_response else [],
                errors=final_state["errors"],
                execution_time=execution_time,
                model_used="claude-3-5-sonnet-20241022"
            )
        
        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(f"Workflow execution failed: {e}")
            
            return TaskProcessingResult(
                task_id=task.notion_id,
                employee_id=employee.employee_id,
                workflow_type=self.workflow_type,
                success=False,
                results=[],
                errors=[str(e)],
                execution_time=execution_time,
                model_used="claude-3-5-sonnet-20241022"
            )
    
    # Workflow node implementations
    async def _gather_context(self, state: WorkflowState) -> WorkflowState:
        """Gather memories and context for the task."""
        employee = state["employee"]
        task = state["task"]
        
        try:
            query = f"{task.title} {task.description}"
            memories = await self.memory_repository.get_memories(employee.name, query, limit=5)
            
            state["context"]["memories"] = memories
            state["current_step"] = "context_gathered"
            
            self.logger.debug(f"Gathered {len(memories)} memories for task {task.notion_id}")
        
        except Exception as e:
            self.logger.error(f"Error gathering context: {e}")
            state["errors"].append(f"Context gathering failed: {e}")
        
        return state
    
    async def _execute_llm_action(self, state: WorkflowState) -> WorkflowState:
        """Execute main LLM action with employee persona and workflow-specific prompt."""
        employee = state["employee"]
        task = state["task"]
        context = state["context"]
        
        try:
            # Build composite prompt
            prompt = self._build_composite_prompt(employee, task, context)
            
            # Call LLM
            response = await self.llm.ainvoke(prompt)
            
            # Extract response content
            result = response.content if hasattr(response, 'content') else str(response)
            
            state["results"].append(result)
            state["current_step"] = "action_executed"
            
            self.logger.info(f"LLM action completed for task {task.notion_id}")
        
        except Exception as e:
            error_msg = f"LLM action failed: {e}"
            self.logger.error(error_msg)
            state["errors"].append(error_msg)
            state["current_step"] = "action_failed"
        
        return state
    
    async def _validate_result(self, state: WorkflowState) -> WorkflowState:
        """Validate the LLM result."""
        if not state["results"]:
            state["errors"].append("No results to validate")
            return state
        
        result = state["results"][-1]
        
        # Basic validation - ensure result has minimum content
        if len(result.strip()) < 50:
            state["errors"].append("Result too short, may be incomplete")
        
        state["current_step"] = "result_validated"
        return state
    
    async def _store_memory(self, state: WorkflowState) -> WorkflowState:
        """Store the interaction in memory."""
        employee = state["employee"]
        task = state["task"]
        
        try:
            if state["results"]:
                result = state["results"][-1]
                memory_text = f"Processed task '{task.title}' with {self.workflow_type} workflow. Result: {result[:200]}..."
                
                await self.memory_repository.store_memory(
                    employee.name,
                    memory_text,
                    {
                        "task_id": task.notion_id,
                        "workflow_type": self.workflow_type,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )
                
                self.logger.debug(f"Stored memory for employee {employee.name}")
        
        except Exception as e:
            self.logger.error(f"Error storing memory: {e}")
            state["errors"].append(f"Memory storage failed: {e}")
        
        state["current_step"] = "memory_stored"
        return state
    
    async def _finalize_result(self, state: WorkflowState) -> WorkflowState:
        """Finalize the workflow result."""
        if state["results"]:
            state["final_response"] = state["results"][-1]
        
        state["current_step"] = "finalized"
        return state
    
    async def _handle_error(self, state: WorkflowState) -> WorkflowState:
        """Handle workflow errors."""
        self.logger.error(f"Workflow error in step {state['current_step']}: {state['errors']}")
        state["current_step"] = "error_handled"
        return state
    
    # Workflow-specific nodes
    async def _analyze_research_scope(self, state: WorkflowState) -> WorkflowState:
        """Analyze research scope for research workflow."""
        task = state["task"]
        
        # Extract research questions or topics
        research_scope = []
        if "?" in task.content:
            questions = [q.strip() for q in task.content.split("?") if q.strip()]
            research_scope.extend(questions)
        
        state["context"]["research_scope"] = research_scope
        state["current_step"] = "research_scope_analyzed"
        
        return state
    
    async def _analyze_code(self, state: WorkflowState) -> WorkflowState:
        """Analyze code for documentation workflow."""
        task = state["task"]
        
        # Extract code blocks
        import re
        code_blocks = re.findall(r'```[\s\S]*?```', task.content)
        
        state["context"]["code_blocks"] = code_blocks
        state["context"]["has_code"] = len(code_blocks) > 0
        state["current_step"] = "code_analyzed"
        
        return state
    
    async def _generate_diagrams(self, state: WorkflowState) -> WorkflowState:
        """Generate diagrams for documentation."""
        # For now, just add a note about diagram generation
        # This could be expanded to actually generate Excalidraw diagrams
        
        diagram_note = "\n\n## Architecture Diagram\n[Excalidraw diagram would be generated here based on the code structure]"
        
        if state["results"]:
            state["results"][-1] += diagram_note
        
        state["current_step"] = "diagrams_generated"
        return state
    
    # Conditional edge functions
    def _should_retry_action(self, state: WorkflowState) -> str:
        """Determine if action should be retried."""
        if state["errors"] and state["retry_count"] < 2:
            state["retry_count"] += 1
            return "retry"
        elif state["errors"]:
            return "error"
        else:
            return "validate"
    
    def _is_spec_complete(self, state: WorkflowState) -> str:
        """Validate if the specification is complete."""
        if not state["results"]:
            return "incomplete"
        
        result = state["results"][-1].lower()
        required_sections = ["requirements", "approach", "implementation"]
        
        if all(section in result for section in required_sections):
            return "complete"
        elif state["retry_count"] >= 2:
            return "error"
        else:
            return "incomplete"
    
    def _needs_more_research(self, state: WorkflowState) -> str:
        """Determine if more research is needed."""
        if state["retry_count"] >= 1:  # Limit research iterations
            return "validate"
        
        if state["results"]:
            result = state["results"][-1].lower()
            if len(result) < 500:  # If result is too short, might need more research
                state["retry_count"] += 1
                return "continue"
        
        return "validate"
    
    def _needs_diagrams(self, state: WorkflowState) -> str:
        """Determine if diagrams should be generated."""
        context = state["context"]
        if context.get("has_code", False):
            return "generate"
        return "validate"
    
    def _build_composite_prompt(self, employee, task: NotionTask, context: Dict[str, Any]) -> str:
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
        
        # Add workflow-specific context
        context_section = ""
        if self.workflow_type == "research" and context.get("research_scope"):
            context_section = f"""
## Research Scope
Focus on these specific questions/topics:
{chr(10).join(f"- {scope}" for scope in context["research_scope"])}
"""
        elif self.workflow_type == "documentation" and context.get("code_blocks"):
            context_section = f"""
## Code Analysis
Found {len(context["code_blocks"])} code blocks to document.
"""
        
        return f"""{employee.persona_system_prompt}

{action_prompt}

## Task Details
Title: {task.title}
Description: {task.description}
Content: {task.content}
GitHub: {task.github_url or 'Not specified'}

{context_section}

{memories_section}

Provide your response:"""
    
    def _get_action_prompt_for_workflow(self) -> str:
        """Get workflow-specific action instructions."""
        if self.workflow_type == "specification":
            return """
Create a detailed technical specification including:
- Clear problem statement and objectives
- Functional requirements (what the system should do)
- Non-functional requirements (performance, security, scalability)
- Technical approach and architecture overview
- Implementation milestones and timeline
- Success criteria and acceptance criteria
- Risk assessment and mitigation strategies

Format your response as a structured document with clear sections.
"""
        elif self.workflow_type == "research":
            return """
Conduct thorough research and provide:
- Executive summary of key findings
- Detailed analysis of the research topic
- Multiple perspectives and sources of information
- Data and evidence to support conclusions
- Actionable recommendations based on findings
- Proper citations and references
- Implications and next steps

Be comprehensive but focus on actionable insights.
"""
        elif self.workflow_type == "documentation":
            return """
Create comprehensive technical documentation including:
- Clear overview of what the code does
- Detailed explanation of key functions and classes
- API documentation with parameters and return values
- Usage examples and code snippets
- Architecture overview and design patterns
- Installation and setup instructions (if applicable)
- Troubleshooting and common issues

Write for developers who need to understand, use, or maintain this code.
If code analysis suggests complex architecture, mention where diagrams would be helpful.
"""
        return "Analyze and respond to the task appropriately with detailed, helpful information."