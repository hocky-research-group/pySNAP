import os
import sys
import json
import time
import secrets
import logging
import subprocess
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

from snap_workflow.utils.constants import *
from snap_workflow.utils import path, io
from snap_workflow.core.domain import spoints as spoint_tools, stages as stage_tools
from snap_workflow.utils.logging import logger
from snap_workflow.server.tunnels import ensure_remote_tunnel
from snap_workflow.server.scheduler import OrchestratorScheduler

active_schedulers = {}


def register_auto_scheduler(server, remote_name, stages="", sweeps="", exclude_stages="", exclude_sweeps="", profile="worker_profile"):
    if not hasattr(server, "schedulers"):
        server.schedulers = {}
    if not hasattr(server, "auto_schedulers"):
        server.auto_schedulers = server.schedulers

    if remote_name in server.schedulers:
        old_sched = server.schedulers[remote_name]
        old_sched.shutdown_event.set()

    sched = OrchestratorScheduler(
        remote=remote_name,
        stages=stages,
        sweeps=sweeps,
        exclude_stages=exclude_stages,
        exclude_sweeps=exclude_sweeps,
        server=server,
        profile=profile
    )
    server.schedulers[remote_name] = sched
    server.auto_schedulers[remote_name] = sched
    sched.daemon = True
    sched.start()


def start_server(host="127.0.0.1", port=0):
    root = path.get_root()
    info_path = os.path.join(root, SERVER_INFO)

    server = WorkflowServer((host, port), WorkflowRequestHandler)
    actual_port = server.server_address[1]
    url = f"http://{host}:{actual_port}"

    server_info = {
        "url": url,
        "token": server.token,
        "host": host,
        "port": actual_port,
        "pid": os.getpid()
    }

    with open(info_path, "w") as f:
        json.dump(server_info, f, indent=4)

    import threading
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    return server, server_info

class WorkflowServer(HTTPServer):
    def __init__(self, server_address, RequestHandlerClass, token=None):
        super().__init__(server_address, RequestHandlerClass)
        self.token = token or secrets.token_hex(16)
        self.spoint_manager = spoint_tools.SPointStatusManager()
        self.schedulers = {}
        self.auto_schedulers = self.schedulers
        self.active_tunnels = {}


class WorkflowRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _check_auth(self):
        auth_header = self.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Unauthorized"}).encode())
            return False

        token = auth_header.split(" ", 1)[1]
        if token != self.server.token:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Forbidden"}).encode())
            return False
        return True

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "running"}).encode())
            return

        if parsed.path == "/shutdown":
            if not self._check_auth():
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "shutdown"}).encode())
            import threading
            threading.Thread(target=self.server.shutdown).start()
            return

        if parsed.path == "/request_work":
            if not self._check_auth():
                return

            try:
                cpus_avail = int(params.get("cpus_avail", [1])[0])
            except Exception:
                cpus_avail = 1

            try:
                gpu_avail = int(params.get("gpu_avail", [-1])[0])
            except Exception:
                gpu_avail = -1

            try:
                mem_avail = float(params.get("mem_avail", [0.0])[0])
            except Exception:
                mem_avail = 0.0

            try:
                min_cpu_running_gpu = int(params.get("min_cpu_running_gpu", [0])[0])
            except Exception:
                min_cpu_running_gpu = 0

            host = params.get("host", ["local"])[0]

            stages_str = params.get("stages", [""])[0]
            sweeps_str = params.get("sweeps", [""])[0]
            exclude_stages_str = params.get("exclude_stages", [""])[0]
            exclude_sweeps_str = params.get("exclude_sweeps", [""])[0]

            allowed_stages = {x.strip() for x in stages_str.split(",") if x.strip()} if stages_str else None
            allowed_sweeps = {x.strip() for x in sweeps_str.split(",") if x.strip()} if sweeps_str else None
            exclude_stages = {x.strip() for x in exclude_stages_str.split(",") if x.strip()} if exclude_stages_str else None
            exclude_sweeps = {x.strip() for x in exclude_sweeps_str.split(",") if x.strip()} if exclude_sweeps_str else None

            try:
                candidate = self.server.spoint_manager.acquire_next_available(
                    cpus_avail=cpus_avail,
                    gpu_avail=gpu_avail,
                    mem_avail=mem_avail,
                    min_cpu_running_gpu=min_cpu_running_gpu,
                    allowed_stages=allowed_stages,
                    allowed_sweeps=allowed_sweeps,
                    exclude_stages=exclude_stages,
                    exclude_sweeps=exclude_sweeps,
                    host=host
                )
            except Exception as e:
                logger.error("Error acquiring next available task: %s", e, exc_info=True)
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
                return

            if candidate:
                sweep_name, stage_name, spoint_dict, spoint_path = candidate
                resp_data = {
                    "status": "spoint",
                    "sweep": sweep_name,
                    "stage": stage_name,
                    "spoint_dict": spoint_dict,
                    "spoint_path": spoint_path
                }
                if host != "local":
                    try:
                        from snap_workflow.utils.io import load_global_remotes, load_local_remotes
                        from snap_workflow.server.sync import push_dependency_data
                        g_remotes = load_global_remotes()
                        l_remotes = load_local_remotes()
                        r_path = l_remotes.get(host, {}).get("path") or g_remotes.get(host, {}).get("path")
                        if r_path:
                            r_host = g_remotes.get(host, {}).get("host", host)
                            rel_sp = os.path.relpath(spoint_path, path.get_root())

                            # Push target spoint directory (containing params.pkl)
                            push_dependency_data(host, r_host, r_path, rel_sp)

                            # Push dependent stage spoints if present
                            st_cfg = self.server.spoint_manager.stages_dict.get(stage_name, {})
                            deps = st_cfg.get("dependencies") if "dependencies" in st_cfg else st_cfg.get("dependent_stages", [])
                            for dep in deps:
                                dep_sp = self.server.spoint_manager.get_spoint(sweep_name, dep, spoint_dict)
                                if dep_sp and os.path.exists(dep_sp["path"]):
                                    dep_rel_sp = os.path.relpath(dep_sp["path"], path.get_root())
                                    push_dependency_data(host, r_host, r_path, dep_rel_sp)
                    except Exception as sync_e:
                        logger.warning("Failed to push spoint and dependency data for %s to %s: %s", stage_name, host, sync_e)
            else:
                all_complete = self.server.spoint_manager.are_all_complete(
                    allowed_stages=allowed_stages,
                    allowed_sweeps=allowed_sweeps,
                    exclude_stages=exclude_stages,
                    exclude_sweeps=exclude_sweeps
                )
                if all_complete:
                    resp_data = {"status": "shutdown"}
                else:
                    resp_data = {"status": "none"}

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(resp_data).encode())
            return

        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": "Not Found"}).encode())

    def do_POST(self):
        if self.path == "/notify_completion":
            if not self._check_auth():
                return

            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode())

            if "spoint_path" in data and "sweep" not in data:
                sp_path = data["spoint_path"]
                parts = os.path.normpath(sp_path).split(os.sep)
                if SPOINTS in parts:
                    idx = parts.index(SPOINTS)
                    stage_name = parts[idx - 1]
                    spoint_string = parts[idx + 1]
                    spoint_dict = spoint_tools.parse_spoint_string(spoint_string)
                    sweeps = sweep_tools.load_sweeps()
                    sweep_name = None
                    for sw_n, sw in sweeps.items():
                        if stage_name in sw.get("stages", []):
                            sweep_name = sw_n
                            break
                    data["stage"] = stage_name
                    data["spoint_dict"] = spoint_dict
                    if sweep_name:
                        data["sweep"] = sweep_name
            sweep_name = data.get("sweep")
            stage_name = data.get("stage")
            spoint_dict = data.get("spoint_dict")
            status_val = data.get("status", "complete")
            host = data.get("host", "local")

            try:
                from snap_workflow.core.domain import status as status_module
                if stage_name and spoint_dict:
                    sp_path = spoint_tools.get_spoint_path(stage_name, spoint_dict)
                    try:
                        status_module.write_status(status_val, sp_path)
                    except Exception as st_e:
                        logger.warning("Failed to write local status file for %s %s: %s", stage_name, spoint_dict, st_e)

                if sweep_name and stage_name and spoint_dict:
                    self.server.spoint_manager.set_status(sweep_name, stage_name, spoint_dict, status_val, host=host)
                    logger.info("Manager updated status of spoint %s %s to '%s' (reported by %s)", stage_name, spoint_dict, status_val, host)

                if host != "local" and stage_name and spoint_dict:
                    try:
                        from snap_workflow.utils.io import load_global_remotes, load_local_remotes
                        g_remotes = load_global_remotes()
                        l_remotes = load_local_remotes()
                        r_path = l_remotes.get(host, {}).get("path") or g_remotes.get(host, {}).get("path")
                        if r_path:
                            r_host = g_remotes.get(host, {}).get("host", host)
                            rel_sp = spoint_tools.get_spoint_path(stage_name, spoint_dict)
                            local_sp = rel_sp
                            r_path_clean = r_path.rstrip('/')
                            remote_sp = f"{r_path_clean}/{os.path.relpath(rel_sp, path.get_root())}"
                            sync_cmd = ["rsync", "-avz", f"{r_host}:{remote_sp}/", f"{local_sp}/"]
                            subprocess.run(sync_cmd, capture_output=True)
                    except Exception as sync_e:
                        logger.warning("Failed to sync back outputs on completion for %s: %s", stage_name, sync_e)
            except Exception as e:
                logger.error("Failed to update status on completion notification: %s", e)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
            return

        if self.path == "/notify_shutdown":
            if not self._check_auth():
                return

            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode())
            worker_id = data.get("worker_id", "unknown")
            host = data.get("host", "local")
            logger.info("[WORKER] Worker '%s' on host '%s' notified server of shutdown.", worker_id, host)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
            return

        if self.path == "/submit_worker":
            if not self._check_auth():
                return

            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode())

            name = data.get("name", data.get("remote"))
            profile = data.get("profile", "cpu")
            num_workers = int(data.get("num_workers", 1))
            sbatch_args = data.get("sbatch_args", "")
            stages = data.get("stages", "")
            sweeps = data.get("sweeps", "")
            exclude_stages = data.get("exclude_stages", "")
            exclude_sweeps = data.get("exclude_sweeps", "")

            try:
                if name == "local":
                    from snap_workflow.worker.slurm import launch_local_workers
                    launch_local_workers(
                        num_workers=num_workers,
                        stages=stages,
                        sweeps=sweeps,
                        exclude_stages=exclude_stages,
                        exclude_sweeps=exclude_sweeps,
                        profile=profile
                    )
                    msg = f"Successfully spawned {num_workers} local worker process(es)."
                else:
                    ensure_remote_tunnel(self.server, name)
                    from snap_workflow.remote.setup import launch_remote_workers_server_side
                    launch_remote_workers_server_side(
                        server_port=self.server.server_port,
                        token=self.server.token,
                        remote_name=name,
                        profile=profile,
                        num_workers=num_workers,
                        sbatch_args=sbatch_args,
                        stages=stages,
                        sweeps=sweeps,
                        exclude_stages=exclude_stages,
                        exclude_sweeps=exclude_sweeps
                    )
                    msg = f"Successfully submitted {num_workers} worker Slurm job(s) to remote '{name}'."

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "message": msg}).encode())
            except Exception as e:
                logger.error("Failed to submit worker: %s", e)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode())
            return

        if self.path == "/submit_auto":
            if not self._check_auth():
                return

            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode())

            remote = data["remote"]
            stages = data.get("stages", "")
            sweeps = data.get("sweeps", "")
            exclude_stages = data.get("exclude_stages", "")
            exclude_sweeps = data.get("exclude_sweeps", "")

            try:
                if remote == "local":
                    stage_tools.validate_stage_resources()
                else:
                    from snap_workflow.utils.io import load_global_remotes, load_local_remotes
                    from snap_workflow.remote.setup import validate_remote_stage_resources, resolve_remote_path
                    global_remotes = load_global_remotes()
                    if remote not in global_remotes:
                        raise ValueError(f"Remote '{remote}' not registered globally.")
                    host = global_remotes[remote]["host"]
                    local_remotes = load_local_remotes()
                    if remote not in local_remotes:
                        raise ValueError(f"Remote '{remote}' not set up locally.")
                    r_path = local_remotes[remote]["path"]
                    resolved_r_path = resolve_remote_path(host, r_path)
                    validate_remote_stage_resources(host, resolved_r_path)
                    ensure_remote_tunnel(self.server, remote)
            except Exception as e:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode())
                return

            register_auto_scheduler(self.server, remote, stages, sweeps, exclude_stages, exclude_sweeps)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success"}).encode())
            return

        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": "Not Found"}).encode())


