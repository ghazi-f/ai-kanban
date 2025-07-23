import json
import os

import pika
from dotenv import load_dotenv

load_dotenv()


class RabbitMQPublisher:
    def __init__(self):
        self.host = os.getenv("RABBITMQ_HOST", "localhost")
        self.port = int(os.getenv("RABBITMQ_PORT", "5672"))
        self.username = os.getenv("RABBITMQ_USERNAME", "guest")
        self.password = os.getenv("RABBITMQ_PASSWORD", "guest")
        self.queue_name = os.getenv("RABBITMQ_QUEUE", "task_notifications")
        self.connection = None
        self.channel = None

    def connect(self):
        """Establish connection to RabbitMQ"""
        try:
            credentials = pika.PlainCredentials(self.username, self.password)
            parameters = pika.ConnectionParameters(
                host=self.host, 
                port=self.port, 
                credentials=credentials,
                heartbeat=600,  # 10 minutes
                blocked_connection_timeout=300,  # 5 minutes
            )
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()

            # Declare queue
            self.channel.queue_declare(queue=self.queue_name, durable=True)
            print(f"Connected to RabbitMQ at {self.host}:{self.port}")

        except Exception as e:
            print(f"Failed to connect to RabbitMQ: {e}")
            raise

    def publish_task(self, task_data: dict):
        """Publish a task notification to the queue"""
        try:
            if not self.channel or self.connection.is_closed:
                self.connect()

            message = json.dumps(task_data)
            self.channel.basic_publish(
                exchange="",
                routing_key=self.queue_name,
                body=message,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Make message persistent
                ),
            )
            task_name = task_data.get('name', 'Unknown')
            task_id = task_data.get('id')
            print(f"Published task: {task_name} (ID: {task_id})")

        except (pika.exceptions.ConnectionClosed, pika.exceptions.ChannelClosed) as e:
            print(f"Connection lost, reconnecting: {e}")
            self.connect()
            # Retry the publish
            message = json.dumps(task_data)
            self.channel.basic_publish(
                exchange="",
                routing_key=self.queue_name,
                body=message,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Make message persistent
                ),
            )
            task_name = task_data.get('name', 'Unknown')
            task_id = task_data.get('id')
            print(f"Published task: {task_name} (ID: {task_id})")
        except Exception as e:
            print(f"Failed to publish task: {e}")
            raise

    def is_connected(self) -> bool:
        """Check if connection is still alive"""
        return (
            self.connection and 
            not self.connection.is_closed and 
            self.channel and 
            self.channel.is_open
        )

    def close(self):
        """Close the connection"""
        if self.connection and not self.connection.is_closed:
            self.connection.close()
            print("RabbitMQ connection closed")
