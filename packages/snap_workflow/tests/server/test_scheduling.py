import os
import json
import pytest
import time
from unittest.mock import patch, MagicMock

from snap_workflow.core import initialize, add_stage, add_variable, add_sweep
from snap_workflow.core.domain.stages import validate_stage_resources
from snap_workflow.server import start_server, get_stage_depth, OrchestratorScheduler
from snap_workflow.dispatcher import detect_system_resources, dispatcher_loop, send_request, parse_memory_to_gb
from snap_workflow.core.domain import status

def test_stage_resource_validation(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    
    with pytest.raises(ValueError) as exc:
        validate_stage_resources()
    assert "unconfigured resources" in str(exc.value)

    env_file = os.path.join("stage1", "env.json")
    with open(env_file, "r") as f:
        env_data = json.load(f)
    env_data["resources"] = {"cpus": 4, "gpus": 1, "mem": "16G"}
    with open(env_file, "w") as f:
        json.dump(env_data, f, indent=4)
        
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

    _, server_info = workflow_server("127.0.0.1", port=0)
    url = server_info["url"]
    token = server_info["token"]

    c_resp = send_request(f"{url}/request_work?cpus_avail=8&gpu_avail=-1&mem_avail=16.0", token)
    assert c_resp["status"] == "spoint"
    assert c_resp["stage"] == "stage1"

    status.write_status("initialized", os.path.join("stage1", "spoints", "x_5"))

    g_resp = send_request(f"{url}/request_work?cpus_avail=8&gpu_avail=0&mem_avail=16.0&min_cpu_running_gpu=4", token)
    assert g_resp["status"] == "spoint"
    assert g_resp["stage"] == "stage1"

    status.write_status("initialized", os.path.join("stage1", "spoints", "x_5"))

    g_reserve_resp = send_request(f"{url}/request_work?cpus_avail=4&gpu_avail=1&mem_avail=16.0&min_cpu_running_gpu=0", token)
    assert g_reserve_resp["status"] in ["idle", "none"]

    g_reserve_resp2 = send_request(f"{url}/request_work?cpus_avail=6&gpu_avail=1&mem_avail=16.0&min_cpu_running_gpu=0", token)
    assert g_reserve_resp2["status"] == "spoint"
    assert g_reserve_resp2["stage"] == "stage1"

def test_worker_task_filtering(sandbox, env_dir, workflow_server):
    initialize(env_dir)
    
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

    _, server_info = workflow_server("127.0.0.1", port=0)
    url = server_info["url"]
    token = server_info["token"]

    resp = send_request(f"{url}/request_work?cpus_avail=4&gpu_avail=-1&mem_avail=8.0&stages=stage1", token)
    assert resp["status"] == "spoint"
    assert resp["stage"] == "stage1"
    
    status.write_status("complete", os.path.join("stage1", "spoints", "x_5"))
    
    resp = send_request(f"{url}/request_work?cpus_avail=4&gpu_avail=-1&mem_avail=8.0&stages=stage1", token)
    assert resp["status"] == "shutdown"

    status.write_status("initialized", os.path.join("stage1", "spoints", "x_5"))

    resp = send_request(f"{url}/request_work?cpus_avail=4&gpu_avail=-1&mem_avail=8.0&exclude_stages=stage1", token)
    assert resp["status"] == "spoint"
    assert resp["stage"] == "stage2"

    status.write_status("initialized", os.path.join("stage2", "spoints", "x_5"))

    resp = send_request(f"{url}/request_work?cpus_avail=4&gpu_avail=-1&mem_avail=8.0&sweeps=sweep2", token)
    assert resp["status"] == "spoint"
    assert resp["sweep"] == "sweep2"

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
        
        with patch("subprocess.run") as mock_run_add:
            mock_res_add = MagicMock()
            mock_res_add.stdout = "ok\n"
            mock_run_add.return_value = mock_res_add
            remote_add_cmd("workflow remote add", ["my_workstation", "--host", "tanner@workstation.local"])
        
        global_data = load_global_remotes()
        assert "my_workstation" in global_data
        assert global_data["my_workstation"]["host"] == "tanner@workstation.local"
        
        from snap_workflow.utils.version import __version__ as local_ver

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

        from snap_workflow.cli.server import server_reserve_cmd
        with pytest.raises(ValueError) as exc:
            server_reserve_cmd("workflow server reserve", ["my_workstation", "template", "--num-workers", "1"])
        assert "Manager server is not running" in str(exc.value)

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

        from snap_workflow.dispatcher.controller import DispatcherController
        def mock_send_request(url, token, data=None, *args, **kwargs):
            if data and data.get("name") == "local":
                ctrl = DispatcherController(
                    target_name="local",
                    mode="subprocess",
                    num_workers=data.get("num_workers", 1),
                    stages=data.get("stages", ""),
                    sweeps=data.get("sweeps", ""),
                    exclude_stages=data.get("exclude_stages", ""),
                    exclude_sweeps=data.get("exclude_sweeps", ""),
                    profile=data.get("profile", "cpu")
                )
                ctrl.start()
                return {"status": "success", "message": "Spawned local workers"}
            return {"status": "success"}

        with patch("snap_workflow.utils.exec.has_slurm", return_value=True), \
             patch("subprocess.Popen") as mock_popen, \
             patch("snap_workflow.server.api.send_request", side_effect=mock_send_request):
            server_reserve_cmd("workflow server reserve", ["local", "cpu", "--num-workers", "3", "--stage", "stage1"])
            assert mock_popen.call_count == 3
            first_args = mock_popen.call_args_list[0][0][0]
            assert any("snap_workflow.dispatcher" in arg for arg in first_args)
            assert "--stages" in first_args
            assert "stage1" in first_args

def test_auto_scheduling(sandbox, env_dir, workflow_server):
    initialize(env_dir)
    
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

    srv, server_info = workflow_server("127.0.0.1", port=0)

    from snap_workflow.cli.server import server_auto_cmd
    from snap_workflow.utils.constants import SERVER_INFO

    with open(SERVER_INFO, "w") as f:
        json.dump(server_info, f)
        
    mock_run_res = MagicMock()
    mock_run_res.returncode = 1
    
    with patch("subprocess.run", return_value=mock_run_res), \
         patch("snap_workflow.server.scheduler.detect_system_resources", return_value=(8, 2, 16.0)), \
         patch("snap_workflow.dispatcher.runner.detect_system_resources", return_value=(8, 2, 16.0)), \
         patch("subprocess.Popen") as mock_popen:
         
        server_auto_cmd("workflow server auto", ["local"])
        
        assert hasattr(srv, "auto_schedulers")
        assert "local" in srv.auto_schedulers
        scheduler = srv.auto_schedulers["local"]
        assert scheduler.is_alive()
        
        time.sleep(1.0)
        
        assert mock_popen.called
        call_envs = [call[1].get("env", {}) for call in mock_popen.call_args_list if call[1] and "env" in call[1]]
        assert any("CUDA_VISIBLE_DEVICES" in env for env in call_envs)
        
        spoint_path = os.path.join("stage1", "spoints", "x_5")
        assert status.load_status(spoint_path) == "running"
        
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

    from snap_workflow.cli.server import server_auto_cmd
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
         
        server_auto_cmd("workflow server auto", ["local"])
        
        scheduler = srv.auto_schedulers["local"]
        scheduler.join(timeout=2.0)
        
        assert not scheduler.is_alive()
        assert not mock_popen.called

def test_local_slurm_auto_scheduling(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    env_file = os.path.join("stage1", "env.json")
    with open(env_file, "r") as f:
        env_data = json.load(f)
    env_data["resources"] = {"cpus": 1, "gpus": 0, "mem": "1G"}
    env_data["sbatch"] = {"partition": "normal"}
    with open(env_file, "w") as f:
        json.dump(env_data, f)
        
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=10)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})

    mock_server = MagicMock()
    from snap_workflow.core.domain import spoints
    mock_server.spoint_manager = spoints.SPointStatusManager()
    mock_server.server_port = 9999
    mock_server.token = "token"

    scheduler = OrchestratorScheduler(remote="local", stages="stage1", sweeps="sweep1", server=mock_server)

    def mock_run_slurm(cmd, *args, **kwargs):
        res = MagicMock()
        if "which" in cmd and "sbatch" in cmd:
            res.returncode = 0
            return res
        if "sbatch" in cmd:
            res.returncode = 0
            return res
        res.returncode = 1
        return res

    def mock_sleep(seconds):
        scheduler.shutdown_event.set()

    with patch("snap_workflow.utils.exec.has_slurm", return_value=True), \
         patch("subprocess.run", side_effect=mock_run_slurm), \
         patch("time.sleep", side_effect=mock_sleep), \
         patch("threading.Event.wait", side_effect=mock_sleep):
        scheduler.run()
    
    assert status.load_status("stage1/spoints/x_5") == "submitted"

