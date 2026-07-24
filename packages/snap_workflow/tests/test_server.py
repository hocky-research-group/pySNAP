import os
import json
import urllib.request
import urllib.error
import subprocess
from unittest.mock import patch, MagicMock
import pytest

from snap_workflow.core.workflow import initialize
from snap_workflow.core.domain.stages import add_stage
from snap_workflow.core.domain.variables import add_variable
from snap_workflow.core.domain.sweeps import add_sweep
from snap_workflow.core.domain import status
from snap_workflow.server import start_server
from snap_workflow.worker import send_request

def configure_stage_resources(stage_name, cpus=1, gpus=0, mem="2G"):
    import yaml
    for ext in ["json", "yaml"]:
        env_file = os.path.join(stage_name, f"env.{ext}")
        if os.path.exists(env_file):
            with open(env_file, "r") as f:
                if ext == "json":
                    env_data = json.load(f)
                else:
                    env_data = yaml.safe_load(f) or {}
            env_data["resources"] = {"cpus": cpus, "gpus": gpus, "mem": mem}
            with open(env_file, "w") as f:
                if ext == "json":
                    json.dump(env_data, f, indent=4)
                else:
                    yaml.safe_dump(env_data, f, default_flow_style=False)

def test_unauthorized_access(sandbox, env_dir, workflow_server):
    # Initialize workflow
    initialize(env_dir)
    
    # Start server in background thread on loopback
    _, server_info = workflow_server("127.0.0.1", port=0)
    url = server_info["url"]
    
    # Try request without token
    req = urllib.request.Request(f"{url}/request_work", method="GET")
    with pytest.raises(urllib.error.HTTPError) as cm:
        urllib.request.urlopen(req)
    assert cm.value.code == 401

    # Try request with wrong token
    req = urllib.request.Request(f"{url}/request_work", headers={"Authorization": "Bearer badtoken"}, method="GET")
    with pytest.raises(urllib.error.HTTPError) as cm:
        urllib.request.urlopen(req)
    assert cm.value.code == 401

def test_work_allocation_and_notification(sandbox, env_dir, workflow_server):
    initialize(env_dir)
    
    # Create a stage, a variable, and a sweep
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    
    # Configure resources explicitly
    env_file = os.path.join("stage1", "env.json")
    with open(env_file, "r") as f:
        env_data = json.load(f)
    env_data["resources"] = {"cpus": 1, "gpus": 0, "mem": "2G"}
    with open(env_file, "w") as f:
        json.dump(env_data, f, indent=4)
        
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=10)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    
    _, server_info = workflow_server("127.0.0.1", port=0)
    url = server_info["url"]
    token = server_info["token"]
    
    # 1. Request work
    resp = send_request(f"{url}/request_work", token)
    assert resp is not None
    assert resp["status"] == "combo"
    assert resp["stage"] == "stage1"
    assert resp["combo_dict"] == {"x": 5}
    
    # Check spoint status was set to submitted
    status_file = os.path.join("stage1", "spoints", "x_5", ".spoint_info", "status")
    with open(status_file, "r") as f:
        assert f.read().strip() == "submitted"
        
    # 2. Notify completion
    payload = {
        "sweep": "sweep1",
        "stage": "stage1",
        "combo_dict": {"x": 5},
        "status": "complete"
    }
    notify_resp = send_request(f"{url}/notify_completion", token, data=payload)
    assert notify_resp["status"] == "ok"
    
    # Check status was updated to complete
    with open(status_file, "r") as f:
        assert f.read().strip() == "complete"
        
    # 3. Requesting work again should return shutdown as no other combos are pending
    idle_resp = send_request(f"{url}/request_work", token)
    assert idle_resp["status"] == "shutdown"

def is_ssh_reachable():
    try:
        res = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=2", "Lab_Main", "echo", "ping"],
            capture_output=True, timeout=3
        )
        return res.returncode == 0
    except Exception:
        return False

def test_orchestrator_scheduler_live_ssh(sandbox, env_dir):
    initialize(env_dir)
    if not is_ssh_reachable():
        pytest.skip("Lab_Main SSH connection not reachable")

    from snap_workflow.utils.constants import GLOBAL_REMOTES_FILE, LOCAL_REMOTES_FILE, GLOBAL_CONFIG_DIR
    if not os.path.exists(GLOBAL_CONFIG_DIR):
        os.makedirs(GLOBAL_CONFIG_DIR, exist_ok=True)
        
    global_remotes = {"Lab_Main": {"host": "Lab_Main"}}
    with open(GLOBAL_REMOTES_FILE, "w") as f:
        json.dump(global_remotes, f)
        
    local_remotes = {"Lab_Main": {"path": "~/test_snap_setup"}}
    with open(f".workflow/{LOCAL_REMOTES_FILE}", "w") as f:
        json.dump(local_remotes, f)

    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    
    env_file = os.path.join("stage1", "env.json")
    with open(env_file, "r") as f:
        env_data = json.load(f)
    env_data["resources"] = {"cpus": 1, "gpus": 0, "mem": "2G"}
    with open(env_file, "w") as f:
        json.dump(env_data, f, indent=4)
        
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=10)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})

    # Instantiate OrchestratorScheduler for Lab_Main remote
    from snap_workflow.server import OrchestratorScheduler
    scheduler = OrchestratorScheduler(
        remote="Lab_Main",
        stages="stage1",
        sweeps="sweep1"
    )
    
    # Mock time.sleep to terminate the thread loop immediately on first wait check
    def mock_sleep(seconds):
        scheduler.shutdown_event.set()
        
    with patch("time.sleep", side_effect=mock_sleep):
        scheduler.run()
        
    # Verify the scheduler completed its loop iteration successfully
    assert scheduler.shutdown_event.is_set()

