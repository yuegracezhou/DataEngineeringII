import os
import json
import pika
import subprocess
import shutil  # For removing directories
import traceback  # For detailed error logging
import time    # For timing and sleep
import re      # For parsing Maven output
import socket  # For getting container hostname as a fallback worker_id

# --- Configuration ---
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "broker")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "project_queue")
# Subprocess Timeouts (adjust based on typical project behavior & AMQP heartbeat)
# Pika heartbeat is 200s, so effective AMQP timeout is ~400s.
# These timeouts should be less than that.
MVN_TEST_TIMEOUT_SECONDS = 360  # 6 minutes
GIT_CLONE_TIMEOUT_SECONDS = 240 # 4 minutes

# Paths inside the container
BASE_WORKDIR = "/work"      # Base directory for cloning projects
BASE_RESULTSDIR = "/results"  # Base directory for storing raw test logs
BASE_SUMMARYDIR = "/summary"  # Directory for structured JSON summaries (mounted to NFS)

def ensure_dir_exists(path):
    """Ensures that a directory exists, creating it if necessary."""
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as e:
        print(f"[WORKER] Error creating directory {path}: {e}")
        # Depending on severity, you might want to raise this or handle it

# --- Main Worker Logic ---
def process_message(channel, method, props, body):
    """
    Processes a single message from the queue.
    Clones a project, runs Maven tests, parses results, and handles acknowledgments.
    """
    project_name = "UnknownProject" # Default for logging
    clone_url = "N/A"
    # Use Swarm's NODE_IDENTIFIER if available, otherwise container hostname
    node_id_or_worker_hostname = os.getenv("NODE_IDENTIFIER", socket.gethostname())
    
    # Initialize paths to None for broader scope in error handling
    project_path = None
    logfile_path = None
    summary_file_path = None

    # --- Timing Start ---
    processing_start_monotonic = time.perf_counter()
    processing_start_absolute_epoch = time.time()

    current_status = "processing_started" # For summary in case of early exit

    try:
        job = json.loads(body)
        project_name = job.get("name", "UnnamedProject")
        clone_url = job.get("clone_url")

        # Define paths for this specific project
        project_path = os.path.join(BASE_WORKDIR, project_name)
        logfile_path = os.path.join(BASE_RESULTSDIR, f"{project_name}_test_output.log")
        summary_file_path = os.path.join(BASE_SUMMARYDIR, f"{project_name}_summary.json")
        
        ensure_dir_exists(BASE_RESULTSDIR) # Ensure results log directory exists
        ensure_dir_exists(BASE_SUMMARYDIR) # Ensure summary output directory exists

        if not clone_url:
            print(f"[WORKER] [{project_name}] ERROR: Missing 'clone_url'. Discarding message.")
            current_status = "error_missing_clone_url"
            raise ValueError("Missing clone_url in job data") # Raise error to go to general except block

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
            error_message = (f"ERROR: Failed to clone. RC: {clone_result.returncode}\n"
                             f"Stderr: {clone_result.stderr}\nStdout: {clone_result.stdout}")
            print(f"[WORKER] [{project_name}] {error_message}")
            with open(logfile_path, "w") as log: log.write(error_message)
            current_status = "clone_failed"
            raise Exception(f"Git clone failed with RC {clone_result.returncode}") # Raise error

        print(f"[WORKER] [{project_name}] Successfully cloned.")
        current_status = "cloned_successfully"

        # 2. Run the Maven tests
        print(f"[WORKER] [{project_name}] Running mvn test (timeout: {MVN_TEST_TIMEOUT_SECONDS}s). Log: {logfile_path}")
        mvn_exit_code = -1 # Default in case of pre-run error for mvn
        
        with open(logfile_path, "w") as log:
            log.write(f"--- Test run for {project_name} ---\nClone URL: {clone_url}\n")
            log.write(f"Node/Worker: {node_id_or_worker_hostname}\n")
            log.write(f"--- Git Clone Output ---\nStdout:\n{clone_result.stdout}\nStderr:\n{clone_result.stderr}\n---\n\n")
            log.write("--- Maven Test Output ---\n")
            
            mvn_process_result = subprocess.run(
                ["mvn", "test", "-B"], # Batch mode for CI/scripts
                cwd=project_path,
                stdout=log, stderr=subprocess.STDOUT, timeout=MVN_TEST_TIMEOUT_SECONDS
            )
            mvn_exit_code = mvn_process_result.returncode

        if mvn_exit_code == 0:
            print(f"[WORKER] [{project_name}] mvn test completed successfully.")
            current_status = "mvn_test_success"
        else:
            print(f"[WORKER] [{project_name}] mvn test completed with exit code {mvn_exit_code}. See log.")
            current_status = f"mvn_test_failed_rc{mvn_exit_code}"
        
        # 3. Extract passed/failed test summary from Maven console output
        tests_run, passed, failures_plus_errors, skipped = 0, 0, 0, 0
        try:
            with open(logfile_path, "r") as logf:
                for line in logf: # Read the whole log file
                    # Example: [INFO] Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
                    # More robust regex might be needed depending on Maven versions / plugins
                    match = re.search(r"Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+),\s*Skipped:\s*(\d+)", line)
                    if match:
                        tests_run = int(match.group(1))
                        # Combine failures and errors as 'failures' for simplicity as per your previous script
                        failures_plus_errors = int(match.group(2)) + int(match.group(3))
                        skipped = int(match.group(4))
                        # Often the summary line is near the end, but taking the first one found.
                        # For more accuracy, you might want to parse the last such line.
                        break 
            passed = tests_run - failures_plus_errors - skipped
            print(f"[WORKER] [{project_name}] Parsed test results: Run={tests_run}, Passed={passed}, Failed/Errored={failures_plus_errors}, Skipped={skipped}")
        except Exception as parse_err:
            print(f"[WORKER] [{project_name}] ERROR: Could not parse test results from log: {parse_err}")
            current_status = "result_parsing_error"
        
        # --- Timing End ---
        processing_end_monotonic = time.perf_counter()
        processing_end_absolute_epoch = time.time()
        total_processing_duration_seconds = processing_end_monotonic - processing_start_monotonic

        # Prepare summary data
        summary_data = {
            "project_name": project_name,
            "clone_url": clone_url,
            "node_id_or_worker_hostname": node_id_or_worker_hostname,
            "status": current_status, # Reflects the stage of processing
            "mvn_exit_code": mvn_exit_code,
            "tests_run": tests_run,
            "passed": passed,
            "failed_plus_errors": failures_plus_errors,
            "skipped": skipped,
            "processing_start_time_monotonic": processing_start_monotonic,
            "processing_end_time_monotonic": processing_end_monotonic,
            "processing_start_absolute_epoch": processing_start_absolute_epoch,
            "processing_end_absolute_epoch": processing_end_absolute_epoch,
            "total_processing_duration_seconds": total_processing_duration_seconds
        }
        with open(summary_file_path, "w") as outf:
            json.dump(summary_data, outf, indent=2)
        print(f"[WORKER] [{project_name}] Summary saved to {summary_file_path}. Processed in {total_processing_duration_seconds:.2f}s.")
        
        # 4. Acknowledge the message
        print(f"[WORKER] [{project_name}] Acknowledging message.")
        channel.basic_ack(delivery_tag=method.delivery_tag)

    except subprocess.TimeoutExpired as te:
        timeout_type = "Git Clone" if "git" in str(te.cmd) else "Maven Test"
        error_message = f"[WORKER] [{project_name}] ERROR: {timeout_type} timed out: {te}"
        print(error_message)
        
        processing_end_monotonic = time.perf_counter()
        processing_end_absolute_epoch = time.time()
        total_processing_duration_seconds = processing_end_monotonic - processing_start_monotonic
        
        if logfile_path:
            with open(logfile_path, "a") as log: log.write(f"\n\n[WORKER] PROCESS TIMEOUT ({timeout_type}): {te}\n")
        
        failed_summary = {
            "project_name": project_name, "clone_url": clone_url,
            "node_id_or_worker_hostname": node_id_or_worker_hostname, 
            "status": f"{timeout_type.lower().replace(' ', '_')}_timeout",
            "processing_start_time_monotonic": processing_start_monotonic, 
            "processing_end_time_monotonic": processing_end_monotonic,
            "processing_start_absolute_epoch": processing_start_absolute_epoch,
            "processing_end_absolute_epoch": processing_end_absolute_epoch,
            "total_processing_duration_seconds": total_processing_duration_seconds
        }
        if summary_file_path: # Ensure summary_file_path is defined
            with open(summary_file_path, "w") as outf: json.dump(failed_summary, outf, indent=2)
            print(f"[WORKER] [{project_name}] Timeout summary saved.")

        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        print(f"[WORKER] [{project_name}] NACKed message due to timeout (no requeue).")

    except json.JSONDecodeError as je:
        print(f"[WORKER] ERROR: Failed to decode JSON body for a message. Error: {je}. Discarding message.")
        # Not writing summary here as project_name might be unknown
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    except pika.exceptions.AMQPConnectionError as amqp_err:
        print(f"[WORKER] [{project_name}] CRITICAL: AMQP Connection Error: {amqp_err}. Worker will attempt to reconnect.")
        raise # Re-raise to trigger reconnection logic in main()

    except Exception as e: # Catch-all for other unexpected errors
        error_message = f"[WORKER] [{project_name}] ERROR: An unexpected error occurred: {e}\n{traceback.format_exc()}"
        print(error_message)
        
        processing_end_monotonic = time.perf_counter()
        processing_end_absolute_epoch = time.time()
        total_processing_duration_seconds = processing_end_monotonic - processing_start_monotonic
        
        if logfile_path:
            with open(logfile_path, "a") as log: log.write(f"\n\n[WORKER] UNEXPECTED ERROR:\n{error_message}\n")
        
        failed_summary = {
            "project_name": project_name, "clone_url": clone_url,
            "node_id_or_worker_hostname": node_id_or_worker_hostname, "status": "unexpected_error",
            "error_details": str(e), "traceback": traceback.format_exc(),
            "processing_start_time_monotonic": processing_start_monotonic, 
            "processing_end_time_monotonic": processing_end_monotonic,
            "processing_start_absolute_epoch": processing_start_absolute_epoch,
            "processing_end_absolute_epoch": processing_end_absolute_epoch,
            "total_processing_duration_seconds": total_processing_duration_seconds
        }
        if summary_file_path: # Ensure summary_file_path is defined
             with open(summary_file_path, "w") as outf: json.dump(failed_summary, outf, indent=2)
             print(f"[WORKER] [{project_name}] Error summary saved.")
        try:
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            print(f"[WORKER] [{project_name}] NACKed message due to unhandled error (no requeue).")
        except Exception as nack_e: # If channel is already closed, nack might fail
            print(f"[WORKER] [{project_name}] ERROR: Failed to NACK message after an unhandled error: {nack_e}")


