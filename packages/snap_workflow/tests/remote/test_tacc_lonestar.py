import os
import json
import time
import shutil
import subprocess
import tempfile
import pytest
from unittest.mock import patch

from snap_workflow.core.workflow import initialize
from snap_workflow.core.domain.stages import add_stage
from snap_workflow.core.domain.variables import add_variable
from snap_workflow.core.domain.sweeps import add_sweep
from snap_workflow.core.domain import status, spoints
from snap_workflow.remote import ensure_remote_tunnel
from snap_workflow.remote.setup import setup_remote_cluster, launch_remote_workers_server_side
from snap_workflow.remote.ssh import run_remote_python, run_remote_bash

# ==============================================================================
# TACC Lonestar Integration Test Configuration
# Edit the variables below to match your TACC Lonestar workspace configuration.
# ==============================================================================
REMOTE_NAME = "Lonestar"        # Global remote name registered via 'workflow remote add'
REMOTE_WORK_PATH = "/work/07828/taw2983/ls6/test_snap_lonestar"  # Target test directory on Lonestar
WORKER_PROFILE = "worker_profile"     # Slurm profile name on cluster (e.g. 'template', 'worker_profile')
REMOTE_PYTHON_CMD = "/work/07828/taw2983/ls6/miniforge3/envs/pySNAP/bin/python"   # Python executable / env on Lonestar
POLL_TIMEOUT_SECONDS = 3600      # Max time to wait for Slurm queueing & execution

# Enable tests only when explicitly invoked via environment variable
RUN_LONESTAR = os.environ.get("RUN_LONESTAR_TESTS") == "1" or os.environ.get("RUN_TACC_TESTS") == "1"

pytestmark = [
    pytest.mark.lonestar,
    pytest.mark.skipif(
        not RUN_LONESTAR,
        reason="TACC Lonestar integration tests are skipped by default. Set RUN_LONESTAR_TESTS=1 to run."
    )
]


def check_lonestar_ssh():
    """Verify basic SSH reachability to the remote host using ControlPath."""
    try:
        from snap_workflow.utils.io import load_global_remotes
        from snap_workflow.remote.ssh import run_remote_python
        remotes = load_global_remotes()
        if REMOTE_NAME not in remotes:
            return False
        host = remotes[REMOTE_NAME]["host"]
        out = run_remote_python(host, "print('ping')", python_cmd=REMOTE_PYTHON_CMD, timeout=15)
        return "ping" in out
    except Exception:
        return False


@pytest.fixture
def sandbox():
    """Creates a local temporary directory for test workflow execution."""
    test_dir = tempfile.mkdtemp(prefix="snap_lonestar_test_")
    orig_cwd = os.getcwd()
    os.chdir(test_dir)
    print(f"\n[Sandbox] Local test workspace initialized at: {test_dir}")
    yield test_dir
    os.chdir(orig_cwd)


def prepare_lonestar_remote(sandbox_dir, remote_path_override=None):
    from snap_workflow.remote.ssh import run_remote_bash
    try:
        run_remote_bash("LoneStar", "scancel -u $USER -n run_worker 2>/dev/null || true")
    except Exception:
        pass
    """Syncs the test workspace to Lonestar, copies worker profile, and configures python paths."""
    from snap_workflow.utils.io import load_global_remotes
    global_remotes = load_global_remotes()
    if REMOTE_NAME not in global_remotes:
        pytest.fail(f"Global remote '{REMOTE_NAME}' is not registered. Run 'workflow remote add' first.")
    
    host = global_remotes[REMOTE_NAME]["host"]
    target_path = remote_path_override or f"{REMOTE_WORK_PATH}_{int(time.time())}"

    # Ensure local workers/ directory exists and copy worker_profile.json
    local_workers_dir = os.path.join(sandbox_dir, "workers")
    os.makedirs(local_workers_dir, exist_ok=True)

    src_profile = os.path.join(os.path.dirname(__file__), "fixtures", "worker_profile.json")
    if os.path.isfile(src_profile):
        shutil.copy(src_profile, os.path.join(local_workers_dir, f"{WORKER_PROFILE}.json"))
        shutil.copy(src_profile, os.path.join(local_workers_dir, "worker_profile.json"))

    print(f"[TACC Setup] Syncing workspace to {host}:{target_path}...")
    resolved_path = setup_remote_cluster(remote_host=host, remote_path=target_path)

    # Sync workers profile to remote resolved_path
    sync_profile_cmd = [
        "rsync", "-avz",
        f"{local_workers_dir}/",
        f"{host}:{resolved_path}/workers/"
    ]
    subprocess.run(sync_profile_cmd, capture_output=True, text=True)

    py_script = (
        "import os, json, glob\n"
        f"res_p = {repr(resolved_path)}\n"
        f"py_env = {repr(REMOTE_PYTHON_CMD)}\n"
        "cfg_p = os.path.expanduser(res_p + '/.workflow/config.json')\n"
        "if os.path.isfile(cfg_p):\n"
        "    with open(cfg_p, 'r') as f:\n"
        "        d = json.load(f)\n"
        "    d['default_python_env'] = py_env\n"
        "    with open(cfg_p, 'w') as f:\n"
        "        json.dump(d, f, indent=4)\n"
        "\n"
        "for env_f in glob.glob(os.path.expanduser(res_p + '/*/env.json')):\n"
        "    with open(env_f, 'r') as f:\n"
        "        ed = json.load(f)\n"
        "    ed['python_path'] = py_env\n"
        "    with open(env_f, 'w') as f:\n"
        "        json.dump(ed, f, indent=4)\n"
    )
    run_remote_python(host, py_script, python_cmd=REMOTE_PYTHON_CMD)
    return host, resolved_path


