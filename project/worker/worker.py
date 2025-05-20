import os
import json
import pika
import subprocess
import shutil # For removing directories
import traceback # For detailed error logging
import time # For sleep in main loop

# --- Configuration ---
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "broker")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "project_queue")
MVN_TEST_TIMEOUT_SECONDS = 350 # 15 minutes
GIT_CLONE_TIMEOUT_SECONDS = 240 # 5 minutes

# Local paths inside container
BASE_WORKDIR = "/work"    # Base directory for cloning projects
BASE_RESULTSDIR = "/results" # Base directory for storing test logs

def ensure_dir_exists(path):
    """Ensures that a directory exists, creating it if necessary."""
    os.makedirs(path, exist_ok=True)

# --- Main Worker Logic ---
def process_message(channel, method, props, body):
    """
    Processes a single message from the queue.
    Clones a project, runs Maven tests, and handles acknowledgments.
    """
    project_name = "UnknownProject"
    project_path = None # Path to the cloned source code
    logfile_path = None

    try:
        job = json.loads(body)
        project_name = job.get("name", "UnnamedProject")
        clone_url = job.get("clone_url")

        if not clone_url:
            print(f"[WORKER] [{project_name}] ERROR: Missing 'clone_url'. Discarding message.")
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return

        # Define paths for this specific project
        # Clone into a directory named after the project inside BASE_WORKDIR
        project_path = os.path.join(BASE_WORKDIR, project_name)
        logfile_path = os.path.join(BASE_RESULTSDIR, f"{project_name}_test_output.log")
        ensure_dir_exists(BASE_RESULTSDIR) # Ensure results directory exists

        # 1. Clean up previous attempt (if any) and Clone
        if os.path.exists(project_path):
            print(f"[WORKER] [{project_name}] Cleaning up existing directory: {project_path}")
            shutil.rmtree(project_path)
        
        print(f"[WORKER] [{project_name}] Cloning {clone_url} into {project_path}")
        clone_result = subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, project_path],
            capture_output=True, text=True, timeout=GIT_CLONE_TIMEOUT_SECONDS
        )

        if clone_result.returncode != 0:
            error_message = (f"[WORKER] [{project_name}] ERROR: Failed to clone. RC: {clone_result.returncode}\n"
                             f"Stderr: {clone_result.stderr}\nStdout: {clone_result.stdout}")
            print(error_message)
            with open(logfile_path, "w") as log: # Write clone error to log
                log.write(error_message)
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return

        print(f"[WORKER] [{project_name}] Successfully cloned.")

        # 2. Run the Maven tests
        print(f"[WORKER] [{project_name}] Running mvn test (timeout: {MVN_TEST_TIMEOUT_SECONDS}s). Log: {logfile_path}")
        with open(logfile_path, "w") as log: # Overwrite/create log for test output
            log.write(f"--- Test run for {project_name} ---\nClone URL: {clone_url}\n")
            log.write(f"--- Git Clone Output ---\nStdout:\n{clone_result.stdout}\nStderr:\n{clone_result.stderr}\n---\n\n")
            log.write("--- Maven Test Output ---\n")
            
            mvn_process_result = subprocess.run(
                ["mvn", "test", "-B"], # Batch mode
                cwd=project_path,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=MVN_TEST_TIMEOUT_SECONDS
            )

        if mvn_process_result.returncode == 0:
            print(f"[WORKER] [{project_name}] mvn test completed successfully.")
        else:
            print(f"[WORKER] [{project_name}] mvn test completed with exit code {mvn_process_result.returncode}. See log.")
        
        # 3. Acknowledge the message - success (job was "processed", even if tests failed)
        print(f"[WORKER] [{project_name}] Processing complete. Acknowledging message.")
        channel.basic_ack(delivery_tag=method.delivery_tag)

    except subprocess.TimeoutExpired as te:
        timeout_type = "Git Clone" if "git" in str(te.cmd) else "Maven Test"
        error_message = f"[WORKER] [{project_name}] ERROR: {timeout_type} timed out: {te}"
        print(error_message)
        if logfile_path:
            with open(logfile_path, "a") as log: # Append timeout info
                log.write(f"\n\n[WORKER] PROCESS TIMEOUT ({timeout_type}): {te}\n")
        # Discard messages that timeout, as they might consistently block workers
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        print(f"[WORKER] [{project_name}] NACKed message due to timeout (no requeue).")

    except json.JSONDecodeError as je:
        print(f"[WORKER] ERROR: Failed to decode JSON body: {body}. Error: {je}. Discarding message.")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    except pika.exceptions.AMQPConnectionError as amqp_err:
        print(f"[WORKER] [{project_name}] CRITICAL: AMQP Connection Error: {amqp_err}. Worker will attempt to reconnect.")
        raise # Re-raise to trigger reconnection logic in main()

    except Exception as e:
        error_message = f"[WORKER] [{project_name}] ERROR: An unexpected error occurred: {e}\n{traceback.format_exc()}"
        print(error_message)
        if logfile_path:
            with open(logfile_path, "a") as log: # Append error info
                log.write(f"\n\n[WORKER] UNEXPECTED ERROR:\n{error_message}\n")
        # Discard messages that cause unhandled errors to prevent blocking
        try:
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            print(f"[WORKER] [{project_name}] NACKed message due to unhandled error (no requeue).")
        except Exception as nack_e:
            print(f"[WORKER] [{project_name}] ERROR: Failed to NACK message after an unhandled error: {nack_e}")


def main():
    """Main function to set up RabbitMQ connection and start consuming."""
    print("[WORKER] Starting up...")
    ensure_dir_exists(BASE_WORKDIR)
    ensure_dir_exists(BASE_RESULTSDIR)

    connection = None
    while True:
        try:
            print(f"[WORKER] Attempting to connect to RabbitMQ host: {RABBITMQ_HOST}")
            connection_params = pika.ConnectionParameters(
                host=RABBITMQ_HOST,
                heartbeat=200 # Heartbeat interval in seconds
            )
            connection = pika.BlockingConnection(connection_params)
            channel = connection.channel()
            channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)
            channel.basic_qos(prefetch_count=1)

            print(f"[WORKER] Connected to RabbitMQ. Waiting for jobs on queue '{RABBITMQ_QUEUE}'...")
            channel.basic_consume(queue=RABBITMQ_QUEUE, on_message_callback=process_message)
            channel.start_consuming()

        except pika.exceptions.AMQPConnectionError as e:
            print(f"[WORKER] RabbitMQ connection failed: {e}. Retrying in 10 seconds...")
            if connection and connection.is_open: # Close broken connection if possible
                try:
                    connection.close()
                except Exception: pass # Ignore errors during close on a failed connection
            time.sleep(10)
        except KeyboardInterrupt:
            print("[WORKER] Shutting down...")
            if connection and connection.is_open:
                connection.close()
            break
        except Exception as e: # Catch any other unexpected errors in the main loop
            print(f"[WORKER] An unexpected error occurred in the main loop: {e}\n{traceback.format_exc()}")
            print("[WORKER] Retrying in 30 seconds...")
            if connection and connection.is_open:
                try:
                    connection.close()
                except Exception: pass
            time.sleep(30)

if __name__ == '__main__':
    main()
