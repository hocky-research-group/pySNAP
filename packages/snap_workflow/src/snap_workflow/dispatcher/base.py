import os
import sys
import time
import json
import logging
import urllib.request
import urllib.parse
import urllib.error
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

logger = logging.getLogger("snap_workflow.dispatcher.base")


def send_request(url: str, token: str, data: Optional[Dict[str, Any]] = None, retries: int = 1, backoff: float = 2.0, timeout: float = 300.0, *args, **kwargs) -> Optional[Dict[str, Any]]:
    """Convenience helper for authenticated HTTP requests with exponential backoff."""
    timeout = kwargs.get("timeout", timeout)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    encoded_data = json.dumps(data).encode("utf-8") if data is not None else None

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=encoded_data, headers=headers, method="POST" if data is not None else "GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(backoff * (2 ** attempt))
            else:
                logger.debug("send_request failed after %s attempts: %s", retries, e)
                return None
    return None


class BaseDispatcher(ABC):
    """Abstract base class for task dispatchers communicating with the workflow server."""

    def __init__(
        self,
        server_url: str,
        token: str,
        stages: str = "",
        sweeps: str = "",
        exclude_stages: str = "",
        exclude_sweeps: str = "",
        idle_delay: float = 1.0,
        connect_timeout: float = 5.0,
        host: Optional[str] = None
    ):
        self.server_url = server_url.rstrip("/")
        self.token = token
        self.stages = stages
        self.sweeps = sweeps
        self.exclude_stages = exclude_stages
        self.exclude_sweeps = exclude_sweeps
        self.idle_delay = idle_delay
        self.connect_timeout = connect_timeout
        self.host = host
        self.shutdown_requested = False
        self.active_jobs: Dict[str, Any] = {}

    def send_request(
        self,
        url: str,
        data: Optional[Dict[str, Any]] = None,
        retries: int = 5,
        backoff: float = 1.0,
        timeout: float = 300.0,
        *args,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Sends an authenticated HTTP request to the workflow server."""
        return send_request(url, self.token, data=data, retries=retries, backoff=backoff, timeout=timeout, *args, **kwargs)

    def get_available_resources(self) -> Dict[str, Any]:
        """Returns currently available hardware resources (e.g. cpus_avail, gpu_avail, mem_avail)."""
        return {}

    def request_work(self) -> Optional[Dict[str, Any]]:
        """Polls the server for an unlocked SPoint task matching filter criteria."""
        params = {}
        if self.stages:
            params["stages"] = self.stages
        if self.sweeps:
            params["sweeps"] = self.sweeps
        if self.exclude_stages:
            params["exclude_stages"] = self.exclude_stages
        if self.exclude_sweeps:
            params["exclude_sweeps"] = self.exclude_sweeps
        if self.host:
            params["host"] = self.host
        if getattr(self, "worker_id", None):
            params["worker_id"] = self.worker_id
        if getattr(self, "pending_assigned", None):
            params["target_spoints"] = ",".join(self.pending_assigned)

        res_info = self.get_available_resources()
        if res_info:
            params.update(res_info)

        query = urllib.parse.urlencode(params)
        url = f"{self.server_url}/request_work"
        if query:
            url += f"?{query}"

        return self.send_request(url)

    def notify_start(
        self,
        spoint_path: str,
        pid: Optional[Any] = None,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Notifies the workflow server that an SPoint task has started executing."""
        url = f"{self.server_url}/api/tasks/start"
        payload = {
            "spoint_path": spoint_path,
            "pid": pid,
            "worker_id": getattr(self, "worker_id", self.host),
            "host": self.host or "local"
        }
        if extra_data:
            payload.update(extra_data)
        resp = self.send_request(url, data=payload)
        return resp is not None and resp.get("status") == "ok"

    def send_heartbeats(self) -> None:
        """Sends heartbeats for all active in-flight tasks to extend server lease TTL."""
        if not self.active_jobs:
            return
        url = f"{self.server_url}/api/tasks/heartbeat"
        payload = {
            "spoint_paths": list(self.active_jobs.keys()),
            "worker_id": getattr(self, "worker_id", self.host),
            "host": self.host or "local"
        }
        self.send_request(url, data=payload)

    def notify_completion(
        self,
        spoint_path: str,
        success: bool = True,
        returncode: int = 0,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Notifies the workflow server that an SPoint task has completed."""
        url = f"{self.server_url}/update_status"
        payload = {
            "spoint_path": spoint_path,
            "status": "COMPLETED" if success else "FAILED",
            "returncode": returncode
        }
        if extra_data:
            payload.update(extra_data)

        resp = self.send_request(url, data=payload)
        return resp is not None and resp.get("status") == "success"

    def notify_shutdown(self) -> None:
        """Notifies the server that this dispatcher is shutting down."""
        url = f"{self.server_url}/notify_worker_shutdown"
        payload = {
            "worker_id": getattr(self, "worker_id", self.host or "unknown"),
            "host": self.host or "unknown",
            "active_tasks": list(self.active_jobs.keys())
        }
        try:
            send_request(url, self.token, data=payload, retries=1, timeout=1)
        except Exception:
            pass

    def run(self) -> None:
        """Main template method loop executing the dispatcher lifecycle."""
        logger.info(f"Starting dispatcher targeting {self.server_url} (host: {self.host or 'local'})")
        last_contact = time.time()
        last_heartbeat = time.time()
        try:
            while not self.shutdown_requested:
                self.reap_finished()

                # Periodic heartbeat check (every 15s)
                if self.active_jobs and (time.time() - last_heartbeat >= 15.0):
                    self.send_heartbeats()
                    last_heartbeat = time.time()

                if self.has_capacity():
                    task = self.request_work()
                    if task:
                        last_contact = time.time()
                        status_val = task.get("status")
                        if status_val == "shutdown":
                            logger.info("Server requested dispatcher shutdown.")
                            self.shutdown_requested = True
                            break
                        elif status_val == "spoint":
                            self.dispatch_task(task)
                    else:
                        # Server unreachable or error
                        if self.connect_timeout and (time.time() - last_contact >= self.connect_timeout):
                            logger.error(f"Failed to communicate with server for {self.connect_timeout}s. Exiting.")
                            self.shutdown_requested = True
                            break

                time.sleep(self.idle_delay)
        except KeyboardInterrupt:
            logger.info("Dispatcher interrupted by user.")
        finally:
            self.cleanup()
            self.notify_shutdown()
            logger.info("Dispatcher terminated.")

    @abstractmethod
    def has_capacity(self) -> bool:
        """Returns True if this dispatcher can accept and run another task."""
        pass

    @abstractmethod
    def dispatch_task(self, task: Dict[str, Any]) -> None:
        """Dispatches an SPoint task for execution."""
        pass

    @abstractmethod
    def reap_finished(self) -> None:
        """Checks the status of active in-flight tasks and reclaims resources."""
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Terminates or cancels any remaining active tasks upon shutdown."""
        pass