# ==============================================================================
# TEST CASES
# ==============================================================================

def test_tacc_lonestar_connectivity():
    """
    1. Connectivity & Environment Check
    Verifies SSH connection to Lonestar, remote Python environment, and base64 payload execution.
    """
    assert check_lonestar_ssh(), f"Cannot reach global remote '{REMOTE_NAME}' via SSH."
    from snap_workflow.utils.io import load_global_remotes
    host = load_global_remotes()[REMOTE_NAME]["host"]

    out = run_remote_python(host, "import sys, platform; print(f'{platform.node()}|{sys.version_info[0]}.{sys.version_info[1]}')", python_cmd=REMOTE_PYTHON_CMD)
    node_info, py_ver = out.strip().split("|")
    print(f"\n[Lonestar Connect] Connected to node: {node_info} (Python {py_ver})")
    assert len(py_ver) > 0


def test_tacc_lonestar_persistent_tunnel(sandbox, workflow_server):
    """
    2. Persistent Server-Side Reverse Tunnel
    Tests starting WorkflowServer and establishing a persistent SSH reverse tunnel to Lonestar.
    """
    initialize(sandbox)
    srv, server_info = workflow_server("127.0.0.1", port=0)
    port = server_info["port"]

    print(f"\n[Tunnel Test] Server started on port {port}. Establishing persistent SSH reverse tunnel...")
    tunnel_proc = ensure_remote_tunnel(srv, REMOTE_NAME)
    assert tunnel_proc is not None
    assert tunnel_proc is not None
    assert tunnel_proc.poll() is None, "SSH reverse tunnel process died immediately."
    
    from snap_workflow.utils.io import load_global_remotes
    host = load_global_remotes()[REMOTE_NAME]["host"]

    # Test reverse port connection on Lonestar
    check_port_script = f"import socket; s = socket.socket(); s.settimeout(3); res = s.connect_ex(('127.0.0.1', {port})); s.close(); print(res)"
    connected = False
    conn_result = -1
    for _ in range(5):
        time.sleep(1)
        res_str = run_remote_python(host, check_port_script, python_cmd=REMOTE_PYTHON_CMD)
        try:
            conn_result = int(res_str.strip())
            if conn_result == 0:
                connected = True
                break
        except Exception:
            pass
    assert connected, f"Reverse tunnel port {port} on Lonestar is not reachable (connect_ex returned {conn_result})."
    print(f"[Tunnel Test] Successfully verified port {port} reverse forwarding on Lonestar.")


