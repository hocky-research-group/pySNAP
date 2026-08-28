import os
import sys
import json

# Add local package source to PYTHONPATH
sys.path.insert(0, os.getcwd() + "/src")

from snap_workflow.dispatcher import dispatcher_loop

stages = os.getenv("WORKER_STAGES", "")
sweeps = os.getenv("WORKER_SWEEPS", "")
exclude_stages = os.getenv("WORKER_EXCLUDE_STAGES", "")
exclude_sweeps = os.getenv("WORKER_EXCLUDE_SWEEPS", "")
worker_host = os.getenv("WORKER_HOST", "local")
worker_id = os.getenv("WORKER_ID")

port = os.getenv("SERVER_PORT")
server_url = os.getenv("SERVER_URL")
if not server_url and port:
    server_url = f"http://127.0.0.1:{port}"
token = os.getenv("SERVER_TOKEN")

if not server_url or not token:
    server_file = ".workflow/server"
    if os.path.isfile(server_file):
        try:
            with open(server_file, "r") as f:
                data = json.load(f)
                p = data.get("port", 8080)
                server_url = server_url or f"http://127.0.0.1:{p}"
                token = token or data.get("token")
        except Exception:
            pass

if not server_url:
    server_url = "http://127.0.0.1:8080"

dispatcher_loop(
    server_url=server_url,
    token=token,
    stages=stages,
    sweeps=sweeps,
    exclude_stages=exclude_stages,
    exclude_sweeps=exclude_sweeps,
    host=worker_host,
    worker_id=worker_id
)
