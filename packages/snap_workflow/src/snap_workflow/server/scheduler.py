import os
import json
import time
import threading
import subprocess
import logging
from snap_workflow.utils import path, io
from snap_workflow.core.domain import stages as stage_tools, sweeps as sweep_tools
from snap_workflow.worker.runner import parse_memory_to_gb, detect_system_resources
from snap_workflow.server.tunnels import ensure_remote_tunnel

logger = logging.getLogger("snap_workflow.server.scheduler")


def get_stage_depth(stage_name, stages_dict, cache=None):
    if cache is None:
        cache = {}
    if stage_name in cache:
        return cache[stage_name]
    stage_cfg = stages_dict.get(stage_name, {})
    deps = stage_cfg.get("dependencies")
    if deps is None:
        deps = stage_cfg.get("dependent_stages", [])
    if not deps:
        cache[stage_name] = 0
        return 0
    depth = 1 + max(get_stage_depth(d, stages_dict, cache) for d in deps)
    cache[stage_name] = depth
    return depth


class OrchestratorScheduler(threading.Thread):
    def __init__(self, remote, stages="", sweeps="", exclude_stages="", exclude_sweeps="", server=None):
        super().__init__()
        self.remote = remote
        self.stages_csv = stages
        self.sweeps_csv = sweeps
        self.exclude_stages_csv = exclude_stages
        self.exclude_sweeps_csv = exclude_sweeps
        self.server = server
        self.shutdown_event = threading.Event()

    def run(self):
        logger.info("Starting auto-scheduler for remote '%s'...", self.remote)

        host = None
        remote_path = None

        if self.remote != "local":
            try:
                from snap_workflow.cli import load_global_remotes, load_local_remotes
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

        try:
            if self.remote == "local":
                stage_tools.validate_stage_resources()
            else:
                from snap_workflow.remote.setup import validate_remote_stage_resources, resolve_remote_path
                resolved_r_path = resolve_remote_path(host, remote_path)
                validate_remote_stage_resources(host, resolved_r_path)
        except Exception as e:
            logger.error("Stage resource validation failed for remote '%s': %s", self.remote, e)
            return

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

        allowed_stages = {x.strip() for x in self.stages_csv.split(",") if x.strip()}
        allowed_sweeps = {x.strip() for x in self.sweeps_csv.split(",") if x.strip()}
        exclude_stages = {x.strip() for x in self.exclude_stages_csv.split(",") if x.strip()}
        exclude_sweeps = {x.strip() for x in self.exclude_sweeps_csv.split(",") if x.strip()}

        stages_dict = stage_tools.load_stages()
        sweeps_dict = sweep_tools.load_sweeps()
        root_dir = path.get_root()

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

        cpus_total = 8
        gpus_total = 0
        mem_total = 16.0
        active_jobs = []

        if not has_slurm:
            if self.remote == "local":
                cpus_total, gpus_total, mem_total = detect_system_resources()
            else:
                try:
                    cmd = ["ssh", host, "python3 -c \"import json; from snap_workflow.worker.runner import detect_system_resources; print(json.dumps(detect_system_resources()))\" || python -c \"import json; from snap_workflow.worker.runner import detect_system_resources; print(json.dumps(detect_system_resources()))\""]
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                    if res.returncode == 0:
                        cpus_total, gpus_total, mem_total = json.loads(res.stdout.strip())
                except Exception as e:
                    logger.warning("Failed to auto-detect remote resources: %s. Using default baseline constraints.", e)
            logger.info("Workstation capacity for remote '%s': CPUs=%s, GPUs=%s, Memory=%.2f GB",
                        self.remote, cpus_total, gpus_total, mem_total)

        while not self.shutdown_event.is_set():
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
            if not has_slurm:
                finished = []
                for job in active_jobs:
                    if self.remote == "local":
                        poll = job["proc"].poll()
                    else:
                        poll = job["proc"].poll()

                    if poll is not None:
                        finished.append(job)
                        status_val = "complete" if poll == 0 else "error"
                        if self.remote != "local" and job.get("r_spoint_path"):
                            try:
                                sync_back = ["rsync", "-avz", f"{host}:{job['r_spoint_path']}/", f"{job['sp_path']}/"]
                                subprocess.run(sync_back, capture_output=True)
                            except Exception as e:
                                logger.warning("Failed to sync back outputs for %s: %s", job['sp_path'], e)
                        logger.info("Workstation job finished: %s %s (status: %s)", job['stage'], job['spoint_dict'], status_val)
                        if self.server:
                            self.server.spoint_manager.set_status(
                                job["sweep"], job["stage"], job["spoint_dict"], status_val, host=self.remote
                            )

                for job in finished:
                    active_jobs.remove(job)

            if self.server:
                manager = self.server.spoint_manager
                candidate_spoint = None

                for sw in target_sweeps:
                    for st in target_stages:
                        spoints_st = manager.get_spoints(sw, st)
                        for sp in spoints_st:
                            sp_dict = sp["variables"]
                            curr_status = sp["status"]
                            if curr_status in ("queued", "submitted", "running", "complete", "error"):
                                continue

                            st_cfg = manager.stages_dict.get(st, {})
                            deps = st_cfg.get("dependencies") if "dependencies" in st_cfg else st_cfg.get("dependent_stages", [])
                            deps_satisfied = True
                            for dep in deps:
                                dep_spoint = manager.get_spoint(sw, dep, sp_dict)
                                if not dep_spoint or dep_spoint["status"] != "complete":
                                    deps_satisfied = False
                                    break

                            if deps_satisfied:
                                candidate_spoint = (sw, st, sp_dict, sp["path"])
                                break
                        if candidate_spoint:
                            break
                    if candidate_spoint:
                        break

                if candidate_spoint:
                    sw, st, sp_dict, sp_path = candidate_spoint
                    st_res = stage_resources.get(st, {"cpus": 1, "gpus": 0, "mem": 1.0})
                    st_cpus = int(st_res.get("cpus", 1))
                    st_gpus = int(st_res.get("gpus", 0))
                    st_mem_val = st_res.get("mem", 1.0)
                    st_mem = parse_memory_to_gb(st_mem_val) if isinstance(st_mem_val, str) else float(st_mem_val)

                    if has_slurm:
                        logger.info("Auto-scheduling spoint: %s %s on Slurm cluster '%s'...", st, sp_dict, self.remote)
                        manager.set_status(sw, st, sp_dict, "queued", host=self.remote)

                        if self.remote == "local":
                            from snap_workflow.worker.slurm import launch_local_workers
                            launch_local_workers(num_workers=1, stages=st, sweeps=sw)
                        else:
                            ensure_remote_tunnel(self.server, self.remote)
                            from snap_workflow.remote.setup import launch_remote_workers_server_side
                            launch_remote_workers_server_side(
                                server_port=self.server.server_port,
                                token=self.server.token,
                                remote_name=self.remote,
                                profile="template",
                                num_workers=1,
                                stages=st,
                                sweeps=sw
                            )
                    else:
                        def _get_stage_mem(stage_n):
                            m_val = stage_resources.get(stage_n, {}).get("mem", 1.0)
                            return parse_memory_to_gb(m_val) if isinstance(m_val, str) else float(m_val)

                        cpus_running = sum(int(stage_resources.get(j["stage"], {}).get("cpus", 1)) for j in active_jobs)
                        gpus_running = sum(int(stage_resources.get(j["stage"], {}).get("gpus", 0)) for j in active_jobs)
                        mem_running = sum(_get_stage_mem(j["stage"]) for j in active_jobs)

                        cpus_avail = cpus_total - cpus_running
                        gpus_avail = -1 if gpus_total == -1 else (gpus_total - gpus_running)
                        mem_avail = mem_total - mem_running

                        fits_cpus = (st_cpus <= cpus_avail)
                        fits_gpus = (gpus_avail == -1) or (st_gpus <= gpus_avail)
                        fits_mem = (st_mem <= mem_avail)

                        if fits_cpus and fits_gpus and fits_mem:
                            logger.info("Spawning workstation job for %s %s on '%s'...", st, sp_dict, self.remote)
                            manager.set_status(sw, st, sp_dict, "running", host=self.remote)

                            if self.remote == "local":
                                spoint_sh = os.path.join(root_dir, ".workflow", "spoint.sh")
                                proc_env = os.environ.copy()
                                if st_res.get("gpus", 0) > 0:
                                    proc_env["CUDA_VISIBLE_DEVICES"] = str(gpus_running)
                                proc = subprocess.Popen(["bash", spoint_sh, sp_path], env=proc_env)
                            else:
                                resolved_r_path = resolve_remote_path(host, remote_path)
                                rel_sp_path = os.path.relpath(sp_path, root_dir)
                                r_spoint_path = os.path.join(resolved_r_path, rel_sp_path)
                                try:
                                    sync_cmd = ["rsync", "-avz", f"{sp_path}/", f"{host}:{r_spoint_path}/"]
                                    subprocess.run(sync_cmd, capture_output=True, check=True)
                                except Exception as sync_e:
                                    logger.warning("Failed to sync spoint directory %s to %s: %s", sp_path, host, sync_e)
                                remote_cmd = f"cd {resolved_r_path} && bash .workflow/spoint.sh {r_spoint_path}"
                                proc = subprocess.Popen(["ssh", host, remote_cmd])

                            active_jobs.append({
                                "proc": proc,
                                "sweep": sw,
                                "stage": st,
                                "spoint_dict": sp_dict,
                                "sp_path": sp_path,
                                "r_spoint_path": r_spoint_path if self.remote != "local" else None
                            })

            self.shutdown_event.wait(2.0)