def test_tacc_lonestar_slurm_worker_execution(sandbox, workflow_server):
    """
    3. Manual Worker Launch via Slurm
    Submits a worker job to Slurm on Lonestar, executes stage tasks, and verifies results.
    """
    initialize(sandbox)
    add_variable("x", ["int"], add_to_stages=[], default_val=10)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [100, 200]})

    # Set stage environment & explicit sbatch requirements from tests/remote/env.json template
    src_env = os.path.join(os.path.dirname(__file__), "fixtures", "env.json")
    env_file = os.path.join(sandbox, "stage1", "env.json")
    if os.path.isfile(src_env):
        shutil.copy(src_env, env_file)
    else:
        with open(env_file, "r") as f:
            env_data = json.load(f)
        env_data["resources"] = {"cpus": 1, "gpus": 0, "mem": "1G"}
        with open(env_file, "w") as f:
            json.dump(env_data, f, indent=4)

    # Set AUTO_SYNC output tracking
    collect_file = os.path.join(sandbox, "stage1", "collect.py")
    with open(collect_file, "w") as f:
        f.write("AUTO_SYNC = ['spoint.log']\n")

    host, resolved_path = prepare_lonestar_remote(sandbox)

    try:
        srv, server_info = workflow_server("127.0.0.1", port=0)
        port = server_info["port"]
        token = server_info["token"]

        ensure_remote_tunnel(srv, REMOTE_NAME)

        print(f"\n[Worker Test] Submitting Slurm worker job on Lonestar profile '{WORKER_PROFILE}'...")
        launch_remote_workers_server_side(
            server_port=port,
            token=token,
            remote_name=REMOTE_NAME,
            profile=WORKER_PROFILE,
            num_workers=1,
            stages="stage1",
            sweeps="sweep1",
            remote_host=host,
            remote_path=resolved_path
        )

        print(f"[Worker Test] Waiting up to {POLL_TIMEOUT_SECONDS}s for Slurm queueing & execution...")
        completed = False
        for _ in range(POLL_TIMEOUT_SECONDS):
            time.sleep(1)
            st1 = status.load_status("stage1/spoints/x_100")
            st2 = status.load_status("stage1/spoints/x_200")
            if st1 == status.COMPLETE and st2 == status.COMPLETE:
                completed = True
                break
            if st1 == status.ERROR or st2 == status.ERROR:
                err_log_1 = ""
                try:
                    err_log_1 = run_remote_bash(host, f"echo === spoint.log ===; cat {resolved_path}/stage1/spoints/x_100/spoint.log 2>/dev/null; echo === err ===; cat {resolved_path}/stage1/spoints/x_100/.spoint_info/err 2>/dev/null; echo === slurm ===; cat {resolved_path}/slurm_out/*.out 2>/dev/null")
                except Exception:
                    pass
                pytest.fail(f"Task failed during worker execution. Statuses: x_100={st1}, x_200={st2}. Remote log:\n{err_log_1}")

        assert completed, f"Tasks did not complete within {POLL_TIMEOUT_SECONDS}s. Statuses: x_100={st1}, x_200={st2}"
        remote_files = run_remote_bash(host, f"find {resolved_path} -type f").strip()
        remote_log_1 = run_remote_bash(host, f"if [ -f {resolved_path}/stage1/spoints/x_100/spoint.log ]; then echo exists; else echo missing; fi").strip()
        remote_log_2 = run_remote_bash(host, f"if [ -f {resolved_path}/stage1/spoints/x_200/spoint.log ]; then echo exists; else echo missing; fi").strip()
        assert remote_log_1 == "exists", f"Remote spoint.log missing for x_100 at {resolved_path}. Found files:\n{remote_files}"
        assert remote_log_2 == "exists", f"Remote spoint.log missing for x_200 at {resolved_path}. Found files:\n{remote_files}" 
        print("[Worker Test] Slurm worker execution and file sync completed successfully.")

    finally:
        print(f"[Cleanup] Removing remote path and worker jobs: {resolved_path}")
        run_remote_bash(host, f"scancel -u $USER -n run_worker 2>/dev/null || true; rm -rf {resolved_path}")


def test_tacc_lonestar_autosubmit_orchestrator(sandbox, workflow_server):
    """
    4. Orchestrator Auto-Scheduler Test
    Registers the auto-scheduler for Lonestar, initializes sweeps, and verifies auto-submission.
    """
    initialize(sandbox)
    add_variable("x", ["int"], add_to_stages=[], default_val=10)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [500, 600]})

    src_env = os.path.join(os.path.dirname(__file__), "fixtures", "env.json")
    env_file = os.path.join(sandbox, "stage1", "env.json")
    if os.path.isfile(src_env):
        shutil.copy(src_env, env_file)
    else:
        with open(env_file, "r") as f:
            env_data = json.load(f)
        env_data["resources"] = {"cpus": 1, "gpus": 0, "mem": "1G"}
        with open(env_file, "w") as f:
            json.dump(env_data, f, indent=4)

    collect_file = os.path.join(sandbox, "stage1", "collect.py")
    with open(collect_file, "w") as f:
        f.write("AUTO_SYNC = ['spoint.log']\n")

    host, resolved_path = prepare_lonestar_remote(sandbox)

    try:
        srv, server_info = workflow_server("127.0.0.1", port=0)

        local_remotes = {REMOTE_NAME: {"path": resolved_path}}

        with patch("snap_workflow.utils.io.load_local_remotes", return_value=local_remotes):
            print(f"\n[Auto-Submit Test] Registering auto-scheduler for remote '{REMOTE_NAME}'...")
            register_auto_scheduler(
                server=srv,
                remote_name=REMOTE_NAME,
                stages="stage1",
                sweeps="sweep1"
            )

            print(f"[Auto-Submit Test] Waiting up to {POLL_TIMEOUT_SECONDS}s for auto-scheduler to submit & process tasks...")
            completed = False
            for _ in range(POLL_TIMEOUT_SECONDS):
                time.sleep(1)
                st1 = status.load_status("stage1/spoints/x_500")
                st2 = status.load_status("stage1/spoints/x_600")
                if st1 == status.COMPLETE and st2 == status.COMPLETE:
                    completed = True
                    break
                if st1 == status.ERROR or st2 == status.ERROR:
                    pytest.fail(f"Task failed during auto-submit execution. Statuses: x_500={st1}, x_600={st2}")

            assert completed, f"Auto-submitted tasks did not complete within {POLL_TIMEOUT_SECONDS}s. Statuses: x_500={st1}, x_600={st2}"
            assert os.path.exists("stage1/spoints/x_500/spoint.log")
            assert os.path.exists("stage1/spoints/x_600/spoint.log")
            print("[Auto-Submit Test] Auto-scheduler integration test completed successfully.")

    finally:
        print(f"[Cleanup] Removing remote path and worker jobs: {resolved_path}")
        run_remote_bash(host, f"scancel -u $USER -n run_worker 2>/dev/null || true; rm -rf {resolved_path}")