def main():
    """Main function to set up RabbitMQ connection and start consuming."""
    print("[WORKER] Starting up...")
    ensure_dir_exists(BASE_WORKDIR)
    ensure_dir_exists(BASE_RESULTSDIR)
    ensure_dir_exists(BASE_SUMMARYDIR)

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
            # Process one message at a time. Only after acking will a new one be fetched by this worker.
            channel.basic_qos(prefetch_count=1) 

            print(f"[WORKER] Connected to RabbitMQ. Waiting for jobs on queue '{RABBITMQ_QUEUE}'...")
            channel.basic_consume(queue=RABBITMQ_QUEUE, on_message_callback=process_message)
            channel.start_consuming()

        except pika.exceptions.AMQPConnectionError as e:
            print(f"[WORKER] RabbitMQ connection failed: {e}. Retrying in 10 seconds...")
            if connection and connection.is_open:
                try:
                    connection.close()
                except Exception: pass 
            time.sleep(10)
        except KeyboardInterrupt: # Allow clean shutdown with Ctrl+C
            print("[WORKER] Shutdown signal received...")
            if connection and connection.is_open:
                print("[WORKER] Closing RabbitMQ connection.")
                connection.close()
            print("[WORKER] Exiting.")
            break
        except Exception as e: # Catch any other unexpected errors in the main loop
            print(f"[WORKER] An critical error occurred in the main worker loop: {e}\n{traceback.format_exc()}")
            print("[WORKER] Attempting to recover. Retrying connection in 30 seconds...")
            if connection and connection.is_open:
                try:
                    connection.close()
                except Exception: pass
            time.sleep(30)

if __name__ == '__main__':
    main()