def test_unauthorized_endpoints(sandbox, env_dir, workflow_server):
    initialize(env_dir)
    _, server_info = workflow_server("127.0.0.1", port=0)
    url = server_info["url"]
    
    # 1. notify_completion unauthorized
    req = urllib.request.Request(f"{url}/notify_completion", headers={"Authorization": "Bearer badtoken"}, method="POST")
    with pytest.raises(urllib.error.HTTPError) as cm:
        urllib.request.urlopen(req)
    assert cm.value.code == 401

    # 2. submit_auto unauthorized
    req = urllib.request.Request(f"{url}/submit_auto", headers={"Authorization": "Bearer badtoken"}, method="POST")
    with pytest.raises(urllib.error.HTTPError) as cm:
        urllib.request.urlopen(req)
    assert cm.value.code == 401

def test_http_get_404(sandbox, env_dir, workflow_server):
    initialize(env_dir)
    _, server_info = workflow_server("127.0.0.1", port=0)
    url = server_info["url"]
    token = server_info["token"]
    
    req = urllib.request.Request(f"{url}/nonexistent", headers={"Authorization": f"Bearer {token}"}, method="GET")
    with pytest.raises(urllib.error.HTTPError) as cm:
        urllib.request.urlopen(req)
    assert cm.value.code == 404

    # Test unauthorized /shutdown GET request (covers line 196)
    req_shutdown_unauth = urllib.request.Request(f"{url}/shutdown", method="GET")
    with pytest.raises(urllib.error.HTTPError) as cm:
        urllib.request.urlopen(req_shutdown_unauth)
    assert cm.value.code == 401

    # Test successful /shutdown GET request to cover lines 195-202 (do this last)
    req_shutdown = urllib.request.Request(f"{url}/shutdown", headers={"Authorization": f"Bearer {token}"}, method="GET")
    resp_shutdown = urllib.request.urlopen(req_shutdown)
    assert json.loads(resp_shutdown.read().decode())["status"] == "shutdown"

def test_request_work_parameter_parsing_exceptions(sandbox, env_dir, workflow_server):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    configure_stage_resources("stage1")
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=10)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})

    _, server_info = workflow_server("127.0.0.1", port=0)
    url = server_info["url"]
    token = server_info["token"]

    # Request with malformed parameters to trigger ValueErrors
    url_with_bad_params = (
        f"{url}/request_work?cpus_avail=invalid_int"
        f"&gpu_avail=invalid_gpu"
        f"&mem_avail=invalid_mem"
        f"&min_cpu_running_gpu=invalid_min"
    )
    resp = send_request(url_with_bad_params, token)
    assert resp is not None
    assert resp["status"] == "combo"

def test_request_work_allowed_excluded_filters(sandbox, env_dir, workflow_server):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    configure_stage_resources("stage1")
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=10)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})

    _, server_info = workflow_server("127.0.0.1", port=0)
    url = server_info["url"]
    token = server_info["token"]

    # Test allowed stage filter
    url_filter = f"{url}/request_work?stages=stage2"
    resp = send_request(url_filter, token)
    assert resp["status"] == "shutdown"  # No combos for stage2

    # Test exclude stage filter
    url_exclude = f"{url}/request_work?exclude_stages=stage1"
    resp = send_request(url_exclude, token)
    assert resp["status"] == "shutdown"

    # Test allowed sweeps filter
    url_sweep_filter = f"{url}/request_work?sweeps=sweep2"
    resp = send_request(url_sweep_filter, token)
    assert resp["status"] == "shutdown"

    # Test exclude sweeps filter
    url_sweep_exclude = f"{url}/request_work?exclude_sweeps=sweep1"
    resp = send_request(url_sweep_exclude, token)
    assert resp["status"] == "shutdown"

def test_request_work_stage_resources_exception_handling(sandbox, env_dir, workflow_server):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    configure_stage_resources("stage1")
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=10)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})

    _, server_info = workflow_server("127.0.0.1", port=0)
    url = server_info["url"]
    token = server_info["token"]

    # Mock load_config to raise exception ONLY during the request
    with patch("snap_workflow.utils.io.load_config", side_effect=RuntimeError("load error")):
        resp = send_request(f"{url}/request_work", token)
        assert resp["status"] == "combo"

def test_spoint_metadata_exceptions(sandbox, env_dir):
    initialize(env_dir)
    from snap_workflow.server import load_spoint_metadata, save_spoint_metadata, update_spoint_metadata
    
    # Write invalid json to spoint_metadata.json to trigger lines 30-31 exception block
    metadata_file = os.path.join(".workflow", "spoint_metadata.json")
    with open(metadata_file, "w") as f:
        f.write("invalid json")
    assert load_spoint_metadata() == {}

    # save_spoint_metadata logs error on open exception (lines 40-41)
    with patch("builtins.open", side_effect=RuntimeError("write error")), \
         patch("snap_workflow.server.logger.error") as mock_log:
        save_spoint_metadata({"test": "data"})
        mock_log.assert_called_once()

    # update_spoint_metadata lock synchronization
    update_spoint_metadata("dummy_path", "local", 100)
    meta = load_spoint_metadata()
    assert meta["dummy_path"] == {"host": "local", "size_bytes": 100}

def test_get_remote_conn_exception(sandbox, env_dir):
    initialize(env_dir)
    from snap_workflow.server import get_remote_conn
    
    # 1. Success remote connectivity check hitting line 57
    with patch("snap_workflow.cli.load_global_remotes", return_value={"Lab_Main": {"host": "Lab_Main"}}), \
         patch("snap_workflow.cli.load_local_remotes", return_value={"Lab_Main": {"path": "~/test_snap_setup"}}):
        res_type, host, path_val = get_remote_conn("Lab_Main")
        assert res_type == "remote"
        assert host == "Lab_Main"
        assert path_val == "~/test_snap_setup"

    # 2. Trigger exception branch inside get_remote_conn (line 58)
    with patch("snap_workflow.cli.load_global_remotes", side_effect=RuntimeError("load error")):
        res_type, host, path_val = get_remote_conn("some_remote")
        assert res_type is None
        assert host is None
        assert path_val is None

