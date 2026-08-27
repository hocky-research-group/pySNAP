import os
import sys

# Add local package source to PYTHONPATH
sys.path.insert(0, os.getcwd() + "/src")

from snap_workflow.dispatcher import dispatcher_loop

stages = os.getenv("WORKER_STAGES", "")
sweeps = os.getenv("WORKER_SWEEPS", "")
exclude_stages = os.getenv("WORKER_EXCLUDE_STAGES", "")
exclude_sweeps = os.getenv("WORKER_EXCLUDE_SWEEPS", "")
worker_host = os.getenv("WORKER_HOST", "local")
worker_id = os.getenv("WORKER_ID")

dispatcher_loop(
    server_url=os.getenv("SERVER_URL"),
    token=os.getenv("SERVER_TOKEN"),
    stages=stages,
    sweeps=sweeps,
    exclude_stages=exclude_stages,
    exclude_sweeps=exclude_sweeps,
    host=worker_host,
    worker_id=worker_id
)
