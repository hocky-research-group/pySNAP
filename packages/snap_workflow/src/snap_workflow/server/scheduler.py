import sys
import os
import json
import time
import threading
import subprocess
import logging
from snap_workflow.utils import path, io
from snap_workflow.core.domain import stages as stage_tools, sweeps as sweep_tools
from snap_workflow.worker.runner import parse_memory_to_gb, detect_system_resources
from snap_workflow.utils.resource_allocator import ResourcePool
import shutil
from snap_workflow.server.tunnels import ensure_remote_tunnel
from snap_workflow.remote.ssh import is_remote_ssh_connected, trigger_alert_sound

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
    def __init__(self, remote, stages="", sweeps="", exclude_stages="", exclude_sweeps="", server=None, profile="worker_profile"):
        super().__init__()
        self.remote = remote
        self.stages_csv = stages
        self.sweeps_csv = sweeps
        self.exclude_stages_csv = exclude_stages
        self.exclude_sweeps_csv = exclude_sweeps
        self.server = server
        self.profile = profile
        self.shutdown_event = threading.Event()
        self.last_squeue_check_time = 0
        self.slurm_job_states = {}

    def run(self):
        logger.info("Starting auto-scheduler for remote '%s'...", self.remote)

        host = None
        remote_path = None

        if self.remote != "local":
            try:
                from snap_workflow.utils.io import load_global_remotes, load_local_remotes
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
        slurm_submitted_jobs = []

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
            logger.info("[SCHEDULER] Workstation capacity for remote '%s': CPUs=%s, GPUs=%s, Memory=%.2f GB",
                        self.remote, cpus_total, gpus_total, mem_total)

        resource_pool = ResourcePool(cpus_total=cpus_total, gpus_total=gpus_total) if not has_slurm else None
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
                        
                        stdout, stderr = "", ""
                        if job.get("proc"):
                            try:
                                out, err = job["proc"].communicate(timeout=5)
                                stdout = out or ""
                                stderr = err or ""
                            except Exception:
                                pass

                        if self.remote != "local" and job.get("r_spoint_path"):
                            try:
                                sync_back = ["rsync", "-avz", f"{host}:{job['r_spoint_path']}/", f"{job['sp_path']}/"]
                                subprocess.run(sync_back, capture_output=True)
                            except Exception as e:
                                logger.warning("Failed to sync back outputs for %s: %s", job['sp_path'], e)

                        shell_output = ""
                        if stdout and stdout.strip():
                            shell_output += f"\n--- STDOUT ---\n{stdout.strip()}"
                        if stderr and stderr.strip():
                            shell_output += f"\n--- STDERR ---\n{stderr.strip()}"

                        if poll != 0:
                            logger.error(
                                "Workstation job failed for stage '%s' %s on remote '%s' (exit code %s).%s",
                                job["stage"], job["spoint_dict"], self.remote, poll, shell_output or " (no shell output captured)"
                            )
                        else:
                            logger.info(
                                "Workstation job finished for stage '%s' %s (status: %s).%s",
                                job['stage'], job['spoint_dict'], status_val, shell_output
                            )

                        if self.server:
                            self.server.spoint_manager.set_status(
                                job["sweep"], job["stage"], job["spoint_dict"], status_val, host=self.remote
                            )

                for job in finished:
                    if resource_pool and "assigned_cpus" in job and "assigned_gpus" in job:
                        resource_pool.release(job["assigned_cpus"], job["assigned_gpus"])
                    active_jobs.remove(job)

            if has_slurm and self.remote != "local":
                # 1. SSH Connection Health Check & Sound Alert if disconnected while jobs are active
                if slurm_submitted_jobs or active_jobs:
                    if not is_remote_ssh_connected(host):
                        logger.error(
                            "[ALERT] SSH master connection to remote '%s' (%s) lost while active Slurm jobs are queued! Run 'workflow remote connect %s' to reconnect.",
                            self.remote, host, self.remote
                        )
                        trigger_alert_sound()

                # 2. Periodic squeue monitoring (every 300s, reporting diffs silently)
                now_t = time.time()
                if (now_t - self.last_squeue_check_time >= 300) and is_remote_ssh_connected(host):
                    self.last_squeue_check_time = now_t
                    try:
                        from snap_workflow.remote.ssh import run_remote_bash
                        sq_out = run_remote_bash(host, "squeue -u $USER -o '%i %T %R' --noheader 2>/dev/null || echo ''", timeout=10)
                        curr_states = {}
                        for line in sq_out.strip().splitlines():
                            parts = line.strip().split()
                            if len(parts) >= 2:
                                j_id, j_st = parts[0], parts[1]
                                curr_states[j_id] = j_st

                        for j_id, new_st in curr_states.items():
                            old_st = self.slurm_job_states.get(j_id)
                            if old_st != new_st:
                                logger.info("[SLURM] Job %s on remote '%s' status: %s -> %s", j_id, self.remote, old_st or "NEW", new_st)

                        for j_id in list(self.slurm_job_states.keys()):
                            if j_id not in curr_states:
                                logger.info("[SLURM] Job %s on remote '%s' departed queue.", j_id, self.remote)

                        self.slurm_job_states = curr_states
                    except Exception as sq_e:
                        logger.debug("Slurm queue check warning on remote '%s': %s", self.remote, sq_e)

            if has_slurm and self.remote != "local" and slurm_submitted_jobs:
                finished_slurm = []
                from snap_workflow.remote.setup import run_remote_bash
                for s_job in slurm_submitted_jobs:
                    r_st_file = f"{s_job['r_spoint_path']}/.spoint_info/status"
                    cat_out = run_remote_bash(s_job["host"], f"cat {r_st_file} 2>/dev/null || echo ''").strip()
                    if cat_out in ("complete", "error"):
                        finished_slurm.append((s_job, cat_out))

                for s_job, st_val in finished_slurm:
                    try:
                        sync_back = ["rsync", "-avz", f"{s_job['host']}:{s_job['r_spoint_path']}/", f"{s_job['sp_path']}/"]
                        subprocess.run(sync_back, capture_output=True)
                    except Exception as sync_e:
                        logger.warning("Failed to sync back Slurm job output for %s: %s", s_job['sp_path'], sync_e)

                    if self.server:
                        self.server.spoint_manager.set_status(s_job["sweep"], s_job["stage"], s_job["spoint_dict"], st_val, host=self.remote)
                    slurm_submitted_jobs.remove(s_job)

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
                        logger.info("[SCHEDULER] Auto-scheduling spoint: %s %s on Slurm cluster '%s'...", st, sp_dict, self.remote)
                        manager.set_status(sw, st, sp_dict, "submitted", host=self.remote)

                        rel_sp_path = os.path.relpath(sp_path, root_dir)
                        server_port = self.server.server_port if self.server else 0
                        token = getattr(self.server, "token", "") if self.server else ""
                        report_url = f"http://127.0.0.1:{server_port}"
                        export_env = f"ALL,REPORT_TO={report_url},SERVER_TOKEN={token}"

                        if self.remote == "local":
                            sbatch_dict = {}
                            env_base = os.path.join(root_dir, st, "env")
                            try:
                                env_data = io.load_config(env_base, full_path=True)
                                sbatch_dict = env_data.get("sbatch", {})
                            except Exception:
                                pass

                            sbatch_flags = [f"-J {st}", "-o slurm_out/%j.out"]
                            for k, v in sbatch_dict.items():
                                dash_k = k if k.startswith("-") else (f"-{k}" if len(k) == 1 else f"--{k}")
                                if v is None or v == "":
                                    sbatch_flags.append(dash_k)
                                else:
                                    sbatch_flags.append(f"{dash_k}={v}")

                            spoint_sh = os.path.join(root_dir, ".workflow", "spoint.sh")
                            os.makedirs(os.path.join(root_dir, "slurm_out"), exist_ok=True)
                            sbatch_cmd = ["sbatch", f"--export={export_env}"] + sbatch_flags + [spoint_sh, sp_path]
                            subprocess.run(sbatch_cmd, capture_output=True)
                        else:
                            ensure_remote_tunnel(self.server, self.remote)
                            from snap_workflow.remote.setup import resolve_remote_path, run_remote_python
                            resolved_r_path = resolve_remote_path(host, remote_path)
                            r_spoint_path = os.path.join(resolved_r_path, rel_sp_path)

                            # Ensure .workflow/spoint.sh and spoint dir are synced to remote cluster
                            from snap_workflow.remote.setup import run_remote_bash
                            local_spoint_sh = os.path.join(root_dir, ".workflow", "spoint.sh")
                            if os.path.isfile(local_spoint_sh):
                                r_wf_dir = f"{resolved_r_path}/.workflow"
                                run_remote_bash(host, f"mkdir -p {r_wf_dir}")
                                subprocess.run(["rsync", "-avz", local_spoint_sh, f"{host}:{r_wf_dir}/spoint.sh"], capture_output=True)

                            subprocess.run(["rsync", "-avz", f"{sp_path}/", f"{host}:{r_spoint_path}/"], capture_output=True)

                            # Load remote stage env.json sbatch flags
                            sbatch_dict = {}
                            try:
                                cat_out = run_remote_bash(host, f"cat {resolved_r_path}/{st}/env.json 2>/dev/null || true").strip()
                                if cat_out:
                                    env_json_data = json.loads(cat_out)
                                    sbatch_dict = env_json_data.get("sbatch", {})
                            except Exception as env_e:
                                logger.warning("Failed to load remote sbatch configuration for stage %s: %s", st, env_e)

                            flags_list = [f"-J {st}", "-o slurm_out/%j.out"]
                            for k, v in sbatch_dict.items():
                                dash_k = k if k.startswith("-") else (f"-{k}" if len(k) == 1 else f"--{k}")
                                if v is None or v == "":
                                    flags_list.append(dash_k)
                                else:
                                    flags_list.append(f"{dash_k}={v}")

                            sbatch_flags_str = " ".join(flags_list)
                            remote_sbatch_cmd = f"cd {resolved_r_path} && mkdir -p slurm_out && sbatch --export={export_env} {sbatch_flags_str} .workflow/spoint.sh {rel_sp_path}"
                            logger.info("[REMOTE:AUTO] Executing sbatch command on '%s': ssh %s '%s'", host, host, remote_sbatch_cmd)
                            run_remote_bash(host, remote_sbatch_cmd)
                            slurm_submitted_jobs.append({"sweep": sw, "stage": st, "spoint_dict": sp_dict, "sp_path": sp_path, "r_spoint_path": r_spoint_path, "host": host})
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
                            logger.info("[JOB] Spawning workstation job for %s %s on '%s'...", st, sp_dict, self.remote)
                            manager.set_status(sw, st, sp_dict, "running", host=self.remote)

                            assigned_cpus, assigned_gpus = [], []
                            if resource_pool:
                                try:
                                    assigned_cpus, assigned_gpus = resource_pool.acquire(st_cpus, st_gpus)
                                except Exception as acq_err:
                                    logger.warning("ResourcePool checkout failed in scheduler for %s: %s", st, acq_err)
                                    assigned_cpus, assigned_gpus = list(range(st_cpus)), list(range(st_gpus)) if st_gpus > 0 else []

                            if self.remote == "local":
                                spoint_sh = os.path.join(root_dir, ".workflow", "spoint.sh")
                                proc_env = os.environ.copy()
                                if st_gpus > 0 and assigned_gpus:
                                    proc_env["CUDA_VISIBLE_DEVICES"] = ",".join(map(str, assigned_gpus))
                                proc_env["OMP_NUM_THREADS"] = str(st_cpus)
                                proc_env["MKL_NUM_THREADS"] = str(st_cpus)
                                proc_env["OPENBLAS_NUM_THREADS"] = str(st_cpus)
                                proc_env["VECLIB_MAXIMUM_THREADS"] = str(st_cpus)
                                proc_env["NUMEXPR_NUM_THREADS"] = str(st_cpus)

                                cmd = ["bash", spoint_sh, sp_path]
                                if sys.platform != "win32" and shutil.which("taskset") and assigned_cpus:
                                    if len(assigned_cpus) > 1 and assigned_cpus == list(range(assigned_cpus[0], assigned_cpus[-1] + 1)):
                                        core_str = f"{assigned_cpus[0]}-{assigned_cpus[-1]}"
                                    else:
                                        core_str = ",".join(map(str, assigned_cpus))
                                    cmd = ["taskset", "-c", core_str] + cmd

                                proc = subprocess.Popen(cmd, env=proc_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                            else:
                                resolved_r_path = resolve_remote_path(host, remote_path)
                                rel_sp_path = os.path.relpath(sp_path, root_dir)
                                r_spoint_path = os.path.join(resolved_r_path, rel_sp_path)

                                # Ensure .workflow/spoint.sh is synced to remote host
                                local_spoint_sh = os.path.join(root_dir, ".workflow", "spoint.sh")
                                if os.path.isfile(local_spoint_sh):
                                    try:
                                        r_wf_dir = f"{resolved_r_path}/.workflow"
                                        subprocess.run(["ssh", host, f"mkdir -p {r_wf_dir}"], capture_output=True)
                                        subprocess.run(["rsync", "-avz", local_spoint_sh, f"{host}:{r_wf_dir}/spoint.sh"], capture_output=True)
                                    except Exception as sh_e:
                                        logger.warning("Failed to sync spoint.sh to remote %s: %s", host, sh_e)

                                try:
                                    sync_cmd = ["rsync", "-avz", f"{sp_path}/", f"{host}:{r_spoint_path}/"]
                                    subprocess.run(sync_cmd, capture_output=True, check=True)
                                except Exception as sync_e:
                                    logger.warning("Failed to sync spoint directory %s to %s: %s", sp_path, host, sync_e)
                                remote_cmd = f"mkdir -p {r_spoint_path} && cd {resolved_r_path} && bash .workflow/spoint.sh {rel_sp_path}"
                                logger.info("[REMOTE:AUTO] Executing remote command on '%s': ssh %s '%s'", host, host, remote_cmd)
                                proc = subprocess.Popen(["ssh", host, remote_cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

                            active_jobs.append({
                                "proc": proc,
                                "sweep": sw,
                                "stage": st,
                                "spoint_dict": sp_dict,
                                "sp_path": sp_path,
                                "r_spoint_path": r_spoint_path if self.remote != "local" else None,
                                "assigned_cpus": assigned_cpus,
                                "assigned_gpus": assigned_gpus
                            })

            self.shutdown_event.wait(2.0)