def test_get_dependency_rel_paths_with_convergence(sandbox, env_dir):
    initialize(env_dir)
    from snap_workflow.server import get_dependency_rel_paths
    
    # Mock get_dependent_spoint_info to return stages with convergence combos to cover lines 73-77
    mock_dep_info = {
        "dep_stage1": {
            "prop_vars": ["x"],
            "conv_vars": [],
            "conv_combos": []
        },
        "dep_stage2": {
            "prop_vars": ["x"],
            "conv_vars": ["y"],
            "conv_combos": [[1], [2]]
        }
    }
    with patch("snap_workflow.core.domain.spoints.get_dependent_spoint_info", return_value=mock_dep_info):
        paths = get_dependency_rel_paths("sweep1", "stage2", {"x": 5, "y": 10})
        assert "dep_stage1/spoints/x_5" in paths
        assert "dep_stage2/spoints/x_5_y_1" in paths
        assert "dep_stage2/spoints/x_5_y_2" in paths

def test_check_data_locality_eligibility_scenarios(sandbox, env_dir):
    initialize(env_dir)
    from snap_workflow.server import check_data_locality_eligibility
    
    with patch("snap_workflow.server.get_dependency_rel_paths", return_value=["dep1"]):
        # 1. Size > 1GB -> False deferred (line 90)
        with patch("snap_workflow.server.load_spoint_metadata", return_value={"dep1": {"host": "remote_host", "size_bytes": 2_000_000_000}}):
            runnable, status_str, detail = check_data_locality_eligibility("sweep1", "stage1", {}, "local")
            assert runnable is False
            assert status_str == "deferred"
            
        # 2. Size <= 1GB -> True sync_needed (line 94)
        with patch("snap_workflow.server.load_spoint_metadata", return_value={"dep1": {"host": "remote_host", "size_bytes": 100_000}}):
            runnable, status_str, detail = check_data_locality_eligibility("sweep1", "stage1", {}, "local")
            assert runnable is True
            assert status_str == "sync_needed"

def test_resolve_deadlock_host_scenarios(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    configure_stage_resources("stage1")
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=10)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    from snap_workflow.server import resolve_deadlock_host
    
    # 1. Successful resolve deadlock routing to max local size host (lines 113-119)
    with patch("snap_workflow.server.get_dependency_rel_paths", return_value=["dep1", "dep2"]), \
         patch("snap_workflow.server.load_spoint_metadata", return_value={"dep1": {"host": "remote1", "size_bytes": 100}, "dep2": {"host": "remote2", "size_bytes": 200}}), \
         patch("snap_workflow.cli.load_global_remotes", return_value={"remote1": {}, "remote2": {}}):
         
         host, syncs = resolve_deadlock_host("sweep1", "stage1", {"x": 5})
         assert host == "remote2"

    # 2. Case with exceptions in load_global_remotes (line 101)
    with patch("snap_workflow.cli.load_global_remotes", side_effect=RuntimeError("load error")):
        host, syncs = resolve_deadlock_host("sweep1", "stage1", {"x": 5})
        assert host == "local"
        assert syncs == []

def test_check_and_prepare_dependencies_deadlock_and_locality(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    configure_stage_resources("stage1")
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=10)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    from snap_workflow.server import check_and_prepare_dependencies
    
    # 1. target_host == best_host -> True (line 145)
    with patch("snap_workflow.core.domain.spoints.check_submittable", return_value=True), \
         patch("snap_workflow.server.check_data_locality_eligibility", return_value=(False, "deferred", ("dep1", "remote_host", 2000000000))), \
         patch("snap_workflow.server.resolve_deadlock_host", return_value=("remote_host", [("dep1", "other_host", 2000000000)])), \
         patch("snap_workflow.server.sync.transit_sync_dependency"):
        assert check_and_prepare_dependencies("sweep1", "stage1", {"x": 5}, "remote_host") is True

    # 2. target_host != best_host -> False (line 149)
    with patch("snap_workflow.core.domain.spoints.check_submittable", return_value=True), \
         patch("snap_workflow.server.check_data_locality_eligibility", return_value=(False, "deferred", ("dep1", "remote_host", 2000000000))), \
         patch("snap_workflow.server.resolve_deadlock_host", return_value=("remote_host", [("dep1", "other_host", 2000000000)])):
        assert check_and_prepare_dependencies("sweep1", "stage1", {"x": 5}, "local") is False

    # 3. is_deadlock is False (someone else is runnable) -> False (line 152)
    def mock_eligibility(sweep, stage, spoint, host):
        if host == "remote_host":
            return True, "runnable", []
        return False, "deferred", ("dep1", "remote_host", 2000000000)
    with patch("snap_workflow.core.domain.spoints.check_submittable", return_value=True), \
         patch("snap_workflow.server.check_data_locality_eligibility", side_effect=mock_eligibility), \
         patch("snap_workflow.cli.load_global_remotes", return_value={"remote_host": {}}):
        assert check_and_prepare_dependencies("sweep1", "stage1", {"x": 5}, "local") is False

    # 4. Mock load_global_remotes to raise exception in check_and_prepare_dependencies (line 134)
    with patch("snap_workflow.core.domain.spoints.check_submittable", return_value=True), \
         patch("snap_workflow.server.check_data_locality_eligibility", return_value=(False, "deferred", ("dep1", "remote_host", 2000000000))), \
         patch("snap_workflow.cli.load_global_remotes", side_effect=RuntimeError("load error")):
         assert check_and_prepare_dependencies("sweep1", "stage1", {"x": 5}, "remote_host") is False