def run_server_foreground(host="127.0.0.1", port=0):
    root = path.get_root()
    info_path = os.path.join(root, SERVER_INFO)

    server = WorkflowServer((host, port), WorkflowRequestHandler)
    actual_port = server.server_address[1]
    url = f"http://{host}:{actual_port}"

    server_info = {
        "url": url,
        "token": server.token,
        "host": host,
        "port": actual_port,
        "pid": os.getpid()
    }

    with open(info_path, "w") as f:
        json.dump(server_info, f, indent=4)

    logger.info("[STARTUP] Manager server started on %s. Token: %s", url, server.token)
    print(f"Manager server is running on {url}")
    print("Press Ctrl+C to stop the manager server.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("[STARTUP] Manager server stopping...")
    finally:
        if hasattr(server, "schedulers"):
            for name, sched in server.schedulers.items():
                logger.info("[SCHEDULER] Stopping auto-scheduler thread for remote '%s'...", name)
                sched.shutdown_event.set()
        if hasattr(server, "active_tunnels"):
            for name, proc in server.active_tunnels.items():
                if proc and proc.poll() is None:
                    logger.info("[TUNNEL] Terminating active SSH reverse tunnel for remote '%s'...", name)
                    proc.terminate()
        server.server_close()
        if os.path.isfile(info_path):
            try:
                os.remove(info_path)
            except Exception:
                pass
        logger.info("[STARTUP] Manager server stopped.")
