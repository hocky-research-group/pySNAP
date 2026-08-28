from snap_workflow.utils import io
from snap_workflow.dispatcher.runner import send_request


def get_server_status():
    """Queries current health, active worker leases, and task queue status from the server."""
    url, token = io.load_server_info()
    res = send_request(f"{url}/status", token, timeout=10)
    if res is None:
        raise ValueError(f"Failed to communicate with workflow server at {url}.")
    return res


def shutdown_server():
    """Cleanly shuts down the running workflow server daemon."""
    url, token = io.load_server_info()
    res = send_request(f"{url}/shutdown", token, timeout=10)
    if res is None:
        raise ValueError(f"Failed to communicate with workflow server at {url}.")
    return res
