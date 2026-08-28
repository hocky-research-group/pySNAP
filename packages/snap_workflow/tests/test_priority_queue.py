import time
import json
import socket
import urllib.request
import threading
import pytest
from snap_workflow.server.daemon import WorkflowServer, WorkflowRequestHandler, PriorityJob

def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port

def test_priority_job_ordering():
    jobs = [
        PriorityJob(priority=1, handler=lambda: "low1"),
        PriorityJob(priority=0, handler=lambda: "high1"),
        PriorityJob(priority=1, handler=lambda: "low2"),
        PriorityJob(priority=0, handler=lambda: "high2"),
    ]
    sorted_jobs = sorted(jobs)
    assert [j.handler() for j in sorted_jobs] == ["high1", "high2", "low1", "low2"]

def test_workflow_server_priority_processing():
    from unittest.mock import MagicMock
    port = get_free_port()
    token = "test_token_123"
    server = WorkflowServer(("127.0.0.1", port), WorkflowRequestHandler, token=token)
    server.spoint_manager = MagicMock()
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        url_status = f"http://127.0.0.1:{port}/status"
        headers = {"Authorization": f"Bearer {token}"}
        req = urllib.request.Request(url_status, headers=headers)
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            assert data["status"] == "running"

        url_update = f"http://127.0.0.1:{port}/update_status"
        payload = json.dumps({
            "sweep": "test_sweep",
            "stage": "test_stage",
            "spoint_dict": {"x": 1},
            "status": "complete"
        }).encode()
        headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url_update, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            assert data["status"] == "ok"
            assert server.spoint_manager.set_status.called
    finally:
        server.shutdown()
        server.server_close()

def test_priority_queue_execution_order():
    from unittest.mock import MagicMock
    port = get_free_port()
    token = "test_token_456"
    server = WorkflowServer(("127.0.0.1", port), WorkflowRequestHandler, token=token)
    server.spoint_manager = MagicMock()
    server.spoint_manager.acquire_next_available.return_value = None
    server.spoint_manager.are_all_complete.return_value = False

    execution_order = []

    # Pause worker queue processing temporarily to accumulate jobs
    server._shutdown_event.set()
    server.scheduler_worker.join()

    # Re-enable worker with tracking
    server._shutdown_event.clear()

    # Enqueue multiple Priority 1 jobs (request_work)
    for i in range(3):
        server.task_queue.put(PriorityJob(1, lambda idx=i: (execution_order.append(f"req_{idx}"), ({"status": "none"}, 200))[1]))

    # Enqueue a Priority 0 job (update_status)
    server.task_queue.put(PriorityJob(0, lambda: (execution_order.append("update_status"), ({"status": "ok"}, 200))[1]))

    # Start queue processor
    worker = threading.Thread(target=server._process_scheduler_queue, daemon=True)
    worker.start()

    time.sleep(0.3)
    server._shutdown_event.set()
    worker.join()
    server.server_close()

    # update_status (Priority 0) MUST have executed before the queued req_* (Priority 1) jobs
    assert execution_order[0] == "update_status"
    assert execution_order[1:] == ["req_0", "req_1", "req_2"]
