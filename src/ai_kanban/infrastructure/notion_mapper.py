"""Mapper for converting between Notion API data and domain objects."""

from typing import Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

from ..domain.events import NotionTask, TaskStatus


class NotionTaskMapper:
    """Maps between Notion API data and NotionTask domain objects."""
    
    @classmethod
    def map_to_domain(cls, notion_data: Dict[str, Any]) -> NotionTask:
        """Convert raw Notion API data to NotionTask domain object."""
        
        # Extract basic properties
        notion_id = notion_data.get("id", "")
        notion_url = notion_data.get("url", "")
        
        # Extract timestamps
        created_time = cls._parse_datetime(notion_data.get("created_time"))
        last_edited_time = cls._parse_datetime(notion_data.get("last_edited_time"))
        
        # Extract properties
        properties = notion_data.get("properties", {})
        
        # Extract title (try both "Title" and "Task" properties)
        title = cls._extract_title(properties)
        
        # Extract other properties
        status = cls._extract_status(properties)
        description = cls._extract_rich_text(properties, "Description")
        ai_employee = cls._extract_text_property(properties, "AI Employee")
        assigned_to = cls._extract_person_property(properties, "assign")
        created_by = cls._extract_person_property(properties, "created by")
        github_url = cls._extract_url_property(properties, "Github")
        ai_processed = cls._extract_checkbox_property(properties, "ai processed")
        
        # Extract page content if available
        content = cls._extract_page_content(notion_data)
        
        return NotionTask(
            notion_id=notion_id,
            title=title,
            status=status,
            description=description,
            content=content,
            ai_employee=ai_employee,
            assigned_to=assigned_to,
            created_by=created_by or "Unknown",
            github_url=github_url,
            notion_url=notion_url,
            last_edited_time=last_edited_time,
            created_time=created_time,
            ai_processed=ai_processed
        )
    
    @classmethod
    def _extract_title(cls, properties: Dict[str, Any]) -> str:
        """Extract title from title property."""
        # Try different property names
        for prop_name in ["Title", "Task", "Name"]:
            title_prop = properties.get(prop_name, {})
            if title_prop.get("type") == "title":
                title_list = title_prop.get("title", [])
                if title_list:
                    return title_list[0].get("text", {}).get("content", "")
        return "Untitled Task"
    
    @classmethod
    def _extract_status(cls, properties: Dict[str, Any]) -> TaskStatus:
        """Extract status from status property."""
        status_prop = properties.get("Status", {})
        status_type = status_prop.get("type")
        
        status_name = ""
        if status_type == "select":
            select_obj = status_prop.get("select")
            if select_obj:
                status_name = select_obj.get("name", "")
        elif status_type == "status":
            status_obj = status_prop.get("status")
            if status_obj:
                status_name = status_obj.get("name", "")
        
        # Map to TaskStatus enum
        try:
            return TaskStatus(status_name)
        except ValueError:
            # Default to TO_DO if status not recognized
            logger.warning(f"Unknown status: {status_name}, using TO_DO")
            return TaskStatus.TO_DO
    
    @classmethod
    def _extract_rich_text(cls, properties: Dict[str, Any], prop_name: str) -> str:
        """Extract rich text content from property."""
        prop = properties.get(prop_name, {})
        if prop.get("type") == "rich_text":
            rich_text = prop.get("rich_text", [])
            return "".join(item.get("text", {}).get("content", "") for item in rich_text)
        return ""
    
    @classmethod
    def _extract_text_property(cls, properties: Dict[str, Any], prop_name: str) -> Optional[str]:
        """Extract text from various property types."""
        prop = properties.get(prop_name, {})
        prop_type = prop.get("type")
        
        if prop_type == "rich_text":
            rich_text = prop.get("rich_text", [])
            content = "".join(item.get("text", {}).get("content", "") for item in rich_text)
            return content if content.strip() else None
        elif prop_type == "select":
            select_obj = prop.get("select")
            return select_obj.get("name") if select_obj else None
        elif prop_type == "title":
            title_list = prop.get("title", [])
            if title_list:
                return title_list[0].get("text", {}).get("content", "")
        
        return None
    
    @classmethod
    def _extract_person_property(cls, properties: Dict[str, Any], prop_name: str) -> Optional[str]:
        """Extract person property (returns first person's name)."""
        prop = properties.get(prop_name, {})
        if prop.get("type") == "people":
            people = prop.get("people", [])
            if people:
                person = people[0]
                return person.get("name", person.get("id", "Unknown"))
        return None
    
    @classmethod
    def _extract_url_property(cls, properties: Dict[str, Any], prop_name: str) -> Optional[str]:
        """Extract URL property."""
        prop = properties.get(prop_name, {})
        if prop.get("type") == "url":
            return prop.get("url")
        return None
    
    @classmethod
    def _extract_checkbox_property(cls, properties: Dict[str, Any], prop_name: str) -> bool:
        """Extract checkbox property."""
        prop = properties.get(prop_name, {})
        if prop.get("type") == "checkbox":
            return prop.get("checkbox", False)
        return False
    
    @classmethod
    def _extract_page_content(cls, notion_data: Dict[str, Any]) -> str:
        """Extract page content if available in the response."""
        # In the current implementation, we don't get page content in the query response
        # This would require a separate API call to get page blocks
        # For now, we'll use the description or set to empty
        return ""
    
    @classmethod
    def _parse_datetime(cls, dt_string: Optional[str]) -> Optional[datetime]:
        """Parse ISO datetime string."""
        if not dt_string:
            return None
        try:
            return datetime.fromisoformat(dt_string.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return None
    
    @classmethod
    def create_notion_update_payload(cls, task_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Create payload for updating Notion task."""
        return {
            "page_id": task_id,
            "properties": updates
        }
    
    @classmethod
    def create_status_update_payload(cls, new_status: str) -> Dict[str, Any]:
        """Create payload for updating task status."""
        return {
            "Status": {
                "status": {
                    "name": new_status
                }
            }
        }
    
    @classmethod
    def create_ai_processed_update_payload(cls, processed: bool) -> Dict[str, Any]:
        """Create payload for updating ai processed checkbox."""
        return {
            "ai processed": {
                "checkbox": processed
            }
        }
    
    @classmethod
    def create_comment_blocks(cls, ai_response: str, processor_name: str, model_used: str) -> list:
        """Create Notion blocks for AI response comment."""
        blocks = [
            {
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": f"🤖 AI Assistant Response ({processor_name})"
                            },
                            "annotations": {
                                "bold": True
                            }
                        }
                    ],
                    "icon": {
                        "type": "emoji",
                        "emoji": "🤖"
                    },
                    "color": "blue"
                }
            }
        ]
        
        # Split long responses into chunks
        max_chunk_size = 2000
        response_chunks = cls._split_text_into_chunks(ai_response, max_chunk_size)
        
        # Add paragraph blocks for each chunk
        for chunk in response_chunks:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": chunk
                            }
                        }
                    ]
                }
            })
        
        # Add model info
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": f"Model: {model_used}"
                        },
                        "annotations": {
                            "italic": True,
                            "color": "gray"
                        }
                    }
                ]
            }
        })
        
        return blocks
    
    @classmethod
    def _split_text_into_chunks(cls, text: str, max_chunk_size: int) -> list:
        """Split text into chunks maintaining readability."""
        if len(text) <= max_chunk_size:
            return [text]
        
        chunks = []
        # Split by paragraphs first
        paragraphs = text.split('\n\n')
        current_chunk = ""
        
        for paragraph in paragraphs:
            # If adding this paragraph would exceed limit, start new chunk
            if len(current_chunk) + len(paragraph) + 2 > max_chunk_size and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = paragraph
            else:
                if current_chunk:
                    current_chunk += "\n\n" + paragraph
                else:
                    current_chunk = paragraph
            
            # If single paragraph is too long, split it
            if len(current_chunk) > max_chunk_size:
                words = current_chunk.split(' ')
                temp_chunk = ""
                
                for word in words:
                    if len(temp_chunk) + len(word) + 1 > max_chunk_size and temp_chunk:
                        chunks.append(temp_chunk.strip())
                        temp_chunk = word
                    else:
                        if temp_chunk:
                            temp_chunk += " " + word
                        else:
                            temp_chunk = word
                
                current_chunk = temp_chunk
        
        # Add remaining chunk
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks