# json_to_rabbitmq.py
import json
import pika
import os
from dotenv import load_dotenv

# Load environment variables for RabbitMQ config
# This assumes you might have a .env file in the /app directory of the container
# or that RABBITMQ_HOST is set as an environment variable directly.
load_dotenv(dotenv_path=".env")

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "project_queue")
# This is the name of the file expected inside the container
INPUT_JSON_FILENAME = "projects.json"

def send_json_to_rabbitmq():
    input_file_path = os.path.join("/app", INPUT_JSON_FILENAME) # Assuming WORKDIR /app

    try:
        with open(input_file_path, 'r', encoding='utf-8') as f:
            projects = json.load(f)
    except FileNotFoundError:
        print(f"[ERROR] File {input_file_path} not found inside the container. Ensure it's correctly mounted.")
        return
    except json.JSONDecodeError:
        print(f"[ERROR] Could not decode JSON from {input_file_path}.")
        return

    if not projects:
        print(f"[INFO] No projects found in {input_file_path} to send to RabbitMQ.")
        return

    try:
        connection_params = pika.ConnectionParameters(host=RABBITMQ_HOST)
        connection = pika.BlockingConnection(connection_params)
        channel = connection.channel()
        channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)
        print(f"[INFO] Connected to RabbitMQ on host '{RABBITMQ_HOST}', queue '{RABBITMQ_QUEUE}'.")
    except pika.exceptions.AMQPConnectionError as e:
        print(f"[ERROR] Could not connect to RabbitMQ: {e}")
        print(f"[INFO] Ensure RabbitMQ is running and host '{RABBITMQ_HOST}' is correct and reachable.")
        return

    published_count = 0
    for project_data in projects:
        try:
            message_body = json.dumps(project_data)
            channel.basic_publish(
                exchange='',
                routing_key=RABBITMQ_QUEUE,
                body=message_body,
                properties=pika.BasicProperties(
                    delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE
                )
            )
            published_count += 1
            print(f"[OK] Sent project to RabbitMQ: {project_data.get('full_name', 'Unknown Project')} ({published_count}/{len(projects)})")
            if published_count >= 500:
                break
        except Exception as e:
            print(f"[ERROR] Failed to send project {project_data.get('full_name', 'Unknown Project')} to RabbitMQ: {e}")

    if connection.is_open:
        connection.close()
        print(f"[INFO] Published {published_count} projects to RabbitMQ. Connection closed.")

if __name__ == "__main__":
    send_json_to_rabbitmq()
