import os
import json
import time
import subprocess
import pytest
from unittest.mock import patch

from snap_workflow.core.workflow import initialize
from snap_workflow.core.domain.stages import add_stage
from snap_workflow.core.domain.variables import add_variable
from snap_workflow.core.domain.sweeps import add_sweep
from snap_workflow.core.domain import status
from snap_workflow.core.domain import spoints
from snap_workflow import dispatcher
from snap_workflow.server import register_auto_scheduler, OrchestratorScheduler

def is_ssh_reachable():
    try:
        res = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=2", "Lab_Main", "echo", "ping"],
            capture_output=True,
            text=True,
            timeout=3
        )
        return res.returncode == 0
    except Exception:
        return False

import tempfile

# Gate these integration tests: skip if Lab_Main is not reachable.
pytestmark = pytest.mark.skipif(
    not is_ssh_reachable(),
    reason="Lab_Main is not reachable via SSH"
)

@pytest.fixture
def sandbox():
    """Fixture to create and change cwd into a temporary sandbox directory without deleting it on teardown."""
    test_dir = tempfile.mkdtemp(prefix="snap_remote_test_")
    original_cwd = os.getcwd()
    os.chdir(test_dir)
    print(f"\n[sandbox] Created temporary directory for remote test: {test_dir}")
    
    yield test_dir
    
    os.chdir(original_cwd)
    # We do NOT run shutil.rmtree(test_dir) so the user can inspect worker logs.

def setup_remote_test_env(remote_path):
    """Utility to sync workflow structure and configure env on Lab_Main."""
    # Sync workflow metadata/structure to remote_path
    from snap_workflow.remote.setup import setup_remote_cluster
    resolved_path = setup_remote_cluster(remote_host="Lab_Main", remote_path=remote_path)

    # Configure env.json and .workflow/config.json to use python3 on remote host
    modify_cmd = [
        "ssh", "Lab_Main",
        f"python3 -c \"import json, os; "
        f"p1=os.path.expanduser('{resolved_path}/stage1/env.json'); "
        f"data1=json.load(open(p1)) if os.path.exists(p1) else {{}}; data1['python_path']='python3'; json.dump(data1, open(p1, 'w')); "
        f"p2=os.path.expanduser('{resolved_path}/.workflow/config.json'); "
        f"data2=json.load(open(p2)) if os.path.exists(p2) else {{}}; data2['python_path']='python3'; json.dump(data2, open(p2, 'w'))\""
    ]
    subprocess.run(modify_cmd, check=True)
    return resolved_path

def test_remote_autosubmit_workstation(sandbox, env_dir, workflow_server):
    # Initialize workspace in sandbox
    initialize(sandbox)
    add_variable("x", ["int"], add_to_stages=[], default_val=10)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [15, 25]})

    # Configure stage resources locally so the server passes pre-flight checks
    env_file = os.path.join(sandbox, "stage1", "env.json")
    with open(env_file, "r") as f:
        env_data = json.load(f)
    env_data["resources"] = {"cpus": 1, "gpus": 0, "mem": "1G"}
    with open(env_file, "w") as f:
        json.dump(env_data, f, indent=4)

    # Define AUTO_SYNC so that the spoint.log output gets synced back to local manager
    collect_file = os.path.join(sandbox, "stage1", "collect.py")
    with open(collect_file, "w") as f:
        f.write("AUTO_SYNC = ['spoint.log']\n")

    timestamp = int(time.time())
    remote_path = f"~/test_snap_integration_auto_{timestamp}"
    resolved_path = None
    try:
        resolved_path = setup_remote_test_env(remote_path)

        # Start the local manager server
        srv, server_info = workflow_server("127.0.0.1", port=0)
        port = server_info["port"]

        # Mock global and local remotes to register Lab_Main_Test
        global_remotes = {"Lab_Main_Test": {"host": "Lab_Main"}}
        local_remotes = {"Lab_Main_Test": {"path": resolved_path}}

        with patch("snap_workflow.utils.io.load_global_remotes", return_value=global_remotes), \
             patch("snap_workflow.utils.io.load_local_remotes", return_value=local_remotes):
            
            # Start auto-scheduler thread for Lab_Main_Test
            # This triggers remote Workstation Mode since has_slurm is False
            print("Registering auto-scheduler...")
            register_auto_scheduler(
                server=srv,
                remote_name="Lab_Main_Test",
                stages="stage1",
                sweeps="sweep1"
            )

            # Wait up to 60 seconds for completion of both spoint tasks
            completed = False
            for _ in range(60):
                time.sleep(1)
                st1 = status.load_status("stage1/spoints/x_15")
                st2 = status.load_status("stage1/spoints/x_25")
                if st1 == status.COMPLETE and st2 == status.COMPLETE:
                    completed = True
                    break
                if st1 == status.ERROR or st2 == status.ERROR:
                    res = subprocess.run(["ssh", "Lab_Main", f"cat {resolved_path}/stage1/spoints/x_15/spoint.log"], capture_output=True, text=True)
                    pytest.fail(f"A remote auto-submitted task encountered an error status. SPOINT LOG:\n{res.stdout}")
            
            assert completed, f"Remote auto-submit tasks did not complete. Statuses: x_15={st1}, x_25={st2}"

            # Verify that outputs and metadata were synced back locally
            assert os.path.exists("stage1/spoints/x_15/spoint.log")
            assert os.path.exists("stage1/spoints/x_25/spoint.log")

    finally:
        if resolved_path:
            print(f"Cleaning up remote path: {resolved_path}")
            subprocess.run(["ssh", "Lab_Main", f"rm -rf {resolved_path}"], capture_output=True)

