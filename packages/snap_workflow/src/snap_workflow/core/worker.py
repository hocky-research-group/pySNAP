import urllib.request
import json
import time
import subprocess
import sys
import os

from .strings import *
from . import path, io
from .exceptions import ServerNotRunningError
from .logging_config import logger

def send_request(url, token, data=None, retries=3, backoff=2):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    if data is not None:
        req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=headers, method="POST")
    else:
        req = urllib.request.Request(url, headers=headers, method="GET")
        
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                return json.loads(response.read().decode())
        except Exception as e:
            if attempt < retries - 1:
                logger.warning("Request to %s failed: %s. Retrying in %s seconds...", url, e, backoff)
                time.sleep(backoff)
                backoff *= 2
            else:
                logger.error("Request to %s failed after %s attempts: %s", url, retries, e)
                return None

def worker_loop(server_url, token, cpus_total=None, gpus_total=None, mem_total=None, idle_delay=5,
                stages="", sweeps="", exclude_stages="", exclude_sweeps="", host="local", worker_id=None):
    if not worker_id:
        import uuid
        worker_id = f"{host}_{int(time.time())}_{uuid.uuid4().hex[:6]}"

    root = None
    log_file = None
    try:
        root = path.get_root()
        log_dir = os.path.join(root, "worker_logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file_path = os.path.join(log_dir, f"worker_{worker_id}.log")
        log_file = open(log_file_path, "a", buffering=1)
    except Exception:
        pass
    
    import sys
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    
    try:
        if log_file is not None:
            sys.stdout = log_file
            sys.stderr = log_file

        if cpus_total is None or gpus_total is None or mem_total is None:
            detected_cpus, detected_gpus, detected_mem = detect_system_resources()
            if cpus_total is None:
                cpus_total = detected_cpus
            if gpus_total is None:
                gpus_total = detected_gpus
            if mem_total is None:
                mem_total = detected_mem

        logger.info("Worker started. Connecting to manager at %s. Resources: cpus_total=%s, gpus_total=%s, mem_total=%.2f GB",
                    server_url, cpus_total, gpus_total, mem_total)
        
        active_spoints = []
        should_shutdown = False
        
        while True:
            # 1. Clean up finished spoints
            finished = []
            for spoint in active_spoints:
                poll = spoint["proc"].poll()
                if poll is not None:
                    finished.append(spoint)
                    status_val = "complete" if poll == 0 else "error"
                    logger.info("Spoint finished: %s %s with status %s", spoint['stage'], spoint['spoint_dict'], status_val)
                    print(f"[Worker Action] Stop executing spoint {spoint['stage']} with variables {spoint['spoint_dict']} (exit status: {status_val})")
                    
                    payload = {
                        "sweep": spoint["sweep"],
                        "stage": spoint["stage"],
                        "combo_dict": spoint["spoint_dict"],
                        "status": status_val,
                        "host": host
                    }
                    send_request(f"{server_url}/notify_completion", token, data=payload)
                    
            for spoint in finished:
                active_spoints.remove(spoint)
                
            # Calculate currently occupied resources
            cpus_running = 0
            gpus_running = 0
            mem_running = 0.0
            running_gpu_cpu_requirements = []
            
            for spoint in active_spoints:
                stage_name = spoint["stage"]
                env_base = os.path.join(root if root is not None else ".", stage_name, "env")
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
                cpus_running += req_cpus
                gpus_running += req_gpus
                mem_running += req_mem
                if req_gpus > 0:
                    running_gpu_cpu_requirements.append(req_cpus)
            
            cpus_avail = max(0, cpus_total - cpus_running)
            gpu_avail = -1 if gpus_total == -1 else max(0, gpus_total - gpus_running)
            mem_avail = max(0.0, mem_total - mem_running)
            min_cpu_running_gpu = min(running_gpu_cpu_requirements) if running_gpu_cpu_requirements else 0
            
            # 2. If we have room and are not in shutdown, request more work
            if not should_shutdown and cpus_avail > 0 and mem_avail > 0:
                url = (
                    f"{server_url}/request_work?cpus_avail={cpus_avail}&gpu_avail={gpu_avail}&mem_avail={mem_avail:.2f}"
                    f"&min_cpu_running_gpu={min_cpu_running_gpu}&host={host}"
                )
                if stages:
                    url += f"&stages={stages}"
                if sweeps:
                    url += f"&sweeps={sweeps}"
                if exclude_stages:
                    url += f"&exclude_stages={exclude_stages}"
                if exclude_sweeps:
                    url += f"&exclude_sweeps={exclude_sweeps}"
                resp = send_request(url, token)
                if resp:
                    status_resp = resp.get("status")
                    if status_resp == "shutdown":
                        logger.info("Worker received shutdown signal from manager. Draining %s active tasks...", len(active_spoints))
                        print(f"[Server Instruction] Shutdown")
                        should_shutdown = True
                    elif status_resp == "combo":
                        sweep = resp["sweep"]
                        stage = resp["stage"]
                        spoint_dict = resp["combo_dict"]
                        spoint_path = resp["combo_path"]
                        
                        logger.info("Acquired spoint: %s %s", stage, spoint_dict)
                        print(f"[Server Instruction] Execute stage {stage} with sweep variables {spoint_dict}")
                        print(f"[Worker Action] Start executing spoint {stage} with variables {spoint_dict}")
                        
                        # Spawn local spoint execution, redirecting stdout/stderr to worker log file
                        combo_sh_script = os.path.join(".workflow", "spoint.sh")
                        if log_file is not None:
                            proc = subprocess.Popen(["bash", combo_sh_script, spoint_path], stdout=log_file, stderr=log_file)
                        else:
                            proc = subprocess.Popen(["bash", combo_sh_script, spoint_path])
                        active_spoints.append({
                            "proc": proc,
                            "sweep": sweep,
                            "stage": stage,
                            "spoint_dict": spoint_dict,
                            "combo_path": spoint_path
                        })
                        continue # Try requesting more work immediately
            
            # 3. Sleep / idle delay / shutdown exit
            if should_shutdown and len(active_spoints) == 0:
                logger.info("Draining complete. Exiting worker loop cleanly.")
                break
                
            if len(active_spoints) == 0:
                time.sleep(idle_delay)
            else:
                time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("Stopping worker. Terminating active spoints...")
        for spoint in active_spoints:
            try:
                spoint["proc"].terminate()
            except Exception:
                pass
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        if log_file is not None:
            log_file.close()

        try:
            payload = {
                "worker_id": worker_id,
                "host": host
            }
            send_request(f"{server_url}/notify_shutdown", token, data=payload, retries=1)
        except Exception as e:
            logger.warning("Failed to notify manager of worker shutdown: %s", e)

def launch_remote_workers(remote_host, remote_path, profile, num_workers=1, concurrency=1, sbatch_args="",
                          stages="", sweeps="", exclude_stages="", exclude_sweeps="", remote_name=""):
    from . import io
    root = path.get_root()
    
    # 1. Load server info
    info_path = os.path.join(root, SERVER_INFO)
    if not os.path.isfile(info_path):
        raise ServerNotRunningError("Manager server is not running. Please start it using 'workflow server start'.")
        
    with open(info_path, "r") as f:
        server_info = json.load(f)
        
    port = server_info["port"]
    token = server_info["token"]
    
    # Resolve and validate remote path
    resolved_path = resolve_remote_path(remote_host, remote_path)
    
    # Load worker profile from remote host (global first, then local override)
    import base64
    profile_py = (
        "import os, json\n"
        f"prof = {repr(profile)}\n"
        f"r_path = {repr(resolved_path)}\n"
        "data = {}\n"
        "def load_prof(p_base):\n"
        "    for ext in ['', '.json', '.yaml', '.yml']:\n"
        "        fn = p_base + ext\n"
        "        if os.path.isfile(fn):\n"
        "            with open(fn) as f:\n"
        "                if fn.endswith('.json') or not (fn.endswith('.yaml') or fn.endswith('.yml')):\n"
        "                    data.update(json.load(f)); return\n"
        "                else:\n"
        "                    import yaml; data.update(yaml.safe_load(f)); return\n"
        "load_prof(os.path.expanduser(f'~/.config/snap_workflow/workers/{prof}'))\n"
        "load_prof(os.path.join(r_path, 'workers', prof))\n"
        "print(json.dumps(data))\n"
    )
    b64_prof = base64.b64encode(profile_py.encode()).decode()
    b64_cmd = f"import base64; exec(base64.b64decode('{b64_prof}'))"
    try:
        res = subprocess.run(["ssh", remote_host, f"python3 -c {repr(b64_cmd)}"], capture_output=True, text=True, check=True)
        profile_data = json.loads(res.stdout.strip())
    except Exception as e:
        profile_data = {}
        logger.warning("Failed to load worker profile '%s' from remote %s: %s", profile, remote_host, e)

    if not profile_data:
        raise ValueError(f"Worker profile '{profile}' was not found on remote '{remote_host}' at '{resolved_path}/workers/{profile}' or '~/.config/snap_workflow/workers/{profile}'.")

    for k, v in profile_data.items():
        if "FIXME" in str(v).upper():
            raise ValueError(f"Worker profile '{profile}' on remote '{remote_host}' contains unconfigured 'FIXME' setting for parameter '{k}'. Please edit '{resolved_path}/workers/{profile}' on the cluster before submitting workers.")
            
    profile_sbatch_args = ""
    if profile_data:
        flags = []
        for k, v in profile_data.items():
            dash_key = k if k.startswith("-") else (f"-{k}" if len(k) == 1 else f"--{k}")
            if v is None:
                flags.append(dash_key)
            else:
                flags.append(f"{dash_key}={v}")
        profile_sbatch_args = " ".join(flags)
        
    if profile_sbatch_args:
        if sbatch_args:
            sbatch_args = f"{profile_sbatch_args} {sbatch_args}"
        else:
            sbatch_args = profile_sbatch_args

    # 2. Sync local codebase to cluster
    # Exclude spoints/combos and dynamic files to minimize transfer weight
    logger.info("Syncing codebase to remote cluster %s:%s...", remote_host, resolved_path)
    sync_command = [
        "rsync", "-avz",
        "--exclude", f"{SPOINTS}/",
        "--exclude", "combos/",
        "--exclude", ".git/",
        "--exclude", "slurm_out/",
        "--exclude", "temp/",
        "--exclude", "**/env.json",
        "--exclude", "**/env.yaml",
        "--exclude", "**/env.yml",
        "--exclude", ".workflow/config.json",
        "--exclude", "workers/",
        "./", f"{remote_host}:{resolved_path}/"
    ]
    subprocess.run(sync_command, check=True)
    
    # 3. Launch reverse tunnel process in the background
    logger.info("Establishing reverse tunnel -R %s:127.0.0.1:%s to %s...", port, port, remote_host)
    tunnel_cmd = [
        "ssh", "-N",
        "-o", "ExitOnForwardFailure=yes",
        "-R", f"{port}:127.0.0.1:{port}",
        remote_host
    ]
    tunnel_proc = subprocess.Popen(tunnel_cmd)
    
    # 4. Submit Slurm workers
    # We pass token and port as environment variables to the workers
    logger.info("Submitting %s worker Slurm jobs on remote cluster...", num_workers)
    run_worker_sh = os.path.join(".workflow", "workers", "run_worker.sh")
    
    export_vars = f"ALL,SERVER_PORT={port},SERVER_TOKEN={token}"
    if remote_name:
        export_vars += f",WORKER_HOST={remote_name}"
    if stages:
        export_vars += f",WORKER_STAGES={stages}"
    if sweeps:
        export_vars += f",WORKER_SWEEPS={sweeps}"
    if exclude_stages:
        export_vars += f",WORKER_EXCLUDE_STAGES={exclude_stages}"
    if exclude_sweeps:
        export_vars += f",WORKER_EXCLUDE_SWEEPS={exclude_sweeps}"
        
    sbatch_cmd = (
        f"cd {resolved_path} && sbatch --export={export_vars} "
        f"{sbatch_args} {run_worker_sh}"
    )
    
    for _ in range(num_workers):
        ssh_cmd = ["ssh", remote_host, sbatch_cmd]
        subprocess.run(ssh_cmd, check=True)
        
    logger.info("Workers submitted successfully. Keeping SSH tunnel open. Press Ctrl+C to close tunnel.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Closing SSH tunnel...")
        tunnel_proc.terminate()

def resolve_remote_path(remote_host, remote_path):
    # Check if directory exists, if it is empty, or if it is a workflow root (.workflow/ exists)
    check_cmd = [
        "ssh", remote_host,
        f'if [ ! -d "{remote_path}" ]; then echo "not_exists"; '
        f'elif [ -d "{remote_path}/.workflow" ]; then echo "workflow_root"; '
        f'elif [ -z "$(ls -A "{remote_path}" 2>/dev/null)" ]; then echo "empty"; '
        f'else echo "not_empty"; fi'
    ]
    try:
        res = subprocess.run(check_cmd, capture_output=True, text=True, check=True)
        status = res.stdout.strip()
    except Exception as e:
        logger.warning("Failed to run remote path check on %s: %s. Proceeding with caution.", remote_host, e)
        # Fall back to not_empty if we fail to check (to be safe)
        status = "not_empty"

    if status in ("not_exists", "empty", "workflow_root"):
        return remote_path

    # Otherwise, create a subdirectory named after the local workflow root
    root_dir = path.get_root()
    dirname = os.path.basename(os.path.abspath(root_dir))
    new_remote_path = f"{remote_path.rstrip('/')}/{dirname}"
    logger.warning(
        "Target remote path '%s' is not empty and is not a workflow root. "
        "Using dedicated subdirectory: '%s'",
        remote_path, new_remote_path
    )
    return new_remote_path

def setup_remote_cluster(remote_host, remote_path):
    # Pre-flight SSH connectivity test
    ssh_test = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", remote_host, "echo ok"]
    try:
        res = subprocess.run(ssh_test, capture_output=True, text=True, check=True)
        if res.stdout.strip() != "ok":
            raise ValueError(f"SSH connection test to '{remote_host}' failed.")
    except Exception as e:
        raise ValueError(f"Cannot connect to remote host '{remote_host}' via SSH: {e}. Please verify hostname and credentials.")

    resolved_path = resolve_remote_path(remote_host, remote_path)
    logger.info("Setting up workflow structure on remote cluster %s:%s...", remote_host, resolved_path)
    
    # Ensure remote directory exists and is writable
    try:
        ssh_mkdir = ["ssh", remote_host, f"mkdir -p {resolved_path}/workers && test -w {resolved_path}"]
        subprocess.run(ssh_mkdir, check=True)
    except Exception as e:
        raise ValueError(f"Failed to create or access remote directory '{resolved_path}' on '{remote_host}': {e}")
    
    # 1. Sync all code and templates, EXCLUDING env.json, config.json, and workers/
    sync_code_command = [
        "rsync", "-avz",
        "--exclude", f"{SPOINTS}/",
        "--exclude", "combos/",
        "--exclude", ".git/",
        "--exclude", "slurm_out/",
        "--exclude", "temp/",
        "--exclude", "**/env.json",
        "--exclude", "**/env.yaml",
        "--exclude", "**/env.yml",
        "--exclude", ".workflow/config.json",
        "--exclude", "workers/",
        "./", f"{remote_host}:{resolved_path}/"
    ]
    subprocess.run(sync_code_command, check=True)
    
    # 2. Sync only missing env.json, config.json, and workers/ files (ignoring existing ones on the cluster)
    sync_envs_command = [
        "rsync", "-avz", "--ignore-existing",
        "--include", "*/",
        "--include", "**/env.json",
        "--include", "**/env.yaml",
        "--include", "**/env.yml",
        "--include", ".workflow/config.json",
        "--include", "workers/",
        "--include", "workers/**",
        "--exclude", "*",
        "./", f"{remote_host}:{resolved_path}/"
    ]
    subprocess.run(sync_envs_command, check=True)

    # 3. Post-setup on remote: initialize FIXME for newly synced configs and ensure default template.json profile
    import base64
    remote_script = (
        "import os, json, glob\n"
        f"r_path = {repr(resolved_path)}\n"
        "cfg_p = os.path.join(r_path, '.workflow', 'config.json')\n"
        "if os.path.isfile(cfg_p):\n"
        "    with open(cfg_p, 'r+') as f:\n"
        "        c = json.load(f); c['default_python_env'] = 'FIXME'\n"
        "        f.seek(0); json.dump(c, f, indent=4); f.truncate()\n"
        "for env_f in glob.glob(os.path.join(r_path, '*', 'env.json')) + glob.glob(os.path.join(r_path, '*', 'env.yaml')) + glob.glob(os.path.join(r_path, '*', 'env.yml')):\n"
        "    if env_f.endswith('.json'):\n"
        "        with open(env_f, 'r+') as f:\n"
        "            c = json.load(f); c['python_path'] = 'FIXME'\n"
        "            f.seek(0); json.dump(c, f, indent=4); f.truncate()\n"
        "    else:\n"
        "        try:\n"
        "            import yaml\n"
        "            with open(env_f, 'r+') as f:\n"
        "                c = yaml.safe_load(f); c['python_path'] = 'FIXME'\n"
        "                f.seek(0); yaml.safe_dump(c, f, default_flow_style=False); f.truncate()\n"
        "        except Exception: pass\n"
        "w_dir = os.path.join(r_path, 'workers')\n"
        "os.makedirs(w_dir, exist_ok=True)\n"
        "tmpl_f = os.path.join(w_dir, 'template.json')\n"
        "if not os.path.isfile(tmpl_f):\n"
        "    tmpl_data = {'partition': 'FIXME', 'nodes': 1, 'ntasks-per-node': 1, 'cpus-per-task': 8, 'mem': '16G', 'time': '04:00:00'}\n"
        "    with open(tmpl_f, 'w') as f: json.dump(tmpl_data, f, indent=4)\n"
    )
    b64_setup = base64.b64encode(remote_script.encode()).decode()
    b64_setup_cmd = f"import base64; exec(base64.b64decode('{b64_setup}'))"
    subprocess.run(["ssh", remote_host, f"python3 -c {repr(b64_setup_cmd)}"], check=True)

    logger.info("Remote cluster setup complete. You can now edit configuration environment templates/workers profiles on the cluster at '%s:%s'.", remote_host, resolved_path)
    return resolved_path


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

def detect_system_resources():
    cpus = None
    for var in ["SLURM_CPUS_ON_NODE", "SLURM_CPUS_PER_TASK"]:
        val = os.getenv(var)
        if val:
            try:
                cpus = int(val)
                break
            except ValueError:
                pass
    if cpus is None:
        cpus = os.cpu_count() or 1

    gpus = -1
    cuda_devices = os.getenv("CUDA_VISIBLE_DEVICES")
    if cuda_devices is not None:
        cuda_devices = cuda_devices.strip()
        if cuda_devices in ["", "NoDevFiles", "none", "-1"]:
            gpus = -1
        else:
            try:
                gpus = len([x for x in cuda_devices.split(",") if x.strip()])
            except Exception:
                gpus = 1
    else:
        slurm_gpus = os.getenv("SLURM_STEP_GPUS") or os.getenv("SLURM_GPUS_ON_NODE")
        if slurm_gpus:
            try:
                gpus = int(slurm_gpus)
            except ValueError:
                gpus = 1
        else:
            try:
                import torch
                if torch.cuda.is_available():
                    gpus = torch.cuda.device_count()
            except ImportError:
                pass

    mem_gb = None
    slurm_mem = os.getenv("SLURM_MEM_PER_NODE")
    if slurm_mem:
        try:
            mem_gb = float(slurm_mem) / 1024.0
        except ValueError:
            pass
    if mem_gb is None:
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        mem_gb = kb / (1024.0 * 1024.0)
                        break
        except Exception:
            pass
    if mem_gb is None:
        try:
            pages = os.sysconf('SC_PHYS_PAGES')
            page_size = os.sysconf('SC_PAGE_SIZE')
            mem_gb = (pages * page_size) / (1024.0 ** 3)
        except Exception:
            mem_gb = 4.0
            
    return cpus, gpus, mem_gb

def launch_local_workers(num_workers=1, stages="", sweeps="", exclude_stages="", exclude_sweeps="", profile="cpu"):
    root = path.get_root()
    info_path = os.path.join(root, SERVER_INFO)
    if not os.path.isfile(info_path):
        raise ServerNotRunningError("Manager server is not running. Please start it using 'workflow server start'.")
        
    with open(info_path, "r") as f:
        server_info = json.load(f)
        
    port = server_info["port"]
    token = server_info["token"]
    server_url = f"http://127.0.0.1:{port}"
    
    logger.info("Spawning %s local background workers...", num_workers)
    os.makedirs(os.path.join(root, "worker_logs"), exist_ok=True)
    for i in range(num_workers):
        worker_id = f"local_{int(time.time())}_{i}"
        log_path = os.path.join(root, "worker_logs", f"worker_{worker_id}.log")
        log_f = open(log_path, "a", buffering=1)
        cmd = [
            sys.executable, "-m", "snap_workflow.core.worker",
            server_url, token, "--host", "local", "--worker-id", worker_id
        ]
        if stages:
            cmd.extend(["--stages", stages])
        if sweeps:
            cmd.extend(["--sweeps", sweeps])
        if exclude_stages:
            cmd.extend(["--exclude_stages", exclude_stages])
        if exclude_sweeps:
            cmd.extend(["--exclude_sweeps", exclude_sweeps])
            
        subprocess.Popen(cmd, stdout=log_f, stderr=log_f)
        
    logger.info("%s local background workers spawned successfully.", num_workers)

if __name__ == "__main__":
    import argparse
    from snap_workflow.core.logging_config import setup_logging
    parser = argparse.ArgumentParser(description="snap_workflow Worker")
    parser.add_argument("server_url", help="URL of the manager server")
    parser.add_argument("token", help="Security token")
    parser.add_argument("--stages", default="", help="CSV allowed stages")
    parser.add_argument("--sweeps", default="", help="CSV allowed sweeps")
    parser.add_argument("--exclude_stages", default="", help="CSV excluded stages")
    parser.add_argument("--exclude_sweeps", default="", help="CSV excluded sweeps")
    parser.add_argument("--host", default="local", help="Worker host name")
    parser.add_argument("--worker-id", default=None, help="Worker ID")
    
    args = parser.parse_args()
    setup_logging()
    worker_loop(
        args.server_url,
        args.token,
        stages=args.stages,
        sweeps=args.sweeps,
        exclude_stages=args.exclude_stages,
        exclude_sweeps=args.exclude_sweeps,
        host=args.host,
        worker_id=args.worker_id
    )


