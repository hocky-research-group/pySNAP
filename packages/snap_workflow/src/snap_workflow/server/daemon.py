import os
import sys
import json
import time
import queue
import secrets
import logging
import itertools
import threading
import subprocess
import socketserver
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

from snap_workflow.utils.constants import *
from snap_workflow.utils import path, io
from snap_workflow.core.domain import spoints as spoint_tools, stages as stage_tools, sweeps as sweep_tools
from snap_workflow.server.scheduler import SPointScheduler
from snap_workflow.utils.logging import logger
from snap_workflow.server.tunnels import ensure_remote_tunnel
from snap_workflow.dispatcher.controller import DispatcherController
from snap_workflow.remote.exec import has_slurm


def register_auto_scheduler(server, remote_name, stages="", sweeps="", exclude_stages="", exclude_sweeps="", profile="worker_profile"):
    if not hasattr(server, "dispatchers"):
        server.dispatchers = {}

    if remote_name in server.dispatchers:
        old_ctrl = server.dispatchers[remote_name]
        old_ctrl.stop()

    mode = "slurm" if has_slurm(remote_name) else "subprocess"
    actual_port = server.server_address[1] if hasattr(server, "server_address") else getattr(server, "server_port", 8080)
    controller = DispatcherController(
        target_name=remote_name,
        mode=mode,
        server_instance=server,
        server_port=actual_port,
        token=getattr(server, "token", None),
        stages=stages,
        sweeps=sweeps,
        exclude_stages=exclude_stages,
        exclude_sweeps=exclude_sweeps,
        profile=profile
    )
    server.dispatchers[remote_name] = controller
    controller.start()
    return controller


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

class PriorityJob:
    _counter = itertools.count()

    def __init__(self, priority: int, handler):
        self.priority = priority
        self.order = next(PriorityJob._counter)
        self.handler = handler
        self.done_event = threading.Event()
        self.response = None
        self.status_code = 200
        self.error = None

    def __lt__(self, other):
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.order < other.order


class WorkflowServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True

    def __init__(self, server_address, RequestHandlerClass, token=None):
        super().__init__(server_address, RequestHandlerClass)
        self.token = token or secrets.token_hex(16)
        self.spoint_manager = SPointScheduler()
        self.dispatchers = {}
        self.active_tunnels = {}
        self.task_queue = queue.PriorityQueue()
        self._shutdown_event = threading.Event()
        self.scheduler_worker = threading.Thread(target=self._process_scheduler_queue, daemon=True)
        self.scheduler_worker.start()

    def _process_scheduler_queue(self):
        while not self._shutdown_event.is_set():
            try:
                job = self.task_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                res = job.handler()
                if isinstance(res, tuple) and len(res) == 2:
                    job.response, job.status_code = res
                else:
                    job.response = res
                    job.status_code = 200
            except Exception as e:
                logger.error("Error executing scheduler job: %s", e, exc_info=True)
                job.error = e
                job.status_code = 500
                job.response = {"error": str(e)}
            finally:
                job.done_event.set()
                self.task_queue.task_done()

    def shutdown(self):
        self._shutdown_event.set()
        super().shutdown()

    def server_close(self):
        self._shutdown_event.set()
        super().server_close()


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

    def _submit_priority_job(self, priority: int, handler):
        if getattr(self.server, "_shutdown_event", None) and self.server._shutdown_event.is_set():
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Server shutting down"}).encode())
            return

        job = PriorityJob(priority, handler)
        self.server.task_queue.put(job)
        completed = job.done_event.wait(timeout=300)
        if not completed:
            self.send_response(504)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Gateway Timeout"}).encode())
            return

        status_code = getattr(job, "status_code", 200)
        response_data = getattr(job, "response", {})
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if isinstance(response_data, bytes):
            self.wfile.write(response_data)
        elif isinstance(response_data, str):
            self.wfile.write(response_data.encode())
        else:
            self.wfile.write(json.dumps(response_data).encode())

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/status":
            def _handle_status():
                return {
                    "status": "running",
                    "dispatchers": {k: d.get_status() for k, d in getattr(self.server, "dispatchers", {}).items()}
                }, 200
            self._submit_priority_job(0, _handle_status)
            return

        if parsed.path == "/shutdown":
            if not self._check_auth():
                return
            def _handle_shutdown():
                logger.info("[SERVER] Received shutdown request. Stopping manager server.")
                threading.Thread(target=self.server.shutdown).start()
                return {"status": "shutdown"}, 200
            self._submit_priority_job(0, _handle_shutdown)
            return

        if parsed.path == "/request_work":
            if not self._check_auth():
                return

            def _handle_request_work():
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

                logger.debug(
                    "[REQUEST_WORK] Dispatcher : %s | CPUs : %s | GPUs : %s | Mem : %.1f GB",
                    host, cpus_avail, gpu_avail, mem_avail
                )

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
                    return {"error": str(e)}, 500

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
                            self.server.spoint_manager.set_status(sweep_name, stage_name, spoint_dict, "initialized", host="local")
                            return {"error": f"Failed to push dependency data: {sync_e}"}, 500
                else:
                    all_complete = self.server.spoint_manager.are_all_complete(
                        allowed_stages=allowed_stages,
                        allowed_sweeps=allowed_sweeps,
                        exclude_stages=exclude_stages,
                        exclude_sweeps=exclude_sweeps
                    )
                    if all_complete:
                        logger.info("[SCHEDULER] All targeted tasks complete. Sending shutdown command to dispatcher '%s'.", host)
                        resp_data = {"status": "shutdown"}
                    else:
                        resp_data = {"status": "none"}

                return resp_data, 200

            self._submit_priority_job(1, _handle_request_work)
            return

        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": "Not Found"}).encode())

    def do_POST(self):
        if self.path in ("/update_status", "/notify_completion"):
            if not self._check_auth():
                return

            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode())

            def _handle_update_status():
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
                        try:
                            sp_path = spoint_tools.get_spoint_path(stage_name, spoint_dict)
                            status_module.write_status(status_val, sp_path)
                        except Exception as st_e:
                            logger.warning("Failed to write local status file for %s %s: %s", stage_name, spoint_dict, st_e)

                    if sweep_name and stage_name and spoint_dict:
                        self.server.spoint_manager.set_status(sweep_name, stage_name, spoint_dict, status_val, host=host)
                        vars_str = ", ".join(f"{k}={v}" for k, v in spoint_dict.items()) if isinstance(spoint_dict, dict) else str(spoint_dict)
                        logger.info("[DISPATCHER:%s] Report | Status: %s | Stage : %s | Spoint : %s", host, status_val, stage_name, vars_str)

                    if host != "local" and stage_name and spoint_dict:
                        try:
                            from snap_workflow.utils.io import load_global_remotes, load_local_remotes
                            from snap_workflow.remote.ssh import get_control_path_args
                            g_remotes = load_global_remotes()
                            l_remotes = load_local_remotes()
                            r_path = (l_remotes.get(host) or {}).get("path") or (g_remotes.get(host) or {}).get("path")
                            if r_path:
                                r_host = g_remotes.get(host, {}).get("host", host)
                                rel_sp = spoint_tools.get_spoint_path(stage_name, spoint_dict)
                                local_sp = rel_sp
                                r_path_clean = r_path.rstrip('/')
                                remote_sp = f"{r_path_clean}/{os.path.relpath(rel_sp, path.get_root())}"
                                sync_cmd = [
                                    "rsync", "-avz",
                                    "-e", "ssh " + " ".join(get_control_path_args()),
                                    f"{r_host}:{remote_sp}/", f"{local_sp}/"
                                ]
                                subprocess.run(sync_cmd, capture_output=True)
                                # Re-assert status on disk in case remote status differed
                                try:
                                    status_module.write_status(status_val, local_sp)
                                except Exception:
                                    pass
                        except Exception as sync_e:
                            logger.warning("Failed to sync back outputs on completion for %s: %s", stage_name, sync_e)
                except Exception as e:
                    logger.error("Failed to update status on completion notification: %s", e)
                    return {"error": str(e)}, 500

                return {"status": "ok"}, 200

            self._submit_priority_job(0, _handle_update_status)
            return

        if self.path == "/notify_shutdown":
            if not self._check_auth():
                return

            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode())

            def _handle_notify_shutdown():
                worker_id = data.get("worker_id", "unknown")
                host = data.get("host", "local")
                logger.info("[WORKER] Worker '%s' on host '%s' notified server of shutdown.", worker_id, host)
                return {"status": "ok"}, 200

            self._submit_priority_job(0, _handle_notify_shutdown)
            return

        if self.path == "/reserve":
            if not self._check_auth():
                return

            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode())

            def _handle_reserve():
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
                        from snap_workflow.dispatcher.controller import DispatcherController
                        controller = DispatcherController(
                            target_name="local",
                            mode="subprocess",
                            server_url=f"http://127.0.0.1:{self.server.server_port}",
                            token=self.server.token,
                            num_workers=num_workers,
                            stages=stages,
                            sweeps=sweeps,
                            exclude_stages=exclude_stages,
                            exclude_sweeps=exclude_sweeps,
                            profile=profile,
                            server_instance=self.server
                        )
                        controller.start()
                        self.server.dispatchers["local"] = controller
                        msg = f"Successfully spawned {num_workers} local worker process(es)."
                    else:
                        ensure_remote_tunnel(self.server, name)
                        from snap_workflow.remote.reserve import reserve_remote_workers
                        reserve_remote_workers(
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

                    return {"status": "success", "message": msg}, 200
                except Exception as e:
                    logger.error("Failed to submit worker: %s", e)
                    return {"status": "error", "message": str(e)}, 200

            self._submit_priority_job(1, _handle_reserve)
            return

        if self.path == "/auto":
            if not self._check_auth():
                return

            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode())

            def _handle_auto():
                remote = data["remote"]
                stages = data.get("stages", "")
                sweeps = data.get("sweeps", "")
                exclude_stages = data.get("exclude_stages", "")
                exclude_sweeps = data.get("exclude_sweeps", "")

                try:
                    if remote == "local":
                        stage_tools.validate_stage_resources()
                    else:
                        from snap_workflow.remote.exec import get_remote_host, get_remote_path
                        from snap_workflow.remote.setup import validate_remote_stage_resources
                        host = get_remote_host(remote)
                        r_path = get_remote_path(remote)
                        validate_remote_stage_resources(host, r_path)
                        ensure_remote_tunnel(self.server, remote)
                except Exception as e:
                    return {"status": "error", "message": str(e)}, 200

                register_auto_scheduler(self.server, remote, stages, sweeps, exclude_stages, exclude_sweeps)
                return {"status": "success"}, 200

            self._submit_priority_job(1, _handle_auto)
            return

        if self.path == "/stop":
            if not self._check_auth():
                return

            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode())

            def _handle_stop():
                target = data.get("target")
                force = bool(data.get("force", False))

                if not target:
                    return {"status": "error", "message": "Target parameter is required."}, 400

                stopped_items = []
                if target == "all":
                    for name, ctrl in list(getattr(self.server, "dispatchers", {}).items()):
                        ctrl.stop(force=force)
                        stopped_items.append(f"dispatcher '{name}'")
                    self.server.dispatchers.clear()

                    if force:
                        for name, proc in list(getattr(self.server, "active_tunnels", {}).items()):
                            if proc and proc.poll() is None:
                                proc.terminate()
                        self.server.active_tunnels.clear()

                    msg = f"Stopped all active targets ({', '.join(stopped_items) if stopped_items else 'none active'})."
                else:
                    if target in getattr(self.server, "dispatchers", {}):
                        ctrl = self.server.dispatchers.pop(target)
                        ctrl.stop(force=force)
                        stopped_items.append(f"dispatcher '{target}'")

                    if force and target in getattr(self.server, "active_tunnels", {}):
                        proc = self.server.active_tunnels.pop(target)
                        if proc and proc.poll() is None:
                            proc.terminate()

                    if stopped_items:
                        msg = f"Successfully stopped {', '.join(stopped_items)}."
                    else:
                        msg = f"No active dispatcher found for target '{target}'."

                return {"status": "success", "message": msg}, 200

            self._submit_priority_job(1, _handle_stop)
            return

        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": "Not Found"}).encode())


def run_server_foreground(host="127.0.0.1", port=0, debug=False):
    from snap_workflow.utils.logging import setup_logging
    if debug:
        setup_logging(level=logging.DEBUG)

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
        if hasattr(server, "dispatchers"):
            for name, ctrl in list(server.dispatchers.items()):
                logger.info("[DISPATCHER] Stopping dispatcher for target '%s'...", name)
                try:
                    ctrl.stop()
                except Exception:
                    pass
        if hasattr(server, "active_tunnels"):
            for name, proc in list(server.active_tunnels.items()):
                if proc and proc.poll() is None:
                    logger.info("[TUNNEL] Terminating active SSH reverse tunnel for remote '%s'...", name)
                    try:
                        proc.terminate()
                    except Exception:
                        pass
        server.server_close()
        if os.path.isfile(info_path):
            try:
                os.remove(info_path)
            except Exception:
                pass
        logger.info("[STARTUP] Manager server stopped.")
