"""Concrete implementations of repository interfaces."""

import json
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
import asyncio
import logging

from ..domain.repositories import MemoryRepository, EventRepository, TaskRepository
from ..domain.events import Event
from .notion_mapper import NotionTaskMapper

# Move NotionTaskMonitor here as a private class
class _NotionTaskMonitor:
    def __init__(self):
        from notion_client import Client
        import os
        self.client = Client(auth=os.getenv("NOTION_TOKEN"))
        self.database_id = os.getenv("NOTION_DATABASE_ID")

    def fetch_tasks(self) -> list[dict]:
        try:
            response = self.client.databases.query(
                database_id=self.database_id,
                sorts=[{"timestamp": "created_time", "direction": "descending"}],
            )
            return response.get("results", [])
        except Exception as e:
            print(f"Error fetching tasks from Notion: {e}")
            return []

    def extract_task_data(self, task: dict) -> dict:
        task_id = task.get("id")
        created_time = task.get("created_time")
        last_edited_time = task.get("last_edited_time")
        title_property = task.get("properties", {}).get("Task", {})
        task_name = ""
        if title_property.get("type") == "title":
            title_list = title_property.get("title", [])
            if title_list:
                task_name = title_list[0].get("text", {}).get("content", "")
        status_property = task.get("properties", {}).get("Status", {})
        status = ""
        if status_property.get("type") == "select":
            select_obj = status_property.get("select")
            if select_obj:
                status = select_obj.get("name", "")
        return {
            "id": task_id,
            "name": task_name,
            "status": status,
            "created_time": created_time,
            "last_edited_time": last_edited_time,
        }

    def update_task_status(self, task_id: str, new_status: str) -> bool:
        try:
            self.client.pages.update(
                page_id=task_id,
                properties={
                    "Status": {
                        "status": {
                            "name": new_status
                        }
                    }
                }
            )
            print(f"Successfully updated task status to: {new_status}")
            return True
        except Exception as e:
            print(f"Error updating task status to '{new_status}': {e}")
            try:
                self.client.pages.update(
                    page_id=task_id,
                    properties={
                        "Status": {
                            "name": new_status
                        }
                    }
                )
                print(f"Successfully updated task status to: {new_status} (alternative format)")
                return True
            except Exception as e2:
                print(f"Alternative format also failed: {e2}")
                return False


class InMemoryMemoryRepository(MemoryRepository):
    """In-memory implementation of MemoryRepository for testing/development."""
    
    def __init__(self):
        self._memories: Dict[str, List[Dict[str, Any]]] = {}
        self.logger = logging.getLogger(__name__)
    
    async def store_memory(self, employee_name: str, memory_text: str, 
                          metadata: Dict[str, Any] = None) -> None:
        """Store a memory for an AI employee."""
        if employee_name not in self._memories:
            self._memories[employee_name] = []
        
        memory_entry = {
            "text": memory_text,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {}
        }
        
        self._memories[employee_name].append(memory_entry)
        
        # Keep only last 100 memories per employee
        if len(self._memories[employee_name]) > 100:
            self._memories[employee_name] = self._memories[employee_name][-100:]
        
        self.logger.debug(f"Stored memory for {employee_name}: {memory_text[:50]}...")
    
    async def get_memories(self, employee_name: str, query: str, limit: int = 10) -> List[str]:
        """Retrieve relevant memories using simple text matching."""
        if employee_name not in self._memories:
            return []
        
        memories = self._memories[employee_name]
        query_lower = query.lower()
        
        # Simple relevance scoring based on keyword matching
        scored_memories = []
        for memory in memories:
            text = memory["text"].lower()
            score = sum(1 for word in query_lower.split() if word in text)
            if score > 0:
                scored_memories.append((score, memory["text"]))
        
        # Sort by relevance and return top results
        scored_memories.sort(key=lambda x: x[0], reverse=True)
        return [memory[1] for memory in scored_memories[:limit]]
    
    async def get_employee_memory_count(self, employee_name: str) -> int:
        """Get total memory count for an employee."""
        return len(self._memories.get(employee_name, []))


class VectorMemoryRepository(MemoryRepository):
    """Vector database implementation - placeholder for future implementation."""
    
    def __init__(self, vector_db_connection=None):
        self.vector_db = vector_db_connection
        self.logger = logging.getLogger(__name__)
        # For now, fallback to in-memory
        self._fallback = InMemoryMemoryRepository()
    
    async def store_memory(self, employee_name: str, memory_text: str, 
                          metadata: Dict[str, Any] = None) -> None:
        """Store a memory using vector embeddings."""
        # TODO: Implement vector database storage
        # For now, use fallback
        await self._fallback.store_memory(employee_name, memory_text, metadata)
    
    async def get_memories(self, employee_name: str, query: str, limit: int = 10) -> List[str]:
        """Retrieve relevant memories using semantic search."""
        # TODO: Implement vector similarity search
        # For now, use fallback
        return await self._fallback.get_memories(employee_name, query, limit)
    
    async def get_employee_memory_count(self, employee_name: str) -> int:
        """Get total memory count for an employee."""
        return await self._fallback.get_employee_memory_count(employee_name)