def test_parse_memory_to_gb_edge_cases():
    from snap_workflow.server import parse_memory_to_gb
    assert parse_memory_to_gb("") == 0.0
    assert parse_memory_to_gb("16K") == 16.0 / (1024 * 1024)
    assert parse_memory_to_gb("16KB") == 16.0 / (1024 * 1024)
    assert parse_memory_to_gb("512M") == 0.5
    assert parse_memory_to_gb("512MB") == 0.5
    assert parse_memory_to_gb("4G") == 4.0
    assert parse_memory_to_gb("4GB") == 4.0
    assert parse_memory_to_gb("2T") == 2048.0
    assert parse_memory_to_gb("2TB") == 2048.0
    assert parse_memory_to_gb("16") == 16.0
    assert parse_memory_to_gb("invalid_val") == 0.0

def test_orchestrator_scheduler_exclusions_and_errors(sandbox, env_dir, workflow_server):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    configure_stage_resources("stage1")
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=10)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})

    from snap_workflow.server import OrchestratorScheduler
    
    # 1. Test exclusions mapping (exclude_stages, exclude_sweeps filters)
    scheduler = OrchestratorScheduler(
        remote="local",
        exclude_stages="stage1",
        exclude_sweeps="sweep1"
    )
    def mock_sleep(seconds):
        scheduler.shutdown_event.set()
        
    with patch("time.sleep", side_effect=mock_sleep):
        scheduler.run()
    assert scheduler.shutdown_event.is_set()

    # 2. Test registration via /submit_auto and remote checks exception branch
    srv, server_info = workflow_server("127.0.0.1", port=0)
    url = server_info["url"]
    token = server_info["token"]
    
    # Unauthorized submit_auto
    req = urllib.request.Request(f"{url}/submit_auto", method="POST")
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(req)

    # Valid submit_auto
    configure_stage_resources("stage1")
    payload = {
        "remote": "local",
        "stages": "stage1",
        "sweeps": "sweep1"
    }
    resp = send_request(f"{url}/submit_auto", token, data=payload)
    assert resp["status"] == "success"
    
    # 3. Test OrchestratorScheduler remote errors
    scheduler2 = OrchestratorScheduler(remote="unregistered_remote")
    scheduler2.run()  # Should log error and return immediately
    
    # Mock load_local_remotes to raise connection configuration load failure
    scheduler3 = OrchestratorScheduler(remote="unregistered_remote")
    with patch("snap_workflow.cli.load_global_remotes", return_value={"unregistered_remote": {"host": "host"}}), \
         patch("snap_workflow.cli.load_local_remotes", side_effect=RuntimeError("config load error")):
         scheduler3.run()  # Should log connection conn exception and return

    # 4. Test remote configuration not set up locally (lines 469-470)
    scheduler_no_local = OrchestratorScheduler(remote="remote_no_local")
    with patch("snap_workflow.cli.load_global_remotes", return_value={"remote_no_local": {"host": "host"}}), \
         patch("snap_workflow.cli.load_local_remotes", return_value={}):
         scheduler_no_local.run()

    # 5. Test workstation process completion polling branch
    scheduler4 = OrchestratorScheduler(remote="local", stages="stage1", sweeps="sweep1")
    
    # Mock proc that returns poll() == 0 (success)
    mock_proc = MagicMock()
    mock_proc.poll.side_effect = [None, 0]  # First poll returns running, second returns completed
    
    # Mock subprocess.Popen to return our mock_proc
    original_popen = subprocess.Popen
    def mock_popen(*args, **kwargs):
        return mock_proc

    # Mock time.sleep to terminate scheduler
    def mock_sleep_poll(seconds):
        scheduler4.shutdown_event.set()
        
    with patch("subprocess.Popen", side_effect=mock_popen), \
         patch("time.sleep", side_effect=mock_sleep_poll), \
         patch("snap_workflow.core.domain.status.load_status", return_value="complete"):
        # We start the stage1 task combo which transitions status
        status.write_status("initialized", "stage1/spoints/x_5")
        scheduler4.run()
        
    # Verify job completed successfully
    assert scheduler4.shutdown_event.is_set()

