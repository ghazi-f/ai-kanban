import signal
import time
from dotenv import load_dotenv


from ai_kanban.infrastructure.repositories import NotionTaskRepository
from ai_kanban.infrastructure.rabbitmq_client import RabbitMQPublisher

load_dotenv()

class TaskMonitorService:
    def __init__(self, poll_interval: int = 60):
        self.poll_interval = poll_interval
        self.notion_client = NotionTaskRepository()
        self.rabbitmq_publisher = RabbitMQPublisher()
        self.running = False

    def setup_signal_handlers(self):
        """Setup graceful shutdown handlers"""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print(f"\nReceived signal {signum}, shutting down gracefully...")
        self.running = False

    def start_monitoring(self):
        """Start the main monitoring loop"""
        self.setup_signal_handlers()
        self.running = True

        try:
            self.rabbitmq_publisher.connect()
            print(f"Starting Notion task monitor (polling every {self.poll_interval}s)")

            while self.running:
                try:
                    self.check_for_new_tasks()
                except Exception as e:
                    print(f"Error during monitoring cycle: {e}")

                # Sleep with interruption check
                for _ in range(self.poll_interval):
                    if not self.running:
                        break
                    time.sleep(1)

        except KeyboardInterrupt:
            print("\nMonitoring stopped by user")
        finally:
            self.rabbitmq_publisher.close()

    def check_for_new_tasks(self):
        """Check Notion database for new tasks and publish them"""
        try:
            # Ensure RabbitMQ connection is healthy
            if not self.rabbitmq_publisher.is_connected():
                print("RabbitMQ connection lost, reconnecting...")
                self.rabbitmq_publisher.connect()

            # Fetch all tasks from Notion
            all_tasks = self.notion_client.fetch_tasks()
            if not all_tasks:
                print("No tasks found in Notion database")
                return

            # Filter to only tasks that haven't been AI processed and are ready for processing
            ai_tasks = []
            for task in all_tasks:
                has_ai_employee = self._has_ai_employee_assigned(task)
                status_is_processable = self._is_status_processable(task)
                not_ai_processed = not self._is_ai_processed(task)
                
                if has_ai_employee and status_is_processable and not_ai_processed:
                    ai_tasks.append(task)
            
            if ai_tasks:
                print(f"Found {len(ai_tasks)} tasks ready for AI processing")
                for task in ai_tasks:
                    # Publish to RabbitMQ
                    self.rabbitmq_publisher.publish_task(task)
                    print(f"Published task: {task.get('properties', {}).get('Title', {}).get('title', [{}])[0].get('text', {}).get('content', 'Unknown')}")
            else:
                print("No tasks ready for AI processing (need AI Employee assigned, processable status, and not yet AI processed)")

        except Exception as e:
            print(f"Error checking for new tasks: {e}")
            # Don't re-raise to allow continuing the monitoring loop
    
    def _has_ai_employee_assigned(self, task: dict) -> bool:
        """Check if the task has an AI Employee assigned"""
        try:
            ai_employee_property = task.get("properties", {}).get("AI Employee", {})
            prop_type = ai_employee_property.get("type")
            
            if prop_type == "rich_text":
                rich_text = ai_employee_property.get("rich_text", [])
                content = "".join(item.get("text", {}).get("content", "") for item in rich_text)
                return bool(content.strip())
            elif prop_type == "select":
                select_obj = ai_employee_property.get("select")
                return select_obj is not None and bool(select_obj.get("name", "").strip())
            elif prop_type == "title":
                title_list = ai_employee_property.get("title", [])
                if title_list:
                    content = title_list[0].get("text", {}).get("content", "")
                    return bool(content.strip())
            
            return False
        except Exception:
            return False
    
    def _is_status_processable(self, task: dict) -> bool:
        """Check if the task status is processable (To Do or In Progress)"""
        try:
            status_property = task.get("properties", {}).get("Status", {})
            status_type = status_property.get("type")
            
            status_name = ""
            if status_type == "select":
                select_obj = status_property.get("select")
                if select_obj:
                    status_name = select_obj.get("name", "")
            elif status_type == "status":
                status_obj = status_property.get("status")
                if status_obj:
                    status_name = status_obj.get("name", "")
            
            # Allow both "To Do" and "In Progress" status for processing
            processable_statuses = ["to do", "in progress"]
            return status_name.lower() in processable_statuses
        except Exception:
            return False
    
    def _is_ai_processed(self, task: dict) -> bool:
        """Check if the task has already been processed by AI."""
        try:
            ai_processed_property = task.get("properties", {}).get("ai processed", {})
            if ai_processed_property.get("type") == "checkbox":
                return ai_processed_property.get("checkbox", False)
            return False
        except Exception:
            return False


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Monitor Notion database for new tasks"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Polling interval in seconds (default: 60)",
    )

    args = parser.parse_args()

    monitor = TaskMonitorService(poll_interval=args.interval)
    monitor.start_monitoring()


if __name__ == "__main__":
    main()
