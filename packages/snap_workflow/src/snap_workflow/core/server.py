import json
import secrets
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import sys
import os
import subprocess
import time

from .strings import *
from . import spoints
from . import status
from . import sweeps as sweep_tools
from . import stages as stage_tools
from . import path
from . import io
from .logging_config import logger, setup_logging
from urllib.parse import urlparse, parse_qs
from . import sync

METADATA_LOCK = threading.Lock()

def load_spoint_metadata():
    root = path.get_root()
    metadata_file = os.path.join(root, ".workflow", "spoint_metadata.json")
    if os.path.isfile(metadata_file):
        try:
            with open(metadata_file, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_spoint_metadata(metadata):
    root = path.get_root()
    metadata_file = os.path.join(root, ".workflow", "spoint_metadata.json")
    try:
        with open(metadata_file, "w") as f:
            json.dump(metadata, f, indent=4)
    except Exception as e:
        logger.error("Failed to save spoint_metadata.json: %s", e)

def update_spoint_metadata(spoint_rel_path, host, size_bytes):
    with METADATA_LOCK:
        metadata = load_spoint_metadata()
        metadata[spoint_rel_path] = {"host": host, "size_bytes": size_bytes}
        save_spoint_metadata(metadata)

def get_remote_conn(remote_name):
    if remote_name == "local":
        return "local", None, None
    try:
        from ..cli import load_global_remotes, load_local_remotes
        global_remotes = load_global_remotes()
        local_remotes = load_local_remotes()
        if remote_name in global_remotes and remote_name in local_remotes:
            return "remote", global_remotes[remote_name]["host"], local_remotes[remote_name]["path"]
    except Exception:
        pass
    return None, None, None

def get_dependency_rel_paths(sweep_name, stage_name, spoint_dict):
    dep_stages = spoints.get_dependent_spoint_info(stage_name, sweep_name, spoint_dict)
    rel_paths = []
    for dep_stage, info in dep_stages.items():
        prop_vars = info["prop_vars"]
        conv_vars = info["conv_vars"]
        dep_dict = {var: spoint_dict[var] for var in prop_vars}
        if len(conv_vars) == 0:
            sp_str = spoints.get_spoint_string(dep_dict)
            rel_paths.append(f"{dep_stage}/{SPOINTS}/{sp_str}")
        else:
            for conv in info["conv_combos"]:
                conv_dict = {var: val for var, val in zip(conv_vars, conv)}
                combined = {**dep_dict, **conv_dict}
                sp_str = spoints.get_spoint_string(combined)
                rel_paths.append(f"{dep_stage}/{SPOINTS}/{sp_str}")
    return rel_paths

def check_data_locality_eligibility(sweep_name, stage_name, spoint_dict, target_host):
    dep_rel_paths = get_dependency_rel_paths(sweep_name, stage_name, spoint_dict)
    syncs_needed = []
    metadata = load_spoint_metadata()
    for dep_rel_path in dep_rel_paths:
        entry = metadata.get(dep_rel_path, {"host": "local", "size_bytes": 0})
        source_host = entry.get("host", "local")
        size_bytes = entry.get("size_bytes", 0)
        if source_host != target_host:
            if size_bytes > 1_000_000_000:
                return False, "deferred", (dep_rel_path, source_host, size_bytes)
            else:
                syncs_needed.append((dep_rel_path, source_host, size_bytes))
    if syncs_needed:
        return True, "sync_needed", syncs_needed
    return True, "runnable", []

def resolve_deadlock_host(sweep_name, stage_name, spoint_dict):
    from ..cli import load_global_remotes
    try:
        remotes = list(load_global_remotes().keys())
    except Exception:
        remotes = []
    all_hosts = ["local"] + remotes
    dep_rel_paths = get_dependency_rel_paths(sweep_name, stage_name, spoint_dict)
    metadata = load_spoint_metadata()
    best_host = "local"
    max_local_size = -1
    best_syncs = []
    for host in all_hosts:
        local_size = 0
        syncs = []
        for dep_rel_path in dep_rel_paths:
            entry = metadata.get(dep_rel_path, {"host": "local", "size_bytes": 0})
            src_host = entry.get("host", "local")
            sz = entry.get("size_bytes", 0)
            if src_host == host:
                local_size += sz
            else:
                syncs.append((dep_rel_path, src_host, sz))
        if local_size > max_local_size:
            max_local_size = local_size
            best_host = host
            best_syncs = syncs
    return best_host, best_syncs
def check_and_prepare_dependencies(sweep_name, stage_name, spoint_dict, target_host):
    if not spoints.check_submittable(sweep_name, stage_name, spoint_dict):
        return False
    is_runnable, status_str, detail = check_data_locality_eligibility(sweep_name, stage_name, spoint_dict, target_host)
    syncs_needed = []
    if not is_runnable:
        from ..cli import load_global_remotes
        try:
            remotes = list(load_global_remotes().keys())
        except Exception:
            remotes = []
        all_hosts = ["local"] + remotes
        is_deadlock = True
        for h in all_hosts:
            h_runnable, _, _ = check_data_locality_eligibility(sweep_name, stage_name, spoint_dict, h)
            if h_runnable:
                is_deadlock = False
                break
        if is_deadlock:
            best_host, best_syncs = resolve_deadlock_host(sweep_name, stage_name, spoint_dict)
            if best_host == target_host:
                logger.warning("Multi-parent dependency deadlock detected for stage %s dict %s. Resolving by choosing host '%s' and forcing transit syncs.",
                               stage_name, spoint_dict, target_host)
                syncs_needed = best_syncs
            else:
                return False
        else:
            return False
    else:
        if status_str == "sync_needed":
            syncs_needed = detail
    if syncs_needed:
        dest_type, dest_ssh_host, dest_path = get_remote_conn(target_host)
        for dep_rel_path, src_host, sz in syncs_needed:
            src_type, src_ssh_host, src_path = get_remote_conn(src_host)
            dep_stage = dep_rel_path.split(os.sep)[0] if os.sep in dep_rel_path else dep_rel_path.split("/")[0]
            sync.transit_sync_dependency(
                source_remote=src_type,
                source_host=src_ssh_host,
                source_path=src_path,
                dest_remote=dest_type,
                dest_host=dest_ssh_host,
                dest_path=dest_path,
                dep_rel_path=dep_rel_path,
                stage_name=dep_stage
            )
    return True


class WorkflowRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        logger.info("%s - - %s", self.address_string(), format % args)

    def _check_auth(self):
        auth_header = self.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"Unauthorized")
            return False
        token = auth_header.split(" ")[1]
        if token != self.server.token:
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"Unauthorized")
            return False
        return True

    def do_GET(self):
        if self.path == "/shutdown":
            if not self._check_auth():
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "shutdown"}).encode())
            threading.Thread(target=self.server.shutdown).start()
            return

        if self.path.startswith("/request_work"):
            if not self._check_auth():
                return
            
            parsed_url = urlparse(self.path)
            q_params = parse_qs(parsed_url.query)
            worker_host = q_params.get("host", ["local"])[0]
            
            try:
                cpus_avail = int(q_params.get("cpus_avail", ["999"])[0])
            except ValueError:
                cpus_avail = 999
            try:
                gpu_avail = int(q_params.get("gpu_avail", ["-1"])[0])
            except ValueError:
                gpu_avail = -1
            try:
                mem_avail = float(q_params.get("mem_avail", ["999.0"])[0])
            except ValueError:
                mem_avail = 999.0
            try:
                min_cpu_running_gpu = int(q_params.get("min_cpu_running_gpu", ["0"])[0])
            except ValueError:
                min_cpu_running_gpu = 0
                
            # Parse constraint query parameters
            stages_str = q_params.get("stages", [""])[0]
            sweeps_str = q_params.get("sweeps", [""])[0]
            ex_stages_str = q_params.get("exclude_stages", [""])[0]
            ex_sweeps_str = q_params.get("exclude_sweeps", [""])[0]
            
            allowed_stages = {x.strip() for x in stages_str.split(",") if x.strip()}
            allowed_sweeps = {x.strip() for x in sweeps_str.split(",") if x.strip()}
            exclude_stages = {x.strip() for x in ex_stages_str.split(",") if x.strip()}
            exclude_sweeps = {x.strip() for x in ex_sweeps_str.split(",") if x.strip()}
            
            stages_dict = stage_tools.load_stages()
            sweeps_dict = sweep_tools.load_sweeps()
            root_dir = path.get_root()
            
            # Determine stage iteration order: sort stages by depth descending
            cache = {}
            sorted_stages = sorted(
                stages_dict.keys(),
                key=lambda name: get_stage_depth(name, stages_dict, cache),
                reverse=True
            )
            
            # Filter sweeps & stages for this worker
            target_sweeps = list(sweeps_dict.keys())
            if allowed_sweeps:
                target_sweeps = [s for s in target_sweeps if s in allowed_sweeps]
            if exclude_sweeps:
                target_sweeps = [s for s in target_sweeps if s not in exclude_sweeps]
                
            target_stages = list(sorted_stages)
            if allowed_stages:
                target_stages = [s for s in target_stages if s in allowed_stages]
            if exclude_stages:
                target_stages = [s for s in target_stages if s not in exclude_stages]
            
            stage_resources = {}
            for st_name in list(stages_dict.keys()):
                env_base = os.path.join(root_dir, st_name, "env")
                req_cpus = 1
                req_gpus = 0
                req_mem = 0.0
                try:
                    env_data = io.load_config(env_base, full_path=True)
                    res = env_data.get("resources", {})
                    req_cpus = int(res.get("cpus", 1))
                    req_gpus = int(res.get("gpus", 0))
                    req_mem = parse_memory_to_gb(res.get("mem", "0"))
                except Exception:
                    pass
                stage_resources[st_name] = {"cpus": req_cpus, "gpus": req_gpus, "mem": req_mem}
                
            # Scan all spoints to count incomplete tasks and find max_gpu_task_cpu_req
            any_incomplete_cpu = False
            any_incomplete_gpu = False
            max_gpu_task_cpu_req = 0
            
            for sweep_name, stage_name, spoint_dict in spoints.iter_spoints(sweep_names=target_sweeps, stage_names=target_stages):
                spoint_path = spoints.get_spoint_path(stage_name, spoint_dict)
                st = status.load_status(spoint_path)
                if st not in [COMPLETE, ERROR]:
                    res = stage_resources.get(stage_name, {"cpus": 1, "gpus": 0, "mem": 0.0})
                    if res["gpus"] > 0:
                        any_incomplete_gpu = True
                        if res["cpus"] > max_gpu_task_cpu_req:
                            max_gpu_task_cpu_req = res["cpus"]
                    else:
                        any_incomplete_cpu = True
                        
            assigned_spoint = None
            
            if gpu_avail == -1:
                # cWorker: CPU-only tasks
                for sweep_name, stage_name, spoint_dict in spoints.iter_spoints(sweep_names=target_sweeps, stage_names=target_stages):
                    res = stage_resources.get(stage_name, {"cpus": 1, "gpus": 0, "mem": 0.0})
                    if res["gpus"] == 0 and res["cpus"] <= cpus_avail and res["mem"] <= mem_avail:
                        if check_and_prepare_dependencies(sweep_name, stage_name, spoint_dict, worker_host):
                            spoint_path = spoints.get_spoint_path(stage_name, spoint_dict)
                            status.write_status(SUBMITTED, spoint_path)
                            assigned_spoint = {
                                "status": "combo",
                                "sweep": sweep_name,
                                "stage": stage_name,
                                "combo_dict": spoint_dict,
                                "combo_path": spoint_path
                            }
                            break
                            
                # Shutdown logic for cWorker:
                if assigned_spoint is None:
                    if not any_incomplete_cpu:
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps({"status": "shutdown"}).encode())
                        return
            else:
                # gWorker: GPU and CPU backfill tasks
                # Step 1: if gpu_avail > 0, prioritize GPU tasks
                if gpu_avail > 0:
                    for sweep_name, stage_name, spoint_dict in spoints.iter_spoints(sweep_names=target_sweeps, stage_names=target_stages):
                        res = stage_resources.get(stage_name, {"cpus": 1, "gpus": 0, "mem": 0.0})
                        if res["gpus"] > 0 and res["gpus"] <= gpu_avail and res["cpus"] <= cpus_avail and res["mem"] <= mem_avail:
                            if check_and_prepare_dependencies(sweep_name, stage_name, spoint_dict, worker_host):
                                spoint_path = spoints.get_spoint_path(stage_name, spoint_dict)
                                status.write_status(SUBMITTED, spoint_path)
                                assigned_spoint = {
                                    "status": "combo",
                                    "sweep": sweep_name,
                                    "stage": stage_name,
                                    "combo_dict": spoint_dict,
                                    "combo_path": spoint_path
                                }
                                break
                                
                # Step 2: CPU backfilling
                if assigned_spoint is None:
                    if any_incomplete_gpu:
                        # Find a submittable CPU task that fits within remaining resources
                        for sweep_name, stage_name, spoint_dict in spoints.iter_spoints(sweep_names=target_sweeps, stage_names=target_stages):
                            res = stage_resources.get(stage_name, {"cpus": 1, "gpus": 0, "mem": 0.0})
                            if res["gpus"] == 0 and res["cpus"] <= cpus_avail and res["mem"] <= mem_avail:
                                # Apply the reservation check
                                if cpus_avail - res["cpus"] + min_cpu_running_gpu >= max_gpu_task_cpu_req:
                                    if check_and_prepare_dependencies(sweep_name, stage_name, spoint_dict, worker_host):
                                        spoint_path = spoints.get_spoint_path(stage_name, spoint_dict)
                                        status.write_status(SUBMITTED, spoint_path)
                                        assigned_spoint = {
                                            "status": "combo",
                                            "sweep": sweep_name,
                                            "stage": stage_name,
                                            "combo_dict": spoint_dict,
                                            "combo_path": spoint_path
                                        }
                                        break
                    else:
                        # Shutdown logic for gWorker:
                        # Only shut down if a GPU is idle and no future GPU tasks remain
                        if gpu_avail > 0:
                            self.send_response(200)
                            self.send_header("Content-Type", "application/json")
                            self.end_headers()
                            self.wfile.write(json.dumps({"status": "shutdown"}).encode())
                            return
                            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if assigned_spoint:
                if worker_host != "local":
                    try:
                        from ..cli import load_local_remotes, load_global_remotes
                        global_remotes = load_global_remotes()
                        local_remotes = load_local_remotes()
                        if worker_host in global_remotes and worker_host in local_remotes:
                            h = global_remotes[worker_host]["host"]
                            p = local_remotes[worker_host]["path"]
                            rel_path = os.path.relpath(os.path.realpath(assigned_spoint["combo_path"]), os.path.realpath(root_dir))
                            sync.push_dependency_data(worker_host, h, p, rel_path)
                    except Exception as e:
                        logger.error("Failed to push spoint data to worker %s: %s", worker_host, e)
                self.wfile.write(json.dumps(assigned_spoint).encode())
            else:
                self.wfile.write(json.dumps({"status": "idle"}).encode())
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path == "/notify_completion":
            if not self._check_auth():
                return

            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode())

            sweep_name = data["sweep"]
            stage_name = data["stage"]
            spoint_dict = data.get("combo_dict", data.get("spoint_dict"))
            spoint_status = data["status"]
            worker_host = data.get("host", "local")

            spoint_path = spoints.get_spoint_path(stage_name, spoint_dict)
            status.write_status(spoint_status, spoint_path)

            if spoint_status == COMPLETE:
                spoint_rel_path = os.path.relpath(spoint_path, path.get_root())
                remote_type, ssh_host, remote_path = get_remote_conn(worker_host)
                sz = sync.measure_directory_size(remote_type, ssh_host, remote_path, spoint_rel_path)
                update_spoint_metadata(spoint_rel_path, worker_host, sz)
                sync.pull_spoint_data(remote_type, ssh_host, remote_path, spoint_rel_path, stage_name)

                dep_info = spoints.get_dependent_spoint_info(stage_name, sweep_name, spoint_dict)
                spoints.link_dependent_combo(stage_name, spoint_dict, dep_info)

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

            worker_host = data.get("host", "local")
            worker_id = data.get("worker_id")

            try:
                remote_type, ssh_host, remote_path = get_remote_conn(worker_host)
                if remote_type != "local":
                    logger.info("Worker %s on %s is shutting down. Pulling worker logs...", worker_id, worker_host)
                    sync.pull_worker_logs(remote_type, ssh_host, remote_path)
                else:
                    logger.info("Local worker %s is shutting down. No pull needed.", worker_id)
            except Exception as e:
                logger.error("Failed to handle worker shutdown notification: %s", e)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
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

            register_auto_scheduler(self.server, remote, stages, sweeps, exclude_stages, exclude_sweeps)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success"}).encode())
            return

class OrchestratorScheduler(threading.Thread):
    def __init__(self, remote, stages="", sweeps="", exclude_stages="", exclude_sweeps=""):
        super().__init__()
        self.remote = remote
        self.stages_csv = stages
        self.sweeps_csv = sweeps
        self.exclude_stages_csv = exclude_stages
        self.exclude_sweeps_csv = exclude_sweeps
        self.shutdown_event = threading.Event()

    def run(self):
        logger.info("Starting auto-scheduler for remote '%s'...", self.remote)
        
        host = None
        remote_path = None
        
        if self.remote != "local":
            try:
                from ..cli import load_global_remotes, load_local_remotes
                global_remotes = load_global_remotes()
                if self.remote not in global_remotes:
                    logger.error("Remote '%s' not registered globally.", self.remote)
                    return
                host = global_remotes[self.remote]["host"]
                
                local_remotes = load_local_remotes()
                if self.remote not in local_remotes:
                    logger.error("Remote '%s' not set up locally.", self.remote)
                    return
                remote_path = local_remotes[self.remote]["path"]
            except Exception as e:
                logger.error("Failed to load remote connection config: %s", e)
                return

        # 1. Dynamically check if Slurm/sbatch is available
        has_slurm = False
        try:
            if self.remote == "local":
                res = subprocess.run(["which", "sbatch"], capture_output=True, text=True)
                has_slurm = (res.returncode == 0)
            else:
                res = subprocess.run(["ssh", host, "which sbatch"], capture_output=True, text=True)
                has_slurm = (res.returncode == 0)
        except Exception:
            pass

        logger.info("Remote '%s' Slurm detection: has_slurm=%s", self.remote, has_slurm)

        if not has_slurm:
            other_scheduler_detected = False
            detected_cmd = None
            for cmd in ["qsub", "bsub", "qstat"]:
                try:
                    if self.remote == "local":
                        check_res = subprocess.run(["which", cmd], capture_output=True, text=True)
                        exists = (check_res.returncode == 0)
                    else:
                        check_res = subprocess.run(["ssh", host, f"which {cmd}"], capture_output=True, text=True)
                        exists = (check_res.returncode == 0)
                    if exists:
                        other_scheduler_detected = True
                        detected_cmd = cmd
                        break
                except Exception:
                    pass
            if other_scheduler_detected:
                logger.error("Non-Slurm scheduler utility '%s' detected on remote '%s'. Aborting execution to prevent direct runs on cluster login nodes.",
                             detected_cmd, self.remote)
                return

        # Parse CSV options
        allowed_stages = {x.strip() for x in self.stages_csv.split(",") if x.strip()}
        allowed_sweeps = {x.strip() for x in self.sweeps_csv.split(",") if x.strip()}
        exclude_stages = {x.strip() for x in self.exclude_stages_csv.split(",") if x.strip()}
        exclude_sweeps = {x.strip() for x in self.exclude_sweeps_csv.split(",") if x.strip()}

        # Load stages and sweeps to configure iteration order
        stages_dict = stage_tools.load_stages()
        sweeps_dict = sweep_tools.load_sweeps()
        root_dir = path.get_root()

        # Sort stages by depth descending
        cache = {}
        sorted_stages = sorted(
            stages_dict.keys(),
            key=lambda name: get_stage_depth(name, stages_dict, cache),
            reverse=True
        )

        target_sweeps = list(sweeps_dict.keys())
        if allowed_sweeps:
            target_sweeps = [s for s in target_sweeps if s in allowed_sweeps]
        if exclude_sweeps:
            target_sweeps = [s for s in target_sweeps if s not in exclude_sweeps]

        target_stages = list(sorted_stages)
        if allowed_stages:
            target_stages = [s for s in target_stages if s in allowed_stages]
        if exclude_stages:
            target_stages = [s for s in target_stages if s not in exclude_stages]

        # Load stage resource requirements
        stage_resources = {}
        for st_name in list(stages_dict.keys()):
            env_base = os.path.join(root_dir, st_name, "env")
            try:
                env_data = io.load_config(env_base, full_path=True)
                res_cfg = env_data.get("resources", {})
                stage_resources[st_name] = {
                    "cpus": int(res_cfg.get("cpus", 1)),
                    "gpus": int(res_cfg.get("gpus", 0)),
                    "mem": parse_memory_to_gb(res_cfg.get("mem", "1G"))
                }
            except Exception:
                stage_resources[st_name] = {"cpus": 1, "gpus": 0, "mem": 1.0}

        # Workstation Mode attributes
        cpus_total = 8
        gpus_total = 0
        mem_total = 16.0
        active_jobs = []

        if not has_slurm:
            # Query target workstation resources
            if self.remote == "local":
                from .worker import detect_system_resources
                cpus_total, gpus_total, mem_total = detect_system_resources()
            else:
                try:
                    cmd = ["ssh", host, "python3 -c \"import json; from snap_workflow.core.worker import detect_system_resources; print(json.dumps(detect_system_resources()))\" || python -c \"import json; from snap_workflow.core.worker import detect_system_resources; print(json.dumps(detect_system_resources()))\""]
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                    if res.returncode == 0:
                        cpus_total, gpus_total, mem_total = json.loads(res.stdout.strip())
                except Exception as e:
                    logger.warning("Failed to auto-detect remote resources: %s. Using default baseline constraints.", e)
            logger.info("Workstation capacity for remote '%s': CPUs=%s, GPUs=%s, Memory=%.2f GB",
                        self.remote, cpus_total, gpus_total, mem_total)

        while not self.shutdown_event.is_set():
            if has_slurm:
                # auto-submit loop
                # A. Poll remote status for submitted jobs
                for sweep_name, stage_name, spoint_dict in spoints.iter_spoints(sweep_names=target_sweeps, stage_names=target_stages):
                    spoint_path = spoints.get_spoint_path(stage_name, spoint_dict)
                    if status.load_status(spoint_path) == status.SUBMITTED:
                        spoint_rel_path = os.path.relpath(spoint_path, root_dir)
                        if self.remote == "local":
                            rem_st = status.load_status(spoint_path)
                        else:
                            try:
                                cat_cmd = f"cat {remote_path}/{spoint_rel_path}/.spoint_info/status"
                                res_st = subprocess.run(["ssh", host, cat_cmd], capture_output=True, text=True, timeout=5)
                                rem_st = res_st.stdout.strip() if res_st.returncode == 0 else status.SUBMITTED
                            except Exception:
                                rem_st = status.SUBMITTED
                        if rem_st in [status.COMPLETE, status.ERROR]:
                            remote_type, ssh_host, r_path = get_remote_conn(self.remote)
                            sz = sync.measure_directory_size(remote_type, ssh_host, r_path, spoint_rel_path)
                            update_spoint_metadata(spoint_rel_path, self.remote, sz)
                            sync.pull_spoint_data(remote_type, ssh_host, r_path, spoint_rel_path, stage_name)
                            status.write_status(rem_st, spoint_path)
                            if rem_st == status.COMPLETE:
                                dep_info = spoints.get_dependent_spoint_info(stage_name, sweep_name, spoint_dict)
                                spoints.link_dependent_combo(stage_name, spoint_dict, dep_info)
                                logger.info("Remote Slurm job completed for stage %s: %s", stage_name, spoint_path)
                            else:
                                logger.error("Remote Slurm job failed for stage %s: %s", stage_name, spoint_path)

                # B. Submit new jobs
                for sweep_name, stage_name, spoint_dict in spoints.iter_spoints(sweep_names=target_sweeps, stage_names=target_stages):
                    if self.shutdown_event.is_set():
                        break
                    spoint_path = spoints.get_spoint_path(stage_name, spoint_dict)
                    st = status.load_status(spoint_path)
                    if st != status.INITIALIZED:
                        continue
                    if not check_and_prepare_dependencies(sweep_name, stage_name, spoint_dict, self.remote):
                        continue

                    # Submit job via sbatch
                    stage = stages_dict[stage_name]
                    submit_details = spoints.get_submission_details(stage_name, stage)
                    if submit_details is None:
                        sbatch_flags = {}
                    else:
                        sbatch_flags = submit_details.get("sbatch_flags", {})

                    if self.remote == "local":
                        spoint_arg = os.path.realpath(spoint_path)
                        sbatch_command = ["sbatch"] + spoints.convert_sbatch_flags(sbatch_flags) + [".workflow/spoint.sh", spoint_arg]
                        res = subprocess.run(sbatch_command, capture_output=True, text=True)
                    else:
                        rel_path = os.path.relpath(os.path.realpath(spoint_path), os.path.realpath(root_dir))
                        remote_spoint_arg = os.path.join(remote_path, rel_path)
                        sbatch_args_list = spoints.convert_sbatch_flags(sbatch_flags)
                        sbatch_args_str = " ".join(sbatch_args_list)
                        sbatch_command = ["ssh", host, f"cd {remote_path} && sbatch {sbatch_args_str} .workflow/spoint.sh {remote_spoint_arg}"]
                        res = subprocess.run(sbatch_command, capture_output=True, text=True)

                    if res.returncode == 0:
                        status.write_status(status.SUBMITTED, spoint_path)
                        logger.info("Auto-submitted Slurm job for stage %s: %s", stage_name, spoint_path)
                    else:
                        logger.error("Auto-submit failed for %s (exit code %s): %s", spoint_path, res.returncode, res.stderr)

            else:
                # auto-run workstation loop
                still_active = []
                for job in active_jobs:
                    poll = job["proc"].poll()
                    if poll is not None:
                        st = status.load_status(job["spoint_path"])
                        if st not in [status.COMPLETE, status.ERROR]:
                            if poll == 0:
                                status.write_status(status.COMPLETE, job["spoint_path"])
                                spoint_rel_path = os.path.relpath(job["spoint_path"], root_dir)
                                remote_type, ssh_host, r_path = get_remote_conn(self.remote)
                                sz = sync.measure_directory_size(remote_type, ssh_host, r_path, spoint_rel_path)
                                update_spoint_metadata(spoint_rel_path, self.remote, sz)
                                sync.pull_spoint_data(remote_type, ssh_host, r_path, spoint_rel_path, job["stage"])
                                dep_info = spoints.get_dependent_spoint_info(job["stage"], job["sweep"], job["spoint_dict"])
                                spoints.link_dependent_combo(job["stage"], job["spoint_dict"], dep_info)
                                logger.info("Workstation run completed for stage %s: %s", job["stage"], job["spoint_path"])
                            else:
                                status.write_status(status.ERROR, job["spoint_path"])
                                logger.error("Workstation run failed (exit code %s) for stage %s: %s", poll, job["stage"], job["spoint_path"])
                    else:
                        still_active.append(job)
                active_jobs = still_active

                # Check available resources
                used_cpus = sum(j["cpus"] for j in active_jobs)
                used_mem = sum(j["mem"] for j in active_jobs)
                used_gpu_indices = set().union(*(j["gpu_indices"] for j in active_jobs))
                
                avail_cpus = cpus_total - used_cpus
                avail_mem = mem_total - used_mem
                avail_gpu_indices = set(range(max(0, gpus_total))) - used_gpu_indices

                for sweep_name, stage_name, spoint_dict in spoints.iter_spoints(sweep_names=target_sweeps, stage_names=target_stages):
                    if self.shutdown_event.is_set():
                        break
                    spoint_path = spoints.get_spoint_path(stage_name, spoint_dict)
                    st = status.load_status(spoint_path)
                    if st != status.INITIALIZED:
                        continue
                    if not check_and_prepare_dependencies(sweep_name, stage_name, spoint_dict, self.remote):
                        continue

                    req = stage_resources[stage_name]
                    if req["cpus"] <= avail_cpus and req["mem"] <= avail_mem and req["gpus"] <= len(avail_gpu_indices):
                        allocated_gpus = []
                        if req["gpus"] > 0:
                            allocated_gpus = list(avail_gpu_indices)[:req["gpus"]]
                            for g in allocated_gpus:
                                avail_gpu_indices.remove(g)

                        # Spawn simulation process
                        cuda_str = ",".join(str(g) for g in allocated_gpus)
                        if self.remote == "local":
                            env = os.environ.copy()
                            if req["gpus"] > 0:
                                env["CUDA_VISIBLE_DEVICES"] = cuda_str
                            cmd = ["bash", ".workflow/spoint.sh", os.path.realpath(spoint_path)]
                            proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        else:
                            rel_path = os.path.relpath(os.path.realpath(spoint_path), os.path.realpath(root_dir))
                            sync.push_dependency_data(self.remote, host, remote_path, rel_path)
                            remote_spoint_arg = os.path.join(remote_path, rel_path)
                            export_str = f"export CUDA_VISIBLE_DEVICES={cuda_str} && " if req["gpus"] > 0 else ""
                            cmd = ["ssh", host, f"cd {remote_path} && {export_str}bash .workflow/spoint.sh {remote_spoint_arg}"]
                            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                        status.write_status(status.RUNNING, spoint_path)
                        logger.info("Auto-run workstation process spawned for stage %s: %s (assigned GPUs %s)",
                                    stage_name, spoint_path, allocated_gpus)
                                    
                        active_jobs.append({
                            "spoint_path": spoint_path,
                            "proc": proc,
                            "cpus": req["cpus"],
                            "mem": req["mem"],
                            "gpus": req["gpus"],
                            "gpu_indices": set(allocated_gpus),
                            "sweep": sweep_name,
                            "stage": stage_name,
                            "spoint_dict": spoint_dict
                        })
                        avail_cpus -= req["cpus"]
                        avail_mem -= req["mem"]

            time.sleep(3)

        for job in active_jobs:
            try:
                job["proc"].terminate()
            except Exception:
                pass

def register_auto_scheduler(server, remote, stages="", sweeps="", exclude_stages="", exclude_sweeps=""):
    if not hasattr(server, "auto_schedulers"):
        server.auto_schedulers = {}
        
    if remote in server.auto_schedulers:
        thread = server.auto_schedulers[remote]
        if thread.is_alive():
            logger.info("Auto-scheduler for remote '%s' is already running.", remote)
            return
            
    thread = OrchestratorScheduler(remote, stages, sweeps, exclude_stages, exclude_sweeps)
    server.auto_schedulers[remote] = thread
    thread.daemon = True
    thread.start()

def start_server(host="127.0.0.1", port=0):
    stage_tools.validate_stage_resources()
    root = path.get_root()
    token = secrets.token_hex(16)
    
    os.makedirs(os.path.join(root, ".workflow"), exist_ok=True)
    setup_logging(log_file=os.path.join(root, SERVER_LOG))

    server = HTTPServer((host, port), WorkflowRequestHandler)
    server.token = token
    actual_port = server.server_port
    
    server_info = {
        "host": host,
        "port": actual_port,
        "token": token,
        "url": f"http://{host}:{actual_port}"
    }
    
    with open(os.path.join(root, SERVER_INFO), "w") as f:
        json.dump(server_info, f)
        
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    
    return server, server_info

def run_server_foreground(host="127.0.0.1", port=0):
    stage_tools.validate_stage_resources()
    root = path.get_root()
    token = secrets.token_hex(16)
    
    os.makedirs(os.path.join(root, ".workflow"), exist_ok=True)
    setup_logging(log_file=os.path.join(root, SERVER_LOG))

    server = HTTPServer((host, port), WorkflowRequestHandler)
    server.token = token
    actual_port = server.server_port
    
    server_info = {
        "host": host,
        "port": actual_port,
        "token": token,
        "url": f"http://{host}:{actual_port}"
    }
    
    with open(os.path.join(root, SERVER_INFO), "w") as f:
        json.dump(server_info, f)
        
    logger.info("Workflow Manager Server running at http://%s:%s", host, actual_port)
    logger.info("Press Ctrl+C to stop.")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping server...")
    finally:
        if hasattr(server, "auto_schedulers"):
            for remote_name, thread in server.auto_schedulers.items():
                logger.info("Stopping auto-scheduler for remote '%s'...", remote_name)
                thread.shutdown_event.set()
                thread.join(timeout=2)
        server.server_close()
        info_file = os.path.join(root, SERVER_INFO)
        if os.path.exists(info_file):
            os.remove(info_file)


def parse_memory_to_gb(mem_str):
    if not mem_str:
        return 0.0
    mem_str = str(mem_str).strip().upper()
    try:
        if mem_str.endswith("GB") or mem_str.endswith("G"):
            val = mem_str.rstrip("GBG")
            return float(val)
        elif mem_str.endswith("MB") or mem_str.endswith("M"):
            val = mem_str.rstrip("MBM")
            return float(val) / 1024.0
        elif mem_str.endswith("KB") or mem_str.endswith("K"):
            val = mem_str.rstrip("KBK")
            return float(val) / (1024.0 * 1024.0)
        elif mem_str.endswith("TB") or mem_str.endswith("T"):
            val = mem_str.rstrip("TBT")
            return float(val) * 1024.0
        else:
            return float(mem_str)
    except ValueError:
        return 0.0

def get_stage_depth(stage_name, stages_dict, cache=None):
    if cache is None:
        cache = {}
    if stage_name in cache:
        return cache[stage_name]
    stage = stages_dict.get(stage_name, {})
    deps = stage.get("dependent_stages", [])
    if not deps:
        depth = 0
    else:
        depth = 1 + max(get_stage_depth(d, stages_dict, cache) for d in deps)
    cache[stage_name] = depth
    return depth