class FileEventRepository(EventRepository):
    """File-based event repository for persistence."""
    
    def __init__(self, events_file: str = "events.jsonl"):
        self.events_file = events_file
        self.logger = logging.getLogger(__name__)
    
    async def store_event(self, event: Event) -> None:
        """Store a domain event to file."""
        try:
            # Clean event data for JSON serialization
            cleaned_data = self._clean_for_json(event.__dict__)
            
            event_data = {
                "event_type": event.__class__.__name__,
                "event_id": str(event.event_id),
                "timestamp": event.timestamp.isoformat(),
                "data": cleaned_data,
                "metadata": event.metadata
            }
            
            # Append to JSONL file
            with open(self.events_file, "a") as f:
                f.write(json.dumps(event_data) + "\n")
        
        except Exception as e:
            self.logger.error(f"Failed to store event {event.event_id}: {e}")
    
    def _clean_for_json(self, data):
        """Clean data structure for JSON serialization."""
        from uuid import UUID
        from datetime import datetime
        from enum import Enum
        
        if isinstance(data, dict):
            return {k: self._clean_for_json(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._clean_for_json(item) for item in data]
        elif isinstance(data, UUID):
            return str(data)
        elif isinstance(data, datetime):
            return data.isoformat()
        elif isinstance(data, Enum):
            return data.value
        elif hasattr(data, '__dict__'):
            return self._clean_for_json(data.__dict__)
        else:
            return data
    
    async def get_events_by_type(self, event_type: str, limit: int = 100) -> List[Event]:
        """Get events of a specific type."""
        events = []
        try:
            if not os.path.exists(self.events_file):
                return events
            
            with open(self.events_file, "r") as f:
                for line in f:
                    try:
                        event_data = json.loads(line.strip())
                        if event_data["event_type"] == event_type:
                            events.append(event_data)
                            if len(events) >= limit:
                                break
                    except json.JSONDecodeError:
                        continue
            
            return events[-limit:]  # Return most recent
        
        except Exception as e:
            self.logger.error(f"Failed to get events by type {event_type}: {e}")
            return []
    
    async def get_events_for_entity(self, entity_id: str, limit: int = 100) -> List[Event]:
        """Get events related to a specific entity."""
        events = []
        try:
            if not os.path.exists(self.events_file):
                return events
            
            with open(self.events_file, "r") as f:
                for line in f:
                    try:
                        event_data = json.loads(line.strip())
                        # Check if entity_id appears in the event data
                        if entity_id in str(event_data.get("data", {})):
                            events.append(event_data)
                            if len(events) >= limit:
                                break
                    except json.JSONDecodeError:
                        continue
            
            return events[-limit:]  # Return most recent
        
        except Exception as e:
            self.logger.error(f"Failed to get events for entity {entity_id}: {e}")
            return []


class NotionTaskRepository(TaskRepository):
    """Notion-based task repository using internal _NotionTaskMonitor."""
    
    def __init__(self, notion_client=None):
        self.notion_client = notion_client or _NotionTaskMonitor()
        self.logger = logging.getLogger(__name__)
    
    async def update_task_status(self, task_id: str, new_status: str) -> bool:
        """Update the status of a task in Notion."""
        try:
            # Use the existing sync method in an async way
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                None, 
                self.notion_client.update_task_status, 
                task_id, 
                new_status
            )
            return success
        except Exception as e:
            self.logger.error(f"Failed to update task status for {task_id}: {e}")
            return False
    
    async def post_comment_to_task(self, task_id: str, comment_content: List[Dict[str, Any]]) -> bool:
        """Post a comment to a task in Notion."""
        try:
            # Use the Notion client to append blocks to the page
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.notion_client.client.blocks.children.append(
                    block_id=task_id,
                    children=comment_content
                )
            )
            self.logger.info(f"Comment posted to Notion task: {task_id}")
            return True
        
        except Exception as e:
            self.logger.error(f"Failed to post comment to task {task_id}: {e}")
            return False
    
    async def get_task_content(self, task_id: str) -> Optional[str]:
        """Get the full content of a task page."""
        try:
            # Get page blocks
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                self.notion_client.client.blocks.children.list,
                task_id
            )
            
            # Extract text content from blocks
            content_parts = []
            for block in response.get("results", []):
                text_content = self._extract_text_from_block(block)
                if text_content:
                    content_parts.append(text_content)
            
            return "\n".join(content_parts)
        
        except Exception as e:
            self.logger.error(f"Failed to get task content for {task_id}: {e}")
            return None
    
    def fetch_tasks(self) -> list[dict]:
        """Fetch all tasks from the Notion database."""
        return self.notion_client.fetch_tasks()
    
    def extract_task_data(self, task: dict) -> dict:
        """Extract task data from a Notion task."""
        return self.notion_client.extract_task_data(task)
    
    def _extract_text_from_block(self, block: Dict[str, Any]) -> str:
        """Extract text content from a Notion block."""
        block_type = block.get("type", "")
        
        if block_type in ["paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item", "numbered_list_item"]:
            rich_text = block.get(block_type, {}).get("rich_text", [])
            return "".join(item.get("text", {}).get("content", "") for item in rich_text)
        elif block_type == "code":
            rich_text = block.get("code", {}).get("rich_text", [])
            language = block.get("code", {}).get("language", "")
            code_content = "".join(item.get("text", {}).get("content", "") for item in rich_text)
            return f"```{language}\n{code_content}\n```"
        elif block_type == "callout":
            rich_text = block.get("callout", {}).get("rich_text", [])
            return "".join(item.get("text", {}).get("content", "") for item in rich_text)
        
        return ""


class RepositoryFactory:
    """Factory for creating repository instances."""
    
    @staticmethod
    def create_memory_repository(use_vector_db: bool = False) -> MemoryRepository:
        """Create memory repository instance."""
        if use_vector_db:
            return VectorMemoryRepository()
        else:
            return InMemoryMemoryRepository()
    
    @staticmethod
    def create_event_repository(events_file: str = "events.jsonl") -> EventRepository:
        """Create event repository instance."""
        return FileEventRepository(events_file)
    
    @staticmethod
    def create_task_repository(notion_client=None) -> TaskRepository:
        """Create task repository instance."""
        return NotionTaskRepository(notion_client)