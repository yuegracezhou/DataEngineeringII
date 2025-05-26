import os
import json
import pika
import subprocess
import shutil # For removing directories
import traceback # For detailed error logging
import time # <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< IMPORT THIS
import re
import socket

# --- Configuration --- (remains the same)
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "broker")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "project_queue")
MVN_TEST_TIMEOUT_SECONDS = 350
GIT_CLONE_TIMEOUT_SECONDS = 240

BASE_WORKDIR = "/work"
BASE_RESULTSDIR = "/results"
BASE_SUMMARYDIR = "/summary"

def ensure_dir_exists(path):
    os.makedirs(path, exist_ok=True)

# --- Main Worker Logic ---
def process_message(channel, method, props, body):
    project_name = "UnknownProject"
    project_path = None
    logfile_path = None
    summary_file_path = None # Define this for potential use in error blocks
    clone_url = "N/A" # Default for summary if not found

    processing_start_time = time.perf_counter() # <<<<<< START: Record time when processing for this message begins
    node_id_or_worker_hostname = os.getenv("NODE_IDENTIFIER", socket.gethostname()) # Get node/worker ID early

    try:
        job = json.loads(body)
        project_name = job.get("name", "UnnamedProject")
        clone_url = job.get("clone_url") # Get clone_url here to include in summary even on failure

        if not clone_url:
            print(f"[WORKER] [{project_name}] ERROR: Missing 'clone_url'. Discarding message.")
            # Log partial info if desired, before nacking
            processing_end_time = time.perf_counter()
            total_processing_time = processing_end_time - processing_start_time
            partial_summary = {
                "project_name": project_name,
                "clone_url": clone_url,
                "node_id_or_worker_hostname": node_id_or_worker_hostname,
                "status": "error_missing_clone_url",
                "processing_start_time": processing_start_time,
                "processing_end_time": processing_end_time,
                "total_processing_duration_seconds": total_processing_time
            }
            summary_file_path = os.path.join(BASE_SUMMARYDIR, f"{project_name}_summary.json")
            ensure_dir_exists(BASE_SUMMARYDIR)
            with open(summary_file_path, "w") as outf:
                json.dump(partial_summary, outf, indent=2)
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return

        project_path = os.path.join(BASE_WORKDIR, project_name)
        logfile_path = os.path.join(BASE_RESULTSDIR, f"{project_name}_test_output.log")
        summary_file_path = os.path.join(BASE_SUMMARYDIR, f"{project_name}_summary.json")
        ensure_dir_exists(BASE_RESULTSDIR)
        ensure_dir_exists(BASE_SUMMARYDIR)

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
            with open(logfile_path, "w") as log: log.write(error_message)
            # Log partial info before nacking
            processing_end_time = time.perf_counter()
            total_processing_time = processing_end_time - processing_start_time
            failed_summary = {
                "project_name": project_name, "clone_url": clone_url,
                "node_id_or_worker_hostname": node_id_or_worker_hostname, "status": "clone_failed",
                "git_clone_return_code": clone_result.returncode, "git_stderr": clone_result.stderr,
                "processing_start_time": processing_start_time, "processing_end_time": processing_end_time,
                "total_processing_duration_seconds": total_processing_time
            }
            with open(summary_file_path, "w") as outf: json.dump(failed_summary, outf, indent=2)
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return

        print(f"[WORKER] [{project_name}] Successfully cloned.")

        print(f"[WORKER] [{project_name}] Running mvn test (timeout: {MVN_TEST_TIMEOUT_SECONDS}s). Log: {logfile_path}")
        mvn_exit_code = -1 # Default if timeout or other pre-run error
        with open(logfile_path, "w") as log:
            log.write(f"--- Test run for {project_name} ---\nClone URL: {clone_url}\n")
            log.write(f"--- Git Clone Output ---\nStdout:\n{clone_result.stdout}\nStderr:\n{clone_result.stderr}\n---\n\n")
            log.write("--- Maven Test Output ---\n")
            
            mvn_process_result = subprocess.run(
                ["mvn", "test", "-B"],
                cwd=project_path,
                stdout=log, stderr=subprocess.STDOUT, timeout=MVN_TEST_TIMEOUT_SECONDS
            )
            mvn_exit_code = mvn_process_result.returncode

        if mvn_exit_code == 0:
            print(f"[WORKER] [{project_name}] mvn test completed successfully.")
        else:
            print(f"[WORKER] [{project_name}] mvn test completed with exit code {mvn_exit_code}. See log.")
        
        tests_run, passed, failures, skipped = 0, 0, 0, 0
        with open(logfile_path, "r") as logf:
            for line in logf:
                match = re.search(r"Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+),\s*Skipped:\s*(\d+)", line)
                if match:
                    tests_run = int(match.group(1))
                    failures = int(match.group(2)) + int(match.group(3)) # Failures + Errors
                    skipped = int(match.group(4))
                    break
        passed = tests_run - failures - skipped
        
        processing_end_time = time.perf_counter() # <<<<<< END: Record time after main work
        total_processing_time = processing_end_time - processing_start_time

        summary = {
            "project_name": project_name,
            "clone_url": clone_url,
            "node_id_or_worker_hostname": node_id_or_worker_hostname,
            "status": "processed",
            "mvn_exit_code": mvn_exit_code,
            "tests_run": tests_run,
            "passed": passed,
            "failed_plus_errors": failures, # Renamed for clarity
            "skipped": skipped,
            "processing_start_time_monotonic": processing_start_time, # Using perf_counter for duration
            "processing_end_time_monotonic": processing_end_time,
            "total_processing_duration_seconds": total_processing_time
        }
        with open(summary_file_path, "w") as outf:
            json.dump(summary, outf, indent=2)
        print(f"[WORKER] [{project_name}] Summary saved. Processed in {total_processing_time:.2f}s. Acknowledging.")
        channel.basic_ack(delivery_tag=method.delivery_tag)

    except subprocess.TimeoutExpired as te:
        timeout_type = "Git Clone" if "git" in str(te.cmd) else "Maven Test"
        error_message = f"[WORKER] [{project_name}] ERROR: {timeout_type} timed out: {te}"
        print(error_message)
        
        processing_end_time = time.perf_counter() # <<<<<< END: Record time even on timeout
        total_processing_time = processing_end_time - processing_start_time
        
        if logfile_path: # Ensure logfile_path is defined
            with open(logfile_path, "a") as log:
                log.write(f"\n\n[WORKER] PROCESS TIMEOUT ({timeout_type}): {te}\n")
        
        failed_summary = {
            "project_name": project_name, "clone_url": clone_url,
            "node_id_or_worker_hostname": node_id_or_worker_hostname, "status": f"{timeout_type.lower().replace(' ', '_')}_timeout",
            "processing_start_time_monotonic": processing_start_time, "processing_end_time_monotonic": processing_end_time,
            "total_processing_duration_seconds": total_processing_time
        }
        if summary_file_path: # Ensure summary_file_path is defined
            with open(summary_file_path, "w") as outf: json.dump(failed_summary, outf, indent=2)
            print(f"[WORKER] [{project_name}] Timeout summary saved.")

        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        print(f"[WORKER] [{project_name}] NACKed message due to timeout (no requeue).")

    except json.JSONDecodeError as je:
        print(f"[WORKER] ERROR: Failed to decode JSON body: {body}. Error: {je}. Discarding message.")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    except pika.exceptions.AMQPConnectionError as amqp_err:
        print(f"[WORKER] [{project_name}] CRITICAL: AMQP Connection Error: {amqp_err}. Worker will attempt to reconnect.")
        raise 

    except Exception as e:
        error_message = f"[WORKER] [{project_name}] ERROR: An unexpected error occurred: {e}\n{traceback.format_exc()}"
        print(error_message)
        
        processing_end_time = time.perf_counter() # <<<<<< END: Record time on other errors too
        total_processing_time = processing_end_time - processing_start_time

        if logfile_path:
            with open(logfile_path, "a") as log:
                log.write(f"\n\n[WORKER] UNEXPECTED ERROR:\n{error_message}\n")
        
        failed_summary = {
            "project_name": project_name, "clone_url": clone_url,
            "node_id_or_worker_hostname": node_id_or_worker_hostname, "status": "unexpected_error",
            "error_details": str(e),
            "processing_start_time_monotonic": processing_start_time, "processing_end_time_monotonic": processing_end_time,
            "total_processing_duration_seconds": total_processing_time
        }
        if summary_file_path:
             with open(summary_file_path, "w") as outf: json.dump(failed_summary, outf, indent=2)
             print(f"[WORKER] [{project_name}] Error summary saved.")
        try:
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            print(f"[WORKER] [{project_name}] NACKed message due to unhandled error (no requeue).")
        except Exception as nack_e:
            print(f"[WORKER] [{project_name}] ERROR: Failed to NACK message after an unhandled error: {nack_e}")

# --- main() function remains the same ---
def main():
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
