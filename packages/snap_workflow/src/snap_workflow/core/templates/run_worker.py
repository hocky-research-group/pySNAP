import os
import sys

# Add local package source to PYTHONPATH
sys.path.insert(0, os.getcwd() + "/src")

try:
    from snap_workflow.worker import worker_loop
except ImportError:
    # If installed in editable mode, PYTHONPATH might not need src/
    from snap_workflow.worker import worker_loop

# Load variables passed by submit command
port = os.getenv("SERVER_PORT")
token = os.getenv("SERVER_TOKEN")
stages = os.getenv("WORKER_STAGES", "")
sweeps = os.getenv("WORKER_SWEEPS", "")
exclude_stages = os.getenv("WORKER_EXCLUDE_STAGES", "")
exclude_sweeps = os.getenv("WORKER_EXCLUDE_SWEEPS", "")
worker_host = os.getenv("WORKER_HOST", "local")
worker_id = os.getenv("WORKER_ID")

if not port or not token:
    print("Error: SERVER_PORT and SERVER_TOKEN must be specified in the environment.")
    sys.exit(1)

server_url = f"http://127.0.0.1:{port}"

worker_loop(server_url, token, stages=stages, sweeps=sweeps,
            exclude_stages=exclude_stages, exclude_sweeps=exclude_sweeps,
            host=worker_host, worker_id=worker_id)