def test_request_work_gpu_allocation_and_backfill(sandbox, env_dir, workflow_server):
    initialize(env_dir)
    
    # Create two stages: stage_cpu and stage_gpu
    add_stage("stage_cpu", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_stage("stage_gpu", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    
    # Configure stage_cpu to have 1 CPU, 0 GPU
    env_file_cpu = os.path.join("stage_cpu", "env.json")
    with open(env_file_cpu, "r") as f:
        env_data = json.load(f)
    env_data["resources"] = {"cpus": 1, "gpus": 0, "mem": "1G"}
    with open(env_file_cpu, "w") as f:
        json.dump(env_data, f, indent=4)
        
    # Configure stage_gpu to have 2 CPUs, 1 GPU
    env_file_gpu = os.path.join("stage_gpu", "env.json")
    with open(env_file_gpu, "r") as f:
        env_data = json.load(f)
    env_data["resources"] = {"cpus": 2, "gpus": 1, "mem": "2G"}
    with open(env_file_gpu, "w") as f:
        json.dump(env_data, f, indent=4)

    add_variable("x", ["int"], add_to_stages=["stage_cpu", "stage_gpu"], default_val=10)
    add_sweep("sweep1", include_stages=["stage_cpu", "stage_gpu"], variable_values={"x": [5]})
    
    _, server_info = workflow_server("127.0.0.1", port=0)
    url = server_info["url"]
    token = server_info["token"]
    
    # Request work with GPU resources (triggers gWorker prioritization and GPU search)
    resp = send_request(f"{url}/request_work?gpu_avail=1&cpus_avail=4&mem_avail=4.0", token)
    assert resp is not None
    assert resp["stage"] == "stage_gpu"
    
    # Request work with CPU reservation check backfilling: min_cpu_running_gpu = 1, max_gpu_task_cpu_req = 2
    # Cpus_avail = 2. Cpus_avail - cpu_req (1) + min_cpu_running_gpu (1) >= max_gpu_task_cpu_req (2) -> True
    resp_backfill = send_request(f"{url}/request_work?gpu_avail=1&cpus_avail=2&mem_avail=4.0&min_cpu_running_gpu=1", token)
    assert resp_backfill is not None
    assert resp_backfill["stage"] == "stage_cpu"

    # 3. Test gWorker shutdown path (lines 367-372)
    # Set status of GPU spoint to complete, then requesting work again with gpu_avail=1 should return shutdown
    status.write_status("complete", "stage_gpu/spoints/x_5")
    resp_shutdown = send_request(f"{url}/request_work?gpu_avail=1&cpus_avail=4&mem_avail=4.0", token)
    assert resp_shutdown["status"] == "shutdown"

    # 4. Test idle path (line 380)
    # Set status of GPU spoint back to "submitted"
    status.write_status("submitted", "stage_gpu/spoints/x_5")
    # Request work with gpu_avail=-1 (CPU-only) -> should return idle (because stage_cpu is submitted, so there is still incomplete CPU task, but none submittable)
    status.write_status("submitted", "stage_cpu/spoints/x_5")
    resp_idle = send_request(f"{url}/request_work?gpu_avail=-1&cpus_avail=4&mem_avail=4.0", token)
    assert resp_idle["status"] == "idle"

def test_check_and_prepare_dependencies_sync_needed(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    configure_stage_resources("stage1")
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=10)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    from snap_workflow.server import check_and_prepare_dependencies

    # 5. target_host has sync_needed -> returns True, runs ssh sync commands (mocked)
    with patch("snap_workflow.core.domain.spoints.check_submittable", return_value=True), \
         patch("snap_workflow.server.check_data_locality_eligibility", return_value=(True, "sync_needed", [("dep1", "remote_host", 1000)])), \
         patch("snap_workflow.server.get_remote_conn", return_value=("remote", "ssh_host", "/path")), \
         patch("snap_workflow.server.sync.transit_sync_dependency") as mock_sync_dep:
         
        assert check_and_prepare_dependencies("sweep1", "stage1", {"x": 5}, "local") is True
        mock_sync_dep.assert_called_once()

def test_orchestrator_scheduler_additional_branches(sandbox, env_dir):
    initialize(env_dir)
    # Add a stage to trigger lines 555-556 load config exception block
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    configure_stage_resources("stage1")
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=10)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    from snap_workflow.server import OrchestratorScheduler

    # 1. Test other scheduler detected aborts scheduler (lines 490-510)
    scheduler_abort = OrchestratorScheduler(remote="local")
    def mock_run_scheduler(cmd, *args, **kwargs):
        if "sbatch" in cmd[1]:
            ret = MagicMock()
            ret.returncode = 1
            return ret
        elif "qsub" in cmd[1]:
            ret = MagicMock()
            ret.returncode = 0
            return ret
        ret = MagicMock()
        ret.returncode = 1
        return ret
    with patch("subprocess.run", side_effect=mock_run_scheduler):
        scheduler_abort.run()

    # 2. Test exceptions in other scheduler detect (lines 505-506)
    scheduler_except = OrchestratorScheduler(remote="local")
    def mock_run_except(cmd, *args, **kwargs):
        if "sbatch" in cmd[1]:
            ret = MagicMock()
            ret.returncode = 1
            return ret
        raise RuntimeError("run error")
    with patch("subprocess.run", side_effect=mock_run_except), \
         patch("time.sleep", side_effect=lambda x: scheduler_except.shutdown_event.set()):
         scheduler_except.run()

    # 3. Load config failure in stage resources (lines 555-556)
    scheduler_res_err = OrchestratorScheduler(remote="local")
    with patch("snap_workflow.utils.io.load_config", side_effect=RuntimeError("load error")), \
         patch("time.sleep", side_effect=lambda x: scheduler_res_err.shutdown_event.set()):
         scheduler_res_err.run()

    # 4. Remote auto-detect exception warning (lines 574-576)
    scheduler_remote_err = OrchestratorScheduler(remote="Lab_Main")
    def mock_run_remote(cmd, *args, **kwargs):
        if "sbatch" in cmd:
            ret = MagicMock()
            ret.returncode = 1
            return ret
        elif "ssh" in cmd[0]:
            raise RuntimeError("ssh error")
        ret = MagicMock()
        ret.returncode = 1
        return ret
    with patch("snap_workflow.cli.load_global_remotes", return_value={"Lab_Main": {"host": "Lab_Main"}}), \
         patch("snap_workflow.cli.load_local_remotes", return_value={"Lab_Main": {"path": "/path"}}), \
         patch("subprocess.run", side_effect=mock_run_remote), \
         patch("time.sleep", side_effect=lambda x: scheduler_remote_err.shutdown_event.set()):
         scheduler_remote_err.run()

def test_orchestrator_slurm_mode(sandbox, env_dir):
    initialize(env_dir)
    # Pass num_jobs and multi_submission in sbatch_details
    add_stage("stage1", sbatch_details={"num_jobs": "1", "multi_submission": False, "cpus": "1"}, stage_variables=["x"], stage_dependencies=[])
    configure_stage_resources("stage1")
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=10)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    from snap_workflow.server import OrchestratorScheduler

    # 1. Test local Slurm polling and local sbatch submit (line 589)
    scheduler_local = OrchestratorScheduler(remote="local", stages="stage1", sweeps="sweep1")
    status.write_status("submitted", "stage1/spoints/x_5")

    def mock_run_local(cmd, *args, **kwargs):
        if "sbatch" in cmd:
            ret = MagicMock()
            ret.returncode = 0
            return ret
        ret = MagicMock()
        ret.returncode = 1
        return ret

    with patch("subprocess.run", side_effect=mock_run_local), \
         patch("time.sleep", side_effect=lambda x: scheduler_local.shutdown_event.set()):
         scheduler_local.run()

    # 2. Test remote Slurm polling (completed) and sync triggers (lines 591-606)
    scheduler_remote = OrchestratorScheduler(remote="Lab_Main", stages="stage1", sweeps="sweep1")
    status.write_status("submitted", "stage1/spoints/x_5")

    def mock_run_remote(cmd, *args, **kwargs):
        ret = MagicMock()
        if "sbatch" in cmd:
            ret.returncode = 0
            return ret
        if "ssh" in cmd[0]:
            if "python3 -c" in cmd[2] or "python -c" in cmd[2]:
                ret.returncode = 0
                return ret
            if "which sbatch" in cmd[2] or "sbatch" in cmd[2]:
                ret.returncode = 0
                return ret
            if "cat" in cmd[2]:
                ret.returncode = 0
                ret.stdout = "complete"
                return ret
        ret.returncode = 1
        return ret

    with patch("snap_workflow.cli.load_global_remotes", return_value={"Lab_Main": {"host": "Lab_Main"}}), \
         patch("snap_workflow.cli.load_local_remotes", return_value={"Lab_Main": {"path": "/path"}}), \
         patch("subprocess.run", side_effect=mock_run_remote), \
         patch("snap_workflow.server.get_remote_conn", return_value=("remote", "Lab_Main", "/path")), \
         patch("snap_workflow.server.sync.measure_directory_size", return_value=123), \
         patch("snap_workflow.server.update_spoint_metadata") as mock_update, \
         patch("snap_workflow.server.sync.pull_spoint_data") as mock_pull, \
         patch("time.sleep", side_effect=lambda x: scheduler_remote.shutdown_event.set()):
         
         scheduler_remote.run()
         mock_update.assert_called_once()
         mock_pull.assert_called_once()

    # 3. Test remote Slurm polling (failed/error) (line 608)
    scheduler_remote_fail = OrchestratorScheduler(remote="Lab_Main", stages="stage1", sweeps="sweep1")
    status.write_status("submitted", "stage1/spoints/x_5")

    def mock_run_remote_fail(cmd, *args, **kwargs):
        ret = MagicMock()
        if "sbatch" in cmd:
            ret.returncode = 0
            return ret
        if "ssh" in cmd[0]:
            if "which sbatch" in cmd[2] or "sbatch" in cmd[2]:
                ret.returncode = 0
                return ret
            if "cat" in cmd[2]:
                ret.returncode = 0
                ret.stdout = "error"
                return ret
        ret.returncode = 1
        return ret

    with patch("snap_workflow.cli.load_global_remotes", return_value={"Lab_Main": {"host": "Lab_Main"}}), \
         patch("snap_workflow.cli.load_local_remotes", return_value={"Lab_Main": {"path": "/path"}}), \
         patch("subprocess.run", side_effect=mock_run_remote_fail), \
         patch("snap_workflow.server.get_remote_conn", return_value=("remote", "Lab_Main", "/path")), \
         patch("snap_workflow.server.sync.measure_directory_size", return_value=123), \
         patch("snap_workflow.server.update_spoint_metadata"), \
         patch("snap_workflow.server.sync.pull_spoint_data"), \
         patch("time.sleep", side_effect=lambda x: scheduler_remote_fail.shutdown_event.set()):
         
         scheduler_remote_fail.run()

    # 4. Test remote Slurm polling exception (lines 595-596)
    scheduler_remote_except = OrchestratorScheduler(remote="Lab_Main", stages="stage1", sweeps="sweep1")
    status.write_status("submitted", "stage1/spoints/x_5")

    def mock_run_remote_except(cmd, *args, **kwargs):
        if "sbatch" in cmd:
            ret = MagicMock()
            ret.returncode = 0
            return ret
        if "ssh" in cmd[0]:
            if "which sbatch" in cmd[2] or "sbatch" in cmd[2]:
                ret.returncode = 0
                return ret
            if "cat" in cmd[2]:
                raise RuntimeError("ssh cat error")
        ret = MagicMock()
        ret.returncode = 1
        return ret

    with patch("snap_workflow.cli.load_global_remotes", return_value={"Lab_Main": {"host": "Lab_Main"}}), \
         patch("snap_workflow.cli.load_local_remotes", return_value={"Lab_Main": {"path": "/path"}}), \
         patch("subprocess.run", side_effect=mock_run_remote_except), \
         patch("time.sleep", side_effect=lambda x: scheduler_remote_except.shutdown_event.set()):
         scheduler_remote_except.run()

    # 5. Test remote Slurm submit job initialized (lines 634-639) & auto-submitted log (lines 642-643)
    scheduler_remote_submit = OrchestratorScheduler(remote="Lab_Main", stages="stage1", sweeps="sweep1")
    status.write_status("initialized", "stage1/spoints/x_5")

    def mock_run_remote_submit(cmd, *args, **kwargs):
        ret = MagicMock()
        if "sbatch" in cmd or "which sbatch" in cmd:
            ret.returncode = 0
            return ret
        if "ssh" in cmd[0]:
            if "sbatch" in cmd[2]:
                ret.returncode = 0
                return ret
        ret.returncode = 1
        return ret

    with patch("snap_workflow.cli.load_global_remotes", return_value={"Lab_Main": {"host": "Lab_Main"}}), \
         patch("snap_workflow.cli.load_local_remotes", return_value={"Lab_Main": {"path": "/path"}}), \
         patch("subprocess.run", side_effect=mock_run_remote_submit), \
         patch("snap_workflow.server.check_and_prepare_dependencies", return_value=True), \
         patch("time.sleep", side_effect=lambda x: scheduler_remote_submit.shutdown_event.set()):
         scheduler_remote_submit.run()

    # 6. Test dependency prepare returns False -> continue (line 619)
    scheduler_dep_fail = OrchestratorScheduler(remote="local", stages="stage1", sweeps="sweep1")
    status.write_status("initialized", "stage1/spoints/x_5")
    with patch("subprocess.run", side_effect=mock_run_local), \
         patch("snap_workflow.server.check_and_prepare_dependencies", return_value=False), \
         patch("time.sleep", side_effect=lambda x: scheduler_dep_fail.shutdown_event.set()):
         scheduler_dep_fail.run()

    # 7. Test auto-submit shutdown break (line 613)
    scheduler_break = OrchestratorScheduler(remote="local", stages="stage1", sweeps="sweep1")
    status.write_status("initialized", "stage1/spoints/x_5")
    def mock_check_and_prepare_dep(sweep, stage, spoint, host):
        scheduler_break.shutdown_event.set()
        return True
    with patch("subprocess.run", side_effect=mock_run_local), \
         patch("snap_workflow.server.check_and_prepare_dependencies", side_effect=mock_check_and_prepare_dep), \
         patch("time.sleep", side_effect=lambda x: scheduler_break.shutdown_event.set()):
         scheduler_break.run()

    # 8. Test auto-submit failure logging branch (line 645)
    scheduler_fail = OrchestratorScheduler(remote="local", stages="stage1", sweeps="sweep1")
    status.write_status("initialized", "stage1/spoints/x_5")
    
    def mock_run_fail(cmd, *args, **kwargs):
        if "sbatch" in cmd[0]:
            ret = MagicMock()
            ret.returncode = 1
            ret.stderr = "sbatch submission failed error text"
            return ret
        ret = MagicMock()
        ret.returncode = 0
        return ret

    with patch("subprocess.run", side_effect=mock_run_fail), \
         patch("snap_workflow.server.check_and_prepare_dependencies", return_value=True), \
         patch("time.sleep", side_effect=lambda x: scheduler_fail.shutdown_event.set()):
         scheduler_fail.run()