def test_remote_worker_tunnel(sandbox, env_dir, workflow_server):
    # Initialize workspace in sandbox
    initialize(sandbox)
    add_variable("x", ["int"], add_to_stages=[], default_val=10)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [30, 40]})

    # Configure stage resources locally so the server passes pre-flight checks
    env_file = os.path.join(sandbox, "stage1", "env.json")
    with open(env_file, "r") as f:
        env_data = json.load(f)
    env_data["resources"] = {"cpus": 1, "gpus": 0, "mem": "1G"}
    with open(env_file, "w") as f:
        json.dump(env_data, f, indent=4)

    # Define AUTO_SYNC so that the spoint.log output gets synced back to local manager
    collect_file = os.path.join(sandbox, "stage1", "collect.py")
    with open(collect_file, "w") as f:
        f.write("AUTO_SYNC = ['spoint.log']\n")

    timestamp = int(time.time())
    remote_path = f"~/test_snap_integration_worker_{timestamp}"
    resolved_path = None
    worker_proc = None
    try:
        resolved_path = setup_remote_test_env(remote_path)

        # Start the local manager server
        srv, server_info = workflow_server("127.0.0.1", port=0)
        port = server_info["port"]
        token = server_info["token"]

        # Mock global and local remotes to register Lab_Main_Test for the server endpoints
        global_remotes = {"Lab_Main_Test": {"host": "Lab_Main"}}
        local_remotes = {"Lab_Main_Test": {"path": resolved_path}}

        with patch("snap_workflow.utils.io.load_global_remotes", return_value=global_remotes), \
             patch("snap_workflow.utils.io.load_local_remotes", return_value=local_remotes):

            # Run remote worker client manually with an SSH reverse tunnel connection
            # to connect back to the local manager server.
            print("Launching remote background worker client via SSH tunnel...")
            worker_cmd = [
                "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ExitOnForwardFailure=yes",
                "-R", f"{port}:127.0.0.1:{port}",
                "Lab_Main",
                (
                    f"cd {resolved_path} && "
                    f"PYTHONPATH=/home/tanner/pySNAP/packages/snap_workflow/src:$PYTHONPATH python3 -u -m snap_workflow.dispatcher.runner http://127.0.0.1:{port} {token} "
                    f"--stages stage1 --sweeps sweep1 --host Lab_Main_Test"
                )
            ]
            
            # Spawn the worker client process in the background
            worker_proc = subprocess.Popen(worker_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Wait up to 60 seconds for both tasks to be processed by the worker client
            completed = False
            for _ in range(60):
                time.sleep(1)
                st1 = status.load_status("stage1/spoints/x_30")
                st2 = status.load_status("stage1/spoints/x_40")
                if st1 == status.COMPLETE and st2 == status.COMPLETE:
                    completed = True
                    break
                if st1 == status.ERROR or st2 == status.ERROR:
                    pytest.fail("A remote worker-processed task encountered an error status.")
            
            if not completed and worker_proc:
                out, err = worker_proc.communicate(timeout=2)
                pytest.fail(f"Remote worker tasks did not complete. Statuses: x_30={st1}, x_40={st2}\nWorker STDOUT:\n{out.decode()}\nWorker STDERR:\n{err.decode()}")
            assert completed, f"Remote worker tasks did not complete. Statuses: x_30={st1}, x_40={st2}"

            # Verify that outputs were registered and synced back locally
            assert os.path.exists("stage1/spoints/x_30/spoint.log")
            assert os.path.exists("stage1/spoints/x_40/spoint.log")

    finally:
        if worker_proc:
            print("Terminating remote worker process...")
            worker_proc.terminate()
            try:
                stdout, stderr = worker_proc.communicate(timeout=5)
                print("Worker stdout:")
                print(stdout.decode(errors='replace'))
                print("Worker stderr:")
                print(stderr.decode(errors='replace'))
            except Exception as e:
                print(f"Failed to communicate with worker: {e}")
        if resolved_path:
            print(f"Cleaning up remote path: {resolved_path}")
            subprocess.run(["ssh", "Lab_Main", f"rm -rf {resolved_path}"], capture_output=True)
