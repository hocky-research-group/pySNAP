import os
import json
import pytest
from unittest.mock import patch, MagicMock

from snap_workflow.core import initialize, add_stage, add_variable, add_sweep
from snap_workflow.core.domain.stages import validate_stage_resources
from snap_workflow.server import start_server, parse_memory_to_gb, get_stage_depth
from snap_workflow.worker import detect_system_resources, worker_loop, send_request
from snap_workflow.core.domain import status

def test_stage_resource_validation(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    
    # By default, cpus/gpus/mem are initialized to -1, which should raise a ValueError
    with pytest.raises(ValueError) as exc:
        validate_stage_resources()
    assert "unconfigured resources" in str(exc.value)

    # Configure stage resources explicitly
    env_file = os.path.join("stage1", "env.json")
    with open(env_file, "r") as f:
        env_data = json.load(f)
    env_data["resources"] = {"cpus": 4, "gpus": 1, "mem": "16G"}
    with open(env_file, "w") as f:
        json.dump(env_data, f, indent=4)
        
    # Now it should validate cleanly without errors
    validate_stage_resources()

def test_parse_memory_to_gb():
    assert parse_memory_to_gb("2G") == 2.0
    assert parse_memory_to_gb("512M") == 0.5
    assert abs(parse_memory_to_gb("1024K") - 0.00097656) < 1e-6
    assert parse_memory_to_gb("1T") == 1024.0
    assert parse_memory_to_gb("4") == 4.0
    assert parse_memory_to_gb("") == 0.0

def test_get_stage_depth():
    stages_dict = {
        "stage1": {"dependent_stages": []},
        "stage2": {"dependent_stages": ["stage1"]},
        "stage3": {"dependent_stages": ["stage2"]}
    }
    cache = {}
    assert get_stage_depth("stage1", stages_dict, cache) == 0
    assert get_stage_depth("stage2", stages_dict, cache) == 1
    assert get_stage_depth("stage3", stages_dict, cache) == 2

@pytest.fixture
def workflow_server():
    servers = []
    def _start(host="127.0.0.1", port=0):
        srv, info = start_server(host, port)
        servers.append(srv)
        return srv, info
        
    yield _start
    for srv in servers:
        try:
            srv.shutdown()
            srv.server_close()
        except Exception:
            pass

def test_dynamic_resource_scheduling(sandbox, env_dir, workflow_server):
    initialize(env_dir)
    
    # Define a pipeline: stage1 (CPU only) -> stage2 (GPU required)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    env_file1 = os.path.join("stage1", "env.json")
    with open(env_file1, "r") as f:
        env1 = json.load(f)
    env1["resources"] = {"cpus": 2, "gpus": 0, "mem": "4G"}
    with open(env_file1, "w") as f:
        json.dump(env1, f, indent=4)
        
    add_stage("stage2", sbatch_details=None, stage_variables=["x"], stage_dependencies=["stage1"])
    env_file2 = os.path.join("stage2", "env.json")
    with open(env_file2, "r") as f:
        env2 = json.load(f)
    env2["resources"] = {"cpus": 4, "gpus": 1, "mem": "16G"}
    with open(env_file2, "w") as f:
        json.dump(env2, f, indent=4)

    add_variable("x", ["int"], add_to_stages=["stage1", "stage2"], default_val=10)
    add_sweep("sweep1", include_stages=["stage1", "stage2"], variable_values={"x": [5]})

    # Start the server
    _, server_info = workflow_server("127.0.0.1", port=0)
    url = server_info["url"]
    token = server_info["token"]

    # 1. cWorker requests work. Should only receive stage1 (since stage2 requires a GPU)
    c_resp = send_request(f"{url}/request_work?cpus_avail=8&gpu_avail=-1&mem_avail=16.0", token)
    assert c_resp["status"] == "spoint"
    assert c_resp["stage"] == "stage1"

    # Reset stage1 status back to initialized so we can test gWorker allocation
    status.write_status("initialized", os.path.join("stage1", "spoints", "x_5"))

    # 2. gWorker requests work.
    # If gpu_avail=0 (gWorker but currently busy on GPU tasks or has 0 idle GPUs)
    # It can backfill CPU tasks because future GPU tasks exist (stage2 is not complete)
    g_resp = send_request(f"{url}/request_work?cpus_avail=8&gpu_avail=0&mem_avail=16.0&min_cpu_running_gpu=4", token)
    assert g_resp["status"] == "spoint"
    assert g_resp["stage"] == "stage1"

    # Reset stage1 status again
    status.write_status("initialized", os.path.join("stage1", "spoints", "x_5"))

    # Test reservation logic:
    # If we request a CPU task with cpus_avail=4, gpu_avail=1, and max_gpu_task_cpu_req=4.
    # If we assign stage1 (cpu_req=2), remaining cpus = 4 - 2 = 2.
    # 2 + 0 < 4 (max_gpu_task_cpu_req), so it should NOT assign stage1 (to reserve CPUs for future GPU tasks).
    g_reserve_resp = send_request(f"{url}/request_work?cpus_avail=4&gpu_avail=1&mem_avail=16.0&min_cpu_running_gpu=0", token)
    assert g_reserve_resp["status"] in ["idle", "none"]

    # If we increase cpus_avail=6, then 6 - 2 + 0 = 4 >= 4, so it should assign stage1!
    g_reserve_resp2 = send_request(f"{url}/request_work?cpus_avail=6&gpu_avail=1&mem_avail=16.0&min_cpu_running_gpu=0", token)
    assert g_reserve_resp2["status"] == "spoint"
    assert g_reserve_resp2["stage"] == "stage1"

def test_worker_task_filtering(sandbox, env_dir, workflow_server):
    initialize(env_dir)
    
    # 2 stages: stage1 (CPU only) and stage2 (CPU only)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    env_file1 = os.path.join("stage1", "env.json")
    with open(env_file1, "r") as f:
        env1 = json.load(f)
    env1["resources"] = {"cpus": 1, "gpus": 0, "mem": "1G"}
    with open(env_file1, "w") as f:
        json.dump(env1, f, indent=4)
        
    add_stage("stage2", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    env_file2 = os.path.join("stage2", "env.json")
    with open(env_file2, "r") as f:
        env2 = json.load(f)
    env2["resources"] = {"cpus": 1, "gpus": 0, "mem": "1G"}
    with open(env_file2, "w") as f:
        json.dump(env2, f, indent=4)

    add_variable("x", ["int"], add_to_stages=["stage1", "stage2"], default_val=10)
    add_sweep("sweep1", include_stages=["stage1", "stage2"], variable_values={"x": [5]})
    add_sweep("sweep2", include_stages=["stage1", "stage2"], variable_values={"x": [5]})

    # Start the server
    _, server_info = workflow_server("127.0.0.1", port=0)
    url = server_info["url"]
    token = server_info["token"]

    # 1. Test allowed stages list
    # Request work with stages=stage1. Should receive stage1
    resp = send_request(f"{url}/request_work?cpus_avail=4&gpu_avail=-1&mem_avail=8.0&stages=stage1", token)
    assert resp["status"] == "spoint"
    assert resp["stage"] == "stage1"
    
    # Complete the task we just checked out
    status.write_status("complete", os.path.join("stage1", "spoints", "x_5"))
    
    # Request work again with stages=stage1. Since all stage1 tasks are complete (or not submittable/running),
    # it should return shutdown even though stage2 has incomplete tasks!
    resp = send_request(f"{url}/request_work?cpus_avail=4&gpu_avail=-1&mem_avail=8.0&stages=stage1", token)
    assert resp["status"] == "shutdown"

    # Reset stage1 task back to initialized
    status.write_status("initialized", os.path.join("stage1", "spoints", "x_5"))

    # 2. Test excluded stages list
    # Request work with exclude_stages=stage1. Should receive stage2 (skipping stage1)
    resp = send_request(f"{url}/request_work?cpus_avail=4&gpu_avail=-1&mem_avail=8.0&exclude_stages=stage1", token)
    assert resp["status"] == "spoint"
    assert resp["stage"] == "stage2"

    # Reset stage2 task back to initialized (since it gets marked submitted when checked out)
    status.write_status("initialized", os.path.join("stage2", "spoints", "x_5"))

    # 3. Test allowed sweeps list
    # Request work with sweeps=sweep2. Should receive sweep2 task
    resp = send_request(f"{url}/request_work?cpus_avail=4&gpu_avail=-1&mem_avail=8.0&sweeps=sweep2", token)
    assert resp["status"] == "spoint"
    assert resp["sweep"] == "sweep2"

    # 4. Test excluded sweeps list
    # Request work with exclude_sweeps=sweep2. Should receive sweep1 task
    resp = send_request(f"{url}/request_work?cpus_avail=4&gpu_avail=-1&mem_avail=8.0&exclude_sweeps=sweep2", token)
    assert resp["status"] == "spoint"
    assert resp["sweep"] == "sweep1"

def test_remote_configs_and_spawning(sandbox, env_dir, tmp_path):
    initialize(env_dir)
    
    global_config_dir = os.path.join(tmp_path, ".snap_workflow")
    global_remotes_file = os.path.join(global_config_dir, "remotes.json")
    
    with patch("snap_workflow.utils.constants.GLOBAL_CONFIG_DIR", global_config_dir), \
         patch("snap_workflow.utils.constants.GLOBAL_REMOTES_FILE", global_remotes_file), \
         patch("snap_workflow.utils.constants.GLOBAL_CONFIG_DIR", global_config_dir), \
         patch("snap_workflow.utils.constants.GLOBAL_REMOTES_FILE", global_remotes_file):
        
        from snap_workflow.cli.remote import remote_add_cmd, remote_setup_cmd
        from snap_workflow.utils.io import load_global_remotes, load_local_remotes
        
        # Test adding remote globally
        with patch("subprocess.run") as mock_run_add:
            mock_res_add = MagicMock()
            mock_res_add.stdout = "ok\n"
            mock_run_add.return_value = mock_res_add
            remote_add_cmd("workflow remote add", ["my_workstation", "--host", "tanner@workstation.local"])
        
        global_data = load_global_remotes()
        assert "my_workstation" in global_data
        assert global_data["my_workstation"]["host"] == "tanner@workstation.local"
        
        from snap_workflow.utils.version import __version__ as local_ver

        # Test local path setup (with patch to mock ssh commands)
        def mock_ssh_run(cmd, **kwargs):
            mock_res = MagicMock()
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            if "echo ok" in cmd_str:
                mock_res.stdout = "ok\n"
            elif "python3 -c" in cmd_str or "python -c" in cmd_str:
                mock_res.stdout = f"{local_ver}\n"
            else:
                mock_res.stdout = "empty\n"
            return mock_res

        with patch("subprocess.run", side_effect=mock_ssh_run) as mock_run:
            remote_setup_cmd("workflow remote setup", ["my_workstation", "--path", "/home/tanner/sims"])
            assert mock_run.called
            
        local_data = load_local_remotes()
        assert "my_workstation" in local_data
        assert local_data["my_workstation"]["path"] == "/home/tanner/sims"

        # 2. Test pre-flight worker submission checks (fail when server not running)
        from snap_workflow.cli.server import server_submit_worker_cmd
        with pytest.raises(ValueError) as exc:
            server_submit_worker_cmd("workflow server submit worker", ["my_workstation", "template", "--num-workers", "1"])
        assert "Manager server is not running" in str(exc.value)

        # 3. Test spawning local workers
        from snap_workflow.utils.constants import SERVER_INFO
        with open(SERVER_INFO, "w") as f:
            json.dump({"port": 1234, "token": "dummy_token"}, f)
            
        add_stage("stage1")
        env_file1 = os.path.join("stage1", "env.json")
        with open(env_file1, "r") as f:
            env1 = json.load(f)
        env1["resources"] = {"cpus": 1, "gpus": 0, "mem": "1G"}
        with open(env_file1, "w") as f:
            json.dump(env1, f, indent=4)

        from snap_workflow.worker import launch_local_workers
        def mock_send_request(url, token, data=None):
            if data and data.get("name") == "local":
                launch_local_workers(
                    num_workers=data.get("num_workers", 1),
                    stages=data.get("stages", ""),
                    sweeps=data.get("sweeps", ""),
                    exclude_stages=data.get("exclude_stages", ""),
                    exclude_sweeps=data.get("exclude_sweeps", ""),
                    profile=data.get("profile", "cpu")
                )
                return {"status": "success", "message": "Spawned local workers"}
            return {"status": "success"}

        with patch("subprocess.Popen") as mock_popen, \
             patch("snap_workflow.worker.send_request", side_effect=mock_send_request):
            server_submit_worker_cmd("workflow server submit worker", ["local", "cpu", "--num-workers", "3", "--stage", "stage1"])
            assert mock_popen.call_count == 3
            first_args = mock_popen.call_args_list[0][0][0]
            assert any("snap_workflow.worker" in arg for arg in first_args)
            assert "--stages" in first_args
            assert "stage1" in first_args

def test_auto_scheduling(sandbox, env_dir, workflow_server):
    initialize(env_dir)
    
    # Configure stages: stage1 (requires 2 cpus, 1 gpu), and stage2 (depends on stage1)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    env_file1 = os.path.join("stage1", "env.json")
    with open(env_file1, "r") as f:
        env1 = json.load(f)
    env1["resources"] = {"cpus": 2, "gpus": 1, "mem": "4G"}
    with open(env_file1, "w") as f:
        json.dump(env1, f, indent=4)
        
    add_stage("stage2", sbatch_details=None, stage_variables=["x"], stage_dependencies=["stage1"])
    env_file2 = os.path.join("stage2", "env.json")
    with open(env_file2, "r") as f:
        env2 = json.load(f)
    env2["resources"] = {"cpus": 1, "gpus": 0, "mem": "1G"}
    with open(env_file2, "w") as f:
        json.dump(env2, f, indent=4)

    add_variable("x", ["int"], add_to_stages=["stage1", "stage2"], default_val=10)
    add_sweep("sweep1", include_stages=["stage1", "stage2"], variable_values={"x": [5]})

    # Start the server
    srv, server_info = workflow_server("127.0.0.1", port=0)
    url = server_info["url"]
    token = server_info["token"]

    # 1. Register auto-scheduler via POST /submit_auto
    from snap_workflow.cli.server import server_submit_auto_cmd
    from snap_workflow.utils.constants import SERVER_INFO
    import time
    
    with open(SERVER_INFO, "w") as f:
        json.dump(server_info, f)
        
    mock_run_res = MagicMock()
    mock_run_res.returncode = 1 # simulates no sbatch available
    
    with patch("subprocess.run", return_value=mock_run_res), \
         patch("snap_workflow.server.scheduler.detect_system_resources", return_value=(8, 2, 16.0)), \
         patch("snap_workflow.worker.detect_system_resources", return_value=(8, 2, 16.0)), \
         patch("subprocess.Popen") as mock_popen:
         
        # Execute the auto-submit command
        server_submit_auto_cmd("workflow server submit auto", ["local"])
        
        # Verify the scheduler registered on the server
        assert hasattr(srv, "auto_schedulers")
        assert "local" in srv.auto_schedulers
        scheduler = srv.auto_schedulers["local"]
        assert scheduler.is_alive()
        
        # Give the scheduler loop a tiny moment to run the workstation spawn
        time.sleep(1.0)
        
        # SPoint 1 should have been spawned because it is initialized and has no dependencies
        assert mock_popen.called
        call_envs = [call[1].get("env", {}) for call in mock_popen.call_args_list if call[1] and "env" in call[1]]
        assert any("CUDA_VISIBLE_DEVICES" in env for env in call_envs)
        
        # Check that status was updated to RUNNING
        spoint_path = os.path.join("stage1", "spoints", "x_5")
        assert status.load_status(spoint_path) == "running"
        
        # Stop the scheduler cleanly
        scheduler.shutdown_event.set()
        scheduler.join()

def test_alternative_scheduler_safety(sandbox, env_dir, workflow_server):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    env_file1 = os.path.join("stage1", "env.json")
    with open(env_file1, "r") as f:
        env1 = json.load(f)
    env1["resources"] = {"cpus": 1, "gpus": 0, "mem": "1G"}
    with open(env_file1, "w") as f:
        json.dump(env1, f, indent=4)
        
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=10)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})

    srv, server_info = workflow_server("127.0.0.1", port=0)
    url = server_info["url"]
    token = server_info["token"]

    from snap_workflow.cli.server import server_submit_auto_cmd
    from snap_workflow.utils.constants import SERVER_INFO
    with open(SERVER_INFO, "w") as f:
        json.dump(server_info, f)

    def mock_run(cmd, *args, **kwargs):
        res = MagicMock()
        if "sbatch" in cmd or "sbatch" in str(cmd):
            res.returncode = 1
        elif "qsub" in cmd or "qsub" in str(cmd):
            res.returncode = 0
        else:
            res.returncode = 1
        return res

    with patch("subprocess.run", side_effect=mock_run), \
         patch("subprocess.Popen") as mock_popen:
         
        server_submit_auto_cmd("workflow server submit auto", ["local"])
        
        scheduler = srv.auto_schedulers["local"]
        scheduler.join(timeout=2.0)
        
        assert not scheduler.is_alive()
        assert not mock_popen.called