def test_orchestrator_workstation_mode_additional_branches(sandbox, env_dir):
    initialize(env_dir)
    # Configure CPU and GPU stages
    add_stage("stage_gpu", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    # Configure stage_gpu to have 2 CPUs, 1 GPU
    env_file_gpu = os.path.join("stage_gpu", "env.json")
    with open(env_file_gpu, "r") as f:
        env_data = json.load(f)
    env_data["resources"] = {"cpus": 2, "gpus": 1, "mem": "2G"}
    with open(env_file_gpu, "w") as f:
        json.dump(env_data, f, indent=4)
        
    add_variable("x", ["int"], add_to_stages=["stage_gpu"], default_val=10)
    add_sweep("sweep1", include_stages=["stage_gpu"], variable_values={"x": [5]})
    from snap_workflow.server import OrchestratorScheduler, register_auto_scheduler

    scheduler = OrchestratorScheduler(remote="local", stages="stage_gpu", sweeps="sweep1")
    status.write_status("initialized", "stage_gpu/spoints/x_5")

    # Mock workstation spawn process with GPU index & terminate-on-shutdown branch
    mock_proc = MagicMock()
    mock_proc.poll.side_effect = [None, None] # Keep running so terminate gets called
    
    sleep_count = 0
    def mock_sleep_poll(seconds):
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count >= 2:
            scheduler.shutdown_event.set()

    with patch("snap_workflow.worker.detect_system_resources", return_value=(8, 1, 16.0)), \
         patch("subprocess.Popen", return_value=mock_proc) as mock_popen, \
         patch("time.sleep", side_effect=mock_sleep_poll), \
         patch("snap_workflow.server.get_remote_conn", return_value=("remote", "ssh_host", "/path")), \
         patch("snap_workflow.server.check_and_prepare_dependencies", return_value=True):
         scheduler.run()
         
    # Verify CUDA_VISIBLE_DEVICES env var was populated correctly in local process spawn (line 704)
    called_env = mock_popen.call_args[1]["env"]
    assert called_env["CUDA_VISIBLE_DEVICES"] == "0"
    # Verify proc terminate was called at thread exit (line 736)
    mock_proc.terminate.assert_called_once()

    # Test local workstation process completion with failure (poll returns 1) to cover lines 665-667
    scheduler_fail = OrchestratorScheduler(remote="local", stages="stage_gpu", sweeps="sweep1")
    status.write_status("initialized", "stage_gpu/spoints/x_5")
    mock_proc_fail = MagicMock()
    mock_proc_fail.poll.side_effect = [None, 1] # First poll is running, second is completed with failure (exit code 1)
    
    sleep_count_fail = 0
    def mock_sleep_poll_fail(seconds):
        nonlocal sleep_count_fail
        sleep_count_fail += 1
        if sleep_count_fail >= 3:
            scheduler_fail.shutdown_event.set()

    with patch("snap_workflow.worker.detect_system_resources", return_value=(8, 1, 16.0)), \
         patch("subprocess.Popen", return_value=mock_proc_fail), \
         patch("time.sleep", side_effect=mock_sleep_poll_fail), \
         patch("snap_workflow.server.get_remote_conn", return_value=("remote", "ssh_host", "/path")), \
         patch("snap_workflow.server.check_and_prepare_dependencies", return_value=True):
         scheduler_fail.run()

    # Test local workstation process completion with success (poll returns 0) to cover lines 654-664
    scheduler_success = OrchestratorScheduler(remote="local", stages="stage_gpu", sweeps="sweep1")
    status.write_status("initialized", "stage_gpu/spoints/x_5")
    mock_proc_success = MagicMock()
    mock_proc_success.poll.side_effect = [None, 0] # First poll is running, second is completed with success (exit code 0)
    
    sleep_count_success = 0
    def mock_sleep_poll_success(seconds):
        nonlocal sleep_count_success
        sleep_count_success += 1
        if sleep_count_success >= 3:
            scheduler_success.shutdown_event.set()

    with patch("snap_workflow.worker.detect_system_resources", return_value=(8, 1, 16.0)), \
         patch("subprocess.Popen", return_value=mock_proc_success), \
         patch("time.sleep", side_effect=mock_sleep_poll_success), \
         patch("snap_workflow.server.get_remote_conn", return_value=("local", None, None)), \
         patch("snap_workflow.server.sync.measure_directory_size", return_value=100), \
         patch("snap_workflow.server.update_spoint_metadata") as mock_update_work, \
         patch("snap_workflow.server.sync.pull_spoint_data") as mock_pull_work, \
         patch("snap_workflow.core.domain.spoints.get_dependent_spoint_info", return_value={}), \
         patch("snap_workflow.core.domain.spoints.link_dependent_combo") as mock_link_work, \
         patch("snap_workflow.server.check_and_prepare_dependencies", return_value=True):
         scheduler_success.run()

    mock_update_work.assert_called_once()
    mock_pull_work.assert_called_once()
    mock_link_work.assert_called_once()

    # Test remote workstation process spawn with CUDA visible devices
    scheduler_remote = OrchestratorScheduler(remote="Lab_Main", stages="stage_gpu", sweeps="sweep1")
    status.write_status("initialized", "stage_gpu/spoints/x_5")
    mock_proc_remote = MagicMock()
    mock_proc_remote.poll.return_value = None
    
    def mock_run_remote_workstation(cmd, *args, **kwargs):
        ret = MagicMock()
        if "python3 -c" in str(cmd) or "python -c" in str(cmd):
            ret.returncode = 0
            if "detect_system_resources" in str(cmd):
                ret.stdout = "[8, 1, 16.0]"
            return ret
        if "sbatch" in cmd or "which sbatch" in cmd:
            ret.returncode = 1
            return ret
        ret.returncode = 1
        return ret
    
    with patch("snap_workflow.cli.load_global_remotes", return_value={"Lab_Main": {"host": "Lab_Main"}}), \
         patch("snap_workflow.cli.load_local_remotes", return_value={"Lab_Main": {"path": "/path"}}), \
         patch("subprocess.Popen", return_value=mock_proc_remote) as mock_popen_remote, \
         patch("subprocess.run", side_effect=mock_run_remote_workstation), \
         patch("snap_workflow.server.check_and_prepare_dependencies", return_value=True), \
         patch("time.sleep", side_effect=lambda x: scheduler_remote.shutdown_event.set()):
         scheduler_remote.run()
         
    # Verify cmd for ssh workstation GPU export was constructed correctly (line 711)
    called_cmd = mock_popen_remote.call_args[0][0]
    assert "export CUDA_VISIBLE_DEVICES=0" in called_cmd[2]

    # Test register_auto_scheduler checking already running thread (lines 745-748)
    mock_server = MagicMock()
    mock_thread = MagicMock()
    mock_thread.is_alive.return_value = True
    mock_server.auto_schedulers = {"local": mock_thread}
    register_auto_scheduler(mock_server, "local")
    mock_thread.start.assert_not_called()

def test_run_server_foreground(sandbox, env_dir):
    initialize(env_dir)
    # Test run_server_foreground KeyboardInterrupt and auto-scheduler teardown
    mock_server = MagicMock()
    mock_server.server_port = 8080
    mock_server.serve_forever.side_effect = KeyboardInterrupt()
    mock_thread = MagicMock()
    mock_server.auto_schedulers = {"local": mock_thread}
    
    with patch("snap_workflow.server.HTTPServer", return_value=mock_server), \
         patch("snap_workflow.server.stage_tools.validate_stage_resources"), \
         patch("snap_workflow.server.setup_logging"):
        
        from snap_workflow.server import run_server_foreground
        run_server_foreground()
        
        mock_thread.shutdown_event.set.assert_called_once()
        mock_thread.join.assert_called_once()
        mock_server.server_close.assert_called_once()

def test_get_stage_depth():
    from snap_workflow.server import get_stage_depth
    stages_dict = {
        "stage1": {"dependent_stages": []},
        "stage2": {"dependent_stages": ["stage1"]}
    }
    # 1. cache is None (line 848)
    assert get_stage_depth("stage1", stages_dict) == 0
    
    # 2. caching/recursion (line 856)
    cache = {}
    assert get_stage_depth("stage2", stages_dict, cache) == 1
    # 3. cached hit (line 850)
    assert get_stage_depth("stage2", stages_dict, cache) == 1

def test_notify_shutdown_endpoint(sandbox, env_dir, workflow_server):
    initialize(env_dir)
    srv, server_info = workflow_server("127.0.0.1", port=0)
    port = server_info["port"]
    token = server_info["token"]
    
    # 1. Test notification with local worker
    import urllib.request
    import json
    
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/notify_shutdown",
        data=json.dumps({"worker_id": "test_local_worker", "host": "local"}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode())
    assert res == {"status": "ok"}
    
    # 2. Test notification with remote worker (mocking get_remote_conn and pull_worker_logs)
    from unittest.mock import patch
    with patch("snap_workflow.server.get_remote_conn", return_value=("remote", "Lab_Main", "~/some_path")), \
         patch("snap_workflow.server.sync.pull_worker_logs") as mock_pull:
         
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/notify_shutdown",
            data=json.dumps({"worker_id": "test_remote_worker", "host": "remote_host"}).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            res = json.loads(resp.read().decode())
        assert res == {"status": "ok"}
        mock_pull.assert_called_once_with("remote", "Lab_Main", "~/some_path")

