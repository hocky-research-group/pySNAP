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
    initialize(env_dir)
    _, server_info = workflow_server("127.0.0.1", port=0)
    url = server_info["url"]
    
    req = urllib.request.Request(f"{url}/request_work", method="GET")
    with pytest.raises(urllib.error.HTTPError) as cm:
        urllib.request.urlopen(req)
    assert cm.value.code == 401

    req = urllib.request.Request(f"{url}/request_work", headers={"Authorization": "Bearer badtoken"}, method="GET")
    with pytest.raises(urllib.error.HTTPError) as cm:
        urllib.request.urlopen(req)
    assert cm.value.code == 401

def test_work_allocation_and_notification(sandbox, env_dir, workflow_server):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    
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
    
    resp = send_request(f"{url}/request_work", token)
    assert resp is not None
    assert resp["status"] == "spoint"
    assert resp["stage"] == "stage1"
    assert resp["spoint_dict"] == {"x": 5}
    
    status_file = os.path.join("stage1", "spoints", "x_5", ".spoint_info", "status")
    with open(status_file, "r") as f:
        assert f.read().strip() == "submitted"
        
    payload = {
        "sweep": "sweep1",
        "stage": "stage1",
        "spoint_dict": {"x": 5},
        "status": "complete"
    }
    notify_resp = send_request(f"{url}/notify_completion", token, data=payload)
    assert notify_resp["status"] == "ok"
    
    with open(status_file, "r") as f:
        assert f.read().strip() == "complete"
        
    idle_resp = send_request(f"{url}/request_work", token)
    assert idle_resp["status"] == "shutdown"

def is_ssh_reachable():
    try:
        res = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=2", "Lab_Main", "echo", "ping"],
            capture_output=True, text=True, timeout=3
        )
        return res.returncode == 0
    except Exception:
        return False

def test_orchestrator_scheduler_live_ssh(sandbox, env_dir, tmp_path):
    initialize(env_dir)
    if not is_ssh_reachable():
        pytest.skip("Lab_Main SSH connection not reachable (set RUN_LIVE_SSH_TESTS=1 to run)")

    from snap_workflow.utils.constants import LOCAL_REMOTES_FILE
    global_config_dir = os.path.join(tmp_path, ".snap_workflow")
    os.makedirs(global_config_dir, exist_ok=True)
    global_remotes_file = os.path.join(global_config_dir, "remotes.json")

    global_remotes = {"Lab_Main": {"host": "Lab_Main"}}
    with open(global_remotes_file, "w") as f:
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

    from snap_workflow.server import OrchestratorScheduler
    scheduler = OrchestratorScheduler(
        remote="Lab_Main",
        stages="stage1",
        sweeps="sweep1"
    )

    def mock_sleep(seconds=None):
        scheduler.shutdown_event.set()

    with patch("snap_workflow.utils.constants.GLOBAL_CONFIG_DIR", global_config_dir), \
         patch("snap_workflow.utils.constants.GLOBAL_REMOTES_FILE", global_remotes_file), \
         patch("snap_workflow.utils.constants.GLOBAL_CONFIG_DIR", global_config_dir), \
         patch("snap_workflow.utils.constants.GLOBAL_REMOTES_FILE", global_remotes_file), \
         patch("time.sleep", side_effect=mock_sleep), \
         patch("threading.Event.wait", side_effect=mock_sleep):
        scheduler.run()

    assert scheduler.shutdown_event.is_set()

def test_unauthorized_endpoints(sandbox, env_dir, workflow_server):
    initialize(env_dir)
    _, server_info = workflow_server("127.0.0.1", port=0)
    url = server_info["url"]
    
    req = urllib.request.Request(f"{url}/notify_completion", headers={"Authorization": "Bearer badtoken"}, method="POST")
    with pytest.raises(urllib.error.HTTPError) as cm:
        urllib.request.urlopen(req)
    assert cm.value.code == 401

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

    req_shutdown_unauth = urllib.request.Request(f"{url}/shutdown", method="GET")
    with pytest.raises(urllib.error.HTTPError) as cm:
        urllib.request.urlopen(req_shutdown_unauth)
    assert cm.value.code == 401

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

    url_with_bad_params = (
        f"{url}/request_work?cpus_avail=invalid_int"
        f"&gpu_avail=invalid_gpu"
        f"&mem_avail=invalid_mem"
        f"&min_cpu_running_gpu=invalid_min"
    )
    resp = send_request(url_with_bad_params, token)
    assert resp is not None
    assert resp["status"] == "spoint"

def test_request_work_allowed_excluded_filters(sandbox, env_dir, workflow_server):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    configure_stage_resources("stage1")
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=10)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})

    _, server_info = workflow_server("127.0.0.1", port=0)
    url = server_info["url"]
    token = server_info["token"]

    url_filter = f"{url}/request_work?stages=stage2"
    resp = send_request(url_filter, token)
    assert resp["status"] == "shutdown"

    url_exclude = f"{url}/request_work?exclude_stages=stage1"
    resp = send_request(url_exclude, token)
    assert resp["status"] == "shutdown"

    url_sweep_filter = f"{url}/request_work?sweeps=sweep2"
    resp = send_request(url_sweep_filter, token)
    assert resp["status"] == "shutdown"

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

    with patch("snap_workflow.utils.io.load_config", side_effect=RuntimeError("load error")):
        resp = send_request(f"{url}/request_work", token)
        assert resp["status"] == "spoint"

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

def test_notify_completion_spoint_path_and_shutdown(sandbox, env_dir, workflow_server):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    configure_stage_resources("stage1")
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=10)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})

    _, server_info = workflow_server("127.0.0.1", port=0)
    url = server_info["url"]
    token = server_info["token"]

    # 1. notify_completion with spoint_path format
    payload1 = {
        "spoint_path": "stage1/spoints/x_5",
        "status": "complete",
        "host": "remote_host"
    }
    with patch("subprocess.run"):
        resp1 = send_request(f"{url}/notify_completion", token, data=payload1)
        assert resp1["status"] == "ok"

    # 2. notify_shutdown
    payload2 = {
        "worker_id": "worker_1",
        "host": "local"
    }
    resp2 = send_request(f"{url}/notify_shutdown", token, data=payload2)
    assert resp2["status"] == "ok"

    # 3. submit_worker
    payload3 = {
        "name": "local",
        "num_workers": 1,
        "profile": "cpu"
    }
    with patch("snap_workflow.worker.slurm.launch_local_workers"):
        resp3 = send_request(f"{url}/submit_worker", token, data=payload3)
        assert resp3["status"] == "success"

def test_run_server_foreground(sandbox, env_dir):
    initialize(env_dir)
    with patch("snap_workflow.server.daemon.WorkflowServer") as mock_srv_cls:
        mock_srv = MagicMock()
        mock_srv.server_address = ("127.0.0.1", 9999)
        mock_srv.token = "test_token"
        mock_srv.serve_forever.side_effect = KeyboardInterrupt
        mock_srv_cls.return_value = mock_srv

        from snap_workflow.server.daemon import run_server_foreground
        run_server_foreground("127.0.0.1", 9999)
        assert mock_srv.server_close.called