def test_remote_slurm_auto_scheduling_and_monitoring(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    env_file = os.path.join("stage1", "env.json")
    with open(env_file, "r") as f:
        env_data = json.load(f)
    env_data["resources"] = {"cpus": 1, "gpus": 0, "mem": "1G"}
    with open(env_file, "w") as f:
        json.dump(env_data, f)

    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=10)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})

    mock_server = MagicMock()
    from snap_workflow.core.domain import spoints
    mock_server.spoint_manager = spoints.SPointStatusManager()

    scheduler = OrchestratorScheduler(remote="cluster1", stages="stage1", sweeps="sweep1", server=mock_server)

    def mock_run(cmd, *args, **kwargs):
        res = MagicMock()
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
        if "which sbatch" in cmd_str:
            res.returncode = 0
            return res
        if "sbatch" in cmd_str:
            res.returncode = 0
            return res
        if "cat" in cmd_str:
            res.returncode = 0
            res.stdout = "complete\n"
            return res
        if "squeue" in cmd_str:
            res.returncode = 0
            res.stdout = "1001 RUNNING node01\n"
            return res
        res.returncode = 0
        res.stdout = "ok\n"
        return res

    def mock_sleep(seconds):
        scheduler.shutdown_event.set()

    with patch("snap_workflow.utils.io.load_global_remotes", return_value={"cluster1": {"host": "user@cluster1"}}), \
         patch("snap_workflow.utils.io.load_local_remotes", return_value={"cluster1": {"path": "~/sims"}}), \
         patch("snap_workflow.server.tunnels.load_global_remotes", return_value={"cluster1": {"host": "user@cluster1"}}), \
         patch("snap_workflow.server.tunnels.ensure_remote_tunnel"), \
         patch("snap_workflow.remote.setup.resolve_remote_path", return_value="~/sims"), \
         patch("snap_workflow.remote.setup.validate_remote_stage_resources"), \
         patch("snap_workflow.remote.setup.run_remote_bash", side_effect=lambda host, script, **kw: "1001 RUNNING node01\n" if "squeue" in script else ("complete" if "cat" in script else "ok")), \
         patch("subprocess.run", side_effect=mock_run), \
         patch("snap_workflow.remote.ssh.is_remote_ssh_connected", return_value=True), \
         patch("time.sleep", side_effect=mock_sleep), \
         patch("threading.Event.wait", side_effect=mock_sleep):
        
        scheduler.last_squeue_check_time = 0
        scheduler.run()

    assert scheduler.shutdown_event.is_set()

def test_remote_ssh_disconnected_alert(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    env_file = os.path.join("stage1", "env.json")
    with open(env_file, "r") as f:
        env_data = json.load(f)
    env_data["resources"] = {"cpus": 1, "gpus": 0, "mem": "1G"}
    with open(env_file, "w") as f:
        json.dump(env_data, f)

    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=10)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})

    mock_server = MagicMock()
    mock_server.active_tunnels = {}
    from snap_workflow.core.domain import spoints
    mock_server.spoint_manager = spoints.SPointStatusManager()

    scheduler = OrchestratorScheduler(remote="cluster1", stages="stage1", sweeps="sweep1", server=mock_server)

    def mock_run_slurm(cmd, *args, **kwargs):
        res = MagicMock()
        res.returncode = 0
        res.stdout = '{"port": 9999, "token": "abc"}\n'
        return res

    iteration_count = 0
    def mock_wait(seconds=None):
        nonlocal iteration_count
        iteration_count += 1
        if iteration_count >= 2:
            scheduler.shutdown_event.set()

    import snap_workflow.server.scheduler as sched_mod

    with patch("snap_workflow.utils.io.load_global_remotes", return_value={"cluster1": {"host": "user@cluster1"}}), \
         patch("snap_workflow.utils.io.load_local_remotes", return_value={"cluster1": {"path": "~/sims"}}), \
         patch("snap_workflow.server.tunnels.load_global_remotes", return_value={"cluster1": {"host": "user@cluster1"}}), \
         patch("snap_workflow.remote.setup.resolve_remote_path", return_value="~/sims"), \
         patch("snap_workflow.remote.setup.validate_remote_stage_resources"), \
         patch("snap_workflow.remote.setup.run_remote_bash", return_value="ok"), \
         patch("subprocess.run", side_effect=mock_run_slurm), \
         patch.object(sched_mod, "is_remote_ssh_connected", return_value=False) as mock_conn, \
         patch.object(sched_mod, "trigger_alert_sound") as mock_sound, \
         patch("time.sleep"), \
         patch("threading.Event.wait", side_effect=mock_wait):
        
        scheduler.run()
        assert mock_sound.called
