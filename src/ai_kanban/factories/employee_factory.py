"""Factory for creating fully configured AI employees."""

from typing import List
import logging

from ..domain.artificial_employee import ArtificialEmployee, EmployeeRegistry
from ..domain.event_checks import (
    AssignmentCheck, KeywordCheck, CompositeCheck, StatusCheck, ContentLengthCheck
)
from ..domain.repositories import MemoryRepository
from ..workflows.employee_workflow import EmployeeWorkflowGraph


class EmployeeFactory:
    """Factory for creating fully configured AI employees."""
    
    def __init__(self, memory_repository: MemoryRepository):
        self.memory_repository = memory_repository
        self.logger = logging.getLogger(__name__)
    
    def create_engineering_manager(self) -> ArtificialEmployee:
        """Create Engineering Manager with specification capabilities."""
        
        employee = ArtificialEmployee(
            employee_id="eng_mgr_001",
            name="EngineeringManager",
            persona_system_prompt="""
You are a Senior Engineering Manager with 10+ years of experience leading technical teams.
You excel at breaking down complex problems into clear, actionable specifications.
You consider scalability, maintainability, and team capabilities in your planning.
You communicate technical concepts clearly to both technical and non-technical stakeholders.
You always provide structured, comprehensive specifications that teams can execute on.
            """.strip(),
            memory_repository=self.memory_repository
        )
        
        # Add reaction: Assigned + specification keywords → specification workflow
        employee.add_reaction(
            CompositeCheck([
                AssignmentCheck(),  # Must be assigned to this employee
                KeywordCheck([
                    "specification", "spec", "requirements", "architecture", 
                    "design", "plan", "roadmap", "technical approach", "solution design"
                ]),
                ContentLengthCheck(20)  # Ensure sufficient content
            ], "AND"),
            workflow=EmployeeWorkflowGraph("specification", self.memory_repository),
            priority=10
        )
        
        # Create and add workflow
        employee.add_workflow("specification", EmployeeWorkflowGraph("specification", self.memory_repository))
        
        self.logger.info(f"Created EngineeringManager employee: {employee.employee_id}")
        return employee
    
    def create_research_agent(self) -> ArtificialEmployee:
        """Create Research Agent with investigation capabilities."""
        
        employee = ArtificialEmployee(
            employee_id="research_001",
            name="ResearchAgent",
            persona_system_prompt="""
You are a Research Specialist with expertise in gathering and analyzing information across various domains.
You excel at finding credible sources, synthesizing complex information, and identifying key insights.
You present findings objectively with proper analysis and actionable recommendations.
You stay current with industry trends and emerging technologies.
You always provide comprehensive research with multiple perspectives and evidence-based conclusions.
            """.strip(),
            memory_repository=self.memory_repository
        )
        
        # Add reaction: Assigned + research keywords → research workflow
        employee.add_reaction(
            CompositeCheck([
                AssignmentCheck(),
                ContentLengthCheck(15)
            ], "AND"),
            workflow=EmployeeWorkflowGraph("research", self.memory_repository),
            priority=10
        )
        
        # Create and add workflow
        employee.add_workflow("research", EmployeeWorkflowGraph("research", self.memory_repository))
        
        self.logger.info(f"Created ResearchAgent employee: {employee.employee_id}")
        return employee
    
    def create_documentation_specialist(self) -> ArtificialEmployee:
        """Create Documentation Specialist with documentation capabilities."""
        
        employee = ArtificialEmployee(
            employee_id="doc_spec_001",
            name="DocSpecialist",
            persona_system_prompt="""
You are a Technical Documentation Specialist who creates clear, comprehensive documentation.
You excel at explaining complex code and systems in simple, understandable terms.
You create well-structured documentation that serves developers at all skill levels.
You always include practical examples and clear explanations of functionality.
When appropriate, you suggest where visual diagrams would enhance understanding.
            """.strip(),
            memory_repository=self.memory_repository
        )
        
        # Add reaction: Assigned + documentation/code keywords → documentation workflow
        employee.add_reaction(
            CompositeCheck([
                AssignmentCheck(),
                KeywordCheck([
                    "documentation", "document", "doc", "readme", "api docs", 
                    "code", "python", "```", "function", "class", "module"
                ]),
                ContentLengthCheck(10)
            ], "AND"),
            workflow=EmployeeWorkflowGraph("documentation", self.memory_repository),
            priority=10
        )
        
        # Create and add workflow
        employee.add_workflow("documentation", EmployeeWorkflowGraph("documentation", self.memory_repository))
        
        self.logger.info(f"Created DocSpecialist employee: {employee.employee_id}")
        return employee
    
    def create_default_employee_registry(self) -> EmployeeRegistry:
        """Create a registry with all default employees."""
        registry = EmployeeRegistry()
        
        # Create and register all employees
        eng_manager = self.create_engineering_manager()
        research_agent = self.create_research_agent()
        doc_specialist = self.create_documentation_specialist()
        
        registry.register_employee(eng_manager)
        registry.register_employee(research_agent)
        registry.register_employee(doc_specialist)
        
        self.logger.info(f"Created default employee registry with {len(registry.get_all_employees())} employees")
        return registry
    
