# AI Kanban System - Setup and Testing Instructions

![Futuristic AI Kanban](./futuristic_kanban.png)
## Overview

This AI Kanban system has been completely redesigned using Domain Driven Design (DDD) principles with LangGraph workflows. The system monitors Notion tasks and processes them using AI employees (EngineeringManager, ResearchAgent, DocSpecialist) through sophisticated workflow orchestration.

## Architecture Summary

- **Domain-Driven Design**: Clean separation of domain logic, infrastructure, and application layers
- **AI Employees**: Autonomous agents with specific personas and capabilities
- **LangGraph Workflows**: Sophisticated workflow orchestration with error handling and retry logic
- **Event-Driven**: Task assignment based on AI Employee column in Notion
- **Memory-Aware**: AI employees maintain context through vectorial database storage (still WIP)

## Prerequisites

1. **Python 3.12+** (tested with Python 3.12.11)
2. **UV package manager** (recommended for dependency management)
3. **RabbitMQ server** (for message queuing)
4. **Notion API access** (for task monitoring and updates)
5. **Anthropic API key** (for Claude AI integration)

## Environment Setup

1. **Install UV package manager** (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Clone and setup the project**:
   ```bash
   cd ai_kanban
   uv sync
   ```

3. **Configure environment variables**:
   Copy `.env.example` to `.env` and configure:
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` with your credentials:
   ```bash
   # Notion Configuration
   NOTION_TOKEN=your_notion_integration_token
   NOTION_DATABASE_ID=your_notion_database_id
   
   # Anthropic API
   ANTHROPIC_API_KEY=your_anthropic_api_key
   
   # RabbitMQ Configuration
   RABBITMQ_USERNAME=guest
   RABBITMQ_PASSWORD=guest
   RABBITMQ_HOST=localhost
   RABBITMQ_PORT=5672
   RABBITMQ_QUEUE=task_notifications
   ```

## Notion Database Setup

Configure your Notion database with these **exact column names**:

- **Title** (Title field)
- **Status** (Status field with values: "To Do", "In Progress", "Done", "Cancelled")
- **AI Employee** (Rich Text field - drives task assignment)
- **Description** (Rich Text field - optional)
- **Github** (URL field - optional)
- **ID** (Text field - optional)
- **assign** (People field - optional)
- **created by** (People field)
- **content** (Rich Text field - optional, auto-populated from page content)

### AI Employee Values

Use these exact values in the "AI Employee" column to assign tasks:
- `EngineeringManager` - For specifications, architecture, planning
- `ResearchAgent` - For research, investigation, analysis
- `DocSpecialist` - For documentation, code explanation

## Running the System

### 1. Start RabbitMQ Server

**MacOS (with Homebrew)**:
```bash
brew services start rabbitmq
```

**Docker**:
```bash
docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management
```

**Linux (systemd)**:
```bash
sudo systemctl start rabbitmq-server
```

### 2. Start the Task Monitor

The monitor watches your Notion database for tasks with assigned AI employees:

```bash
uv run python -m ai_kanban.monitor
```

This will:
- Monitor Notion database every 30 seconds
- Send new tasks to RabbitMQ queue
- Only process tasks with "AI Employee" assigned
- Respect status filters (processes "To Do" and "In Progress")

### 3. Start the DDD Consumer

The consumer processes tasks using AI employees and LangGraph workflows:

```bash
uv run python -m ai_kanban.consumer
```

This will:
- Connect to RabbitMQ and consume task messages
- Route tasks to appropriate AI employees based on assignment
- Execute LangGraph workflows with error handling and retries
- Update task status: To Do → In Progress → Done
- Post AI responses as comments to Notion tasks
- Store memories for context in future tasks

### 4. Monitor Logs

Both services provide detailed logging. Watch for:
- Task assignment validation
- Workflow execution progress
- Status transitions
- Error handling and retries

## Testing the System

### 1. Run the Test Suite

```bash
uv run pytest tests/ -v
```

Expected output: `92 passed, 66 warnings`

The test suite covers:
- Domain events and business logic
- AI employee behavior and workflows
- Event check system
- Consumer message processing
- Repository implementations

### 2. Integration Testing

**Create a test task in Notion**:
1. Add a new row to your Notion database
2. Set Title: "Research AI agent architecture patterns"
3. Set Status: "To Do"
4. Set AI Employee: "ResearchAgent"
5. Add Description: "Investigate different patterns for AI agent architecture"

**Expected behavior**:
1. Monitor detects the new task (within 30 seconds)
2. Task is sent to RabbitMQ queue
3. Consumer picks up the task
4. ResearchAgent processes it using research workflow
5. Status changes: To Do → In Progress → Done
6. AI response appears as a comment in Notion

### 3. Test Each Employee Type

**EngineeringManager**:
- Title: "Create technical specification for user authentication"
- AI Employee: "EngineeringManager"
- Keywords: specification, requirements, architecture

**ResearchAgent**:
- Title: "Research best practices for microservices deployment"
- AI Employee: "ResearchAgent"  
- Keywords: research, investigate, analyze

**DocSpecialist**:
- Title: "Document the API endpoints and create examples"
- AI Employee: "DocSpecialist"
- Keywords: documentation, API docs, code

## System Features

### Status Transitions
- **To Do → In Progress**: When AI employee starts processing
- **In Progress → Done**: When processing completes successfully
- **In Progress → To Do**: When processing fails (with error logging)

### Memory System
- AI employees remember previous interactions
- Context is retrieved using vectorial search
- Memories are stored per employee for continualization

### Workflow Orchestration
- **Specification Workflow**: Requirements gathering, architecture planning
- **Research Workflow**: Information gathering, analysis, recommendations
- **Documentation Workflow**: Code analysis, documentation generation

### Error Handling
- Automatic retries with exponential backoff
- Graceful degradation on failures
- Comprehensive error logging
- Status reversion on critical failures

## Troubleshooting

### Common Issues

**1. "No module named 'ai_kanban'"**
```bash
# Ensure you're in the project directory and using uv
cd ai_kanban
uv run python -m ai_kanban.monitor
```

**2. "Connection refused" to RabbitMQ**
```bash
# Check RabbitMQ is running
brew services list | grep rabbitmq
# Or check Docker container
docker ps | grep rabbitmq
```

**3. "Task not being processed"**
- Verify "AI Employee" column has exact spelling: `EngineeringManager`, `ResearchAgent`, or `DocSpecialist`
- Check task status is "To Do" or "In Progress"
- Verify monitor logs show task detection
- Check consumer logs for processing errors

**4. "Tests failing"**
```bash
# Clean and reinstall dependencies
uv clean
uv sync
uv run pytest tests/ -v
```

### Debug Mode

Enable debug logging by setting:
```bash
export LOG_LEVEL=DEBUG
```

### Log Locations

- Monitor: Stdout with timestamps
- Consumer: Stdout with employee-specific logging
- Tests: Pytest output with detailed failures

## Architecture Diagrams

See `docs/architecture_diagram.excalidraw` for the complete system architecture visualization showing data flow from Notion → Monitor → RabbitMQ → Consumer → AI Employees → Claude AI.

## Development

### Adding New Employee Types

1. Create employee in `factories/employee_factory.py`
2. Define keywords and workflow type
3. Implement workflow logic in `workflows/employee_workflow.py`
4. Add tests in `tests/`

### Extending Workflows

LangGraph workflows support:
- Multiple execution paths
- Conditional branching
- Error recovery
- State management
- Tool integration

See `src/ai_kanban/workflows/employee_workflow.py` for examples.

---

**System Status**: ✅ All tests passing, DDD architecture implemented, LangGraph workflows operational 