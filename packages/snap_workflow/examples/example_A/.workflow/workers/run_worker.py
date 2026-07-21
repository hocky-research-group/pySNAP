import os
import sys

# Add local package source to PYTHONPATH
sys.path.insert(0, os.getcwd() + "/src")

try:
    from nyut_workflow.core.worker import worker_loop
except ImportError:
    # If installed in editable mode, PYTHONPATH might not need src/
    from nyut_workflow.core.worker import worker_loop

# Load variables passed by submit command
port = os.getenv("SERVER_PORT")
token = os.getenv("SERVER_TOKEN")
concurrency = int(os.getenv("WORKER_CONCURRENCY", "1"))

if not port or not token:
    print("Error: SERVER_PORT and SERVER_TOKEN must be specified in the environment.")
    sys.exit(1)

server_url = f"http://127.0.0.1:{port}"

worker_loop(server_url, token, concurrency=concurrency)
