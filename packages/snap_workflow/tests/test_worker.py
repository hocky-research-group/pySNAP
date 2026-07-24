import os
import json
import pytest
import subprocess
from unittest.mock import patch, MagicMock
from snap_workflow.core.workflow import initialize
from snap_workflow.core.stages import add_stage
from snap_workflow.core.variables import add_variable
from snap_workflow.core.sweeps import add_sweep
from snap_workflow.core import status
from snap_workflow.core import worker

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

def test_parse_memory_to_gb():
    assert worker.parse_memory_to_gb("4G") == 4.0
    assert worker.parse_memory_to_gb("4096M") == 4.0
    assert worker.parse_memory_to_gb("4194304K") == 4.0
    assert worker.parse_memory_to_gb("4") == 4.0
    assert worker.parse_memory_to_gb("") == 0.0
    assert worker.parse_memory_to_gb("invalid") == 0.0

def test_detect_system_resources():
    cpus, gpus, mem = worker.detect_system_resources()
    assert isinstance(cpus, int)
    assert isinstance(gpus, int)
    assert isinstance(mem, float)

def test_send_request():
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"status": "ok"}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        resp = worker.send_request("http://localhost:8000", "token")
        assert resp == {"status": "ok"}

def test_worker_loop(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    
    # Mock send_request to return a combo job on the first call,
    # ok on notify_completion, and shutdown on the second request_work call.
    mock_responses = [
        {"status": "combo", "sweep": "sweep1", "stage": "stage1", "combo_dict": {"x": 5}, "combo_path": "stage1/spoints/x_5"},
        {"status": "ok"},
        {"status": "shutdown"}
    ]
    
    call_idx = 0
    def mock_send_request(url, token, data=None):
        nonlocal call_idx
        resp = mock_responses[call_idx]
        call_idx += 1
        return resp
        
    mock_proc = MagicMock()
    mock_proc.poll.return_value = 0 # immediately complete
    
    with patch("snap_workflow.core.worker.send_request", side_effect=mock_send_request), \
         patch("subprocess.Popen", return_value=mock_proc):
        worker.worker_loop(
            server_url="http://localhost:8000",
            token="token",
            cpus_total=4,
            gpus_total=0,
            mem_total=8.0,
            idle_delay=0.1
        )
    assert call_idx >= 2

def test_launch_local_workers(sandbox, env_dir):
    initialize(env_dir)
    # Create a mock SERVER_INFO to bypass the server running check
    from snap_workflow.core.strings import SERVER_INFO
    server_info = {"port": 1234, "token": "dummy_token"}
    with open(SERVER_INFO, "w") as f:
        json.dump(server_info, f)
        
    with patch("subprocess.Popen") as mock_popen:
        worker.launch_local_workers(num_workers=2, stages="stage1", sweeps="sweep1")
        assert mock_popen.call_count == 2
        args = mock_popen.call_args_list[0][0][0]
        assert "snap_workflow.core.worker" in args

# --- Additional Worker Coverage Tests ---

def test_send_request_failures_and_retries():
    import urllib.error
    # 1. Connection fails with retries and eventual success on 3rd attempt, testing POST data parsing
    call_count = 0
    def mock_urlopen(req, data=None, timeout=None):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise urllib.error.URLError("mock connection error")
        mock_response = MagicMock()
        mock_response.__enter__.return_value = mock_response
        mock_response.read.return_value = json.dumps({"status": "ok"}).encode("utf-8")
        return mock_response
        
    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        resp = worker.send_request("http://localhost:8000", "token", data={"hello": "world"}, retries=3, backoff=0.01)
        assert resp == {"status": "ok"}
        assert call_count == 3

    # 2. Connection fails completely after maximum retries
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("permanent error")):
        resp = worker.send_request("http://localhost:8000", "token", retries=2, backoff=0.01)
        assert resp is None

def test_worker_loop_auto_detect_resources_and_env_json(sandbox, env_dir):
    initialize(env_dir)
    # stage1 uses env.json resource limits
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    env_file = os.path.join("stage1", "env.json")
    with open(env_file, "w") as f:
        json.dump({"resources": {"cpus": 2, "gpus": 1, "mem": "4G"}}, f)
        
    # stage2 uses invalid env.json resource limits to trigger parsing exception handling
    add_stage("stage2", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    env_file2 = os.path.join("stage2", "env.json")
    with open(env_file2, "w") as f:
        f.write("invalid json content")
        
    # Mock send_request to notify combo then shutdown
    mock_responses = [
        {"status": "combo", "sweep": "sweep1", "stage": "stage1", "combo_dict": {"x": 5}, "combo_path": "stage1/spoints/x_5"},
        {"status": "combo", "sweep": "sweep1", "stage": "stage2", "combo_dict": {"x": 6}, "combo_path": "stage2/spoints/x_6"},
        {"status": "ok"},
        {"status": "ok"},
        {"status": "shutdown"}
    ]
    
    call_idx = 0
    def mock_send_request(url, token, data=None):
        nonlocal call_idx
        # Check that query string parameters for filters were appended correctly
        if "request_work" in url:
            assert "stages=stage1" in url
            assert "sweeps=sweep1" in url
            assert "exclude_stages=stage2" in url
            assert "exclude_sweeps=sweep2" in url
        resp = mock_responses[call_idx]
        call_idx += 1
        return resp
        
    mock_proc = MagicMock()
    # task runs: first checks return running (None) so they are kept in queue, then finished (0)
    mock_proc.poll.side_effect = [None, None, None, 0, 0, 0]
    
    with patch("snap_workflow.core.worker.send_request", side_effect=mock_send_request), \
         patch("subprocess.Popen", return_value=mock_proc), \
         patch("snap_workflow.core.worker.detect_system_resources", return_value=(3, 0, 8.0)):
        # Pass None to auto-detect resources (will return 3 cpus from mocked detect_system_resources, covering line 42)
        worker.worker_loop(
            server_url="http://localhost:8000",
            token="token",
            cpus_total=None,
            gpus_total=None,
            mem_total=None,
            idle_delay=0.01,
            stages="stage1",
            sweeps="sweep1",
            exclude_stages="stage2",
            exclude_sweeps="sweep2"
        )
    assert call_idx >= 3

def test_worker_loop_zero_resources(sandbox, env_dir):
    initialize(env_dir)
    # Start a loop with 0 cpus capacity, it should sleep on line 155 and exit via KeyboardInterrupt cleanly
    with patch("time.sleep", side_effect=KeyboardInterrupt):
        worker.worker_loop(
            server_url="http://localhost:8000",
            token="token",
            cpus_total=0,
            gpus_total=0,
            mem_total=0,
            idle_delay=0.01
        )

def test_worker_loop_keyboard_interrupt(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    
    mock_responses = [
        {"status": "combo", "sweep": "sweep1", "stage": "stage1", "combo_dict": {"x": 5}, "combo_path": "stage1/spoints/x_5"},
        {"status": "ok"}
    ]
    
    call_idx = 0
    def mock_send_request(url, token, data=None):
        nonlocal call_idx
        resp = mock_responses[call_idx]
        call_idx += 1
        return resp
        
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None # process running
    # Mock terminate to raise an exception to cover try/except block in KeyboardInterrupt
    mock_proc.terminate.side_effect = RuntimeError("mock terminate error")
    
    # We raise KeyboardInterrupt inside loop via time.sleep mock
    with patch("snap_workflow.core.worker.send_request", side_effect=mock_send_request), \
         patch("subprocess.Popen", return_value=mock_proc), \
         patch("time.sleep", side_effect=KeyboardInterrupt):
        worker.worker_loop(
            server_url="http://localhost:8000",
            token="token",
            cpus_total=4,
            gpus_total=0,
            mem_total=8.0,
            idle_delay=0.1
        )
    # Assert terminate was called to terminate active spoint on KeyboardInterrupt
    assert mock_proc.terminate.called

def test_launch_remote_workers_errors_and_profiles(sandbox, env_dir):
    from snap_workflow.core.exceptions import ServerNotRunningError
    initialize(env_dir)
    
    # 1. ServerNotRunningError when SERVER_INFO is missing
    with pytest.raises(ServerNotRunningError):
        worker.launch_remote_workers("Lab_Main", "~/test_snap_setup", "template")
        
    # Create SERVER_INFO
    from snap_workflow.core.strings import SERVER_INFO
    server_info = {"port": 1234, "token": "dummy_token"}
    with open(SERVER_INFO, "w") as f:
        json.dump(server_info, f)
        
    # Test FIXME profile validation failure
    def mock_ssh_run_fixme(cmd, **kwargs):
        mock_res = MagicMock()
        if "python3 -c" in cmd[2]:
            mock_res.stdout = '{"partition": "FIXME"}'
        else:
            mock_res.stdout = "workflow_root\n"
        return mock_res

    with patch("subprocess.run", side_effect=mock_ssh_run_fixme):
        with pytest.raises(ValueError) as exc:
            worker.launch_remote_workers(
                remote_host="Lab_Main",
                remote_path="~/test_snap_setup",
                profile="template"
            )
        assert "FIXME" in str(exc.value)

    # Test valid profile success path
    def mock_ssh_run_valid(cmd, **kwargs):
        mock_res = MagicMock()
        if "python3 -c" in cmd[2]:
            mock_res.stdout = '{"partition": "test"}'
        else:
            mock_res.stdout = "workflow_root\n"
        return mock_res

    with patch("time.sleep", side_effect=KeyboardInterrupt), \
         patch("subprocess.Popen") as mock_popen, \
         patch("subprocess.run", side_effect=mock_ssh_run_valid) as mock_run:
        worker.launch_remote_workers(
            remote_host="Lab_Main",
            remote_path="~/test_snap_setup",
            profile="valid_prof",
            sbatch_args="--partition=test",
            stages="stage1",
            sweeps="sweep1",
            exclude_stages="stage2",
            exclude_sweeps="sweep2",
            remote_name="my_remote_node"
        )
        
        # Verify custom env arguments mapping
        sbatch_call = next(c for c in mock_run.call_args_list if "sbatch" in c[0][0][2])
        cmd_str = sbatch_call[0][0][2]
        assert "WORKER_STAGES=stage1" in cmd_str
        assert "WORKER_SWEEPS=sweep1" in cmd_str
        assert "WORKER_EXCLUDE_STAGES=stage2" in cmd_str
        assert "WORKER_EXCLUDE_SWEEPS=sweep2" in cmd_str
        assert "WORKER_HOST=my_remote_node" in cmd_str
        assert "--partition=test" in cmd_str

def test_parse_memory_tb_units():
    assert worker.parse_memory_to_gb("1T") == 1024.0
    assert worker.parse_memory_to_gb("1TB") == 1024.0

def test_detect_system_resources_gpu_and_fallbacks(monkeypatch):
    import sys
    # 1. Test GPU count successfully parsed from CUDA_VISIBLE_DEVICES
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0,1")
    cpus, gpus, mem = worker.detect_system_resources()
    assert gpus == 2
    
    # 2. Test GPU count from SLURM_GPUS_ON_NODE when CUDA_VISIBLE_DEVICES not set
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    monkeypatch.setenv("SLURM_GPUS_ON_NODE", "3")
    cpus, gpus, mem = worker.detect_system_resources()
    assert gpus == 3
    
    # 3. Test GPU count fallback to 1 when SLURM variable is malformed
    monkeypatch.setenv("SLURM_GPUS_ON_NODE", "invalid_gpu")
    cpus, gpus, mem = worker.detect_system_resources()
    assert gpus == 1

    # 4. Test CUDA_VISIBLE_DEVICES "none" -> gpus = -1
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "none")
    cpus, gpus, mem = worker.detect_system_resources()
    assert gpus == -1
    
    # 5. Test CUDA_VISIBLE_DEVICES empty -> gpus = 0
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", ",")
    cpus, gpus, mem = worker.detect_system_resources()
    assert gpus == 0
    
    # 6. Test CUDA_VISIBLE_DEVICES exception -> gpus = 1
    class BadString:
        def strip(self):
            return self
        def split(self, sep):
            raise ValueError("custom error")
            
    original_getenv = os.getenv
    def mock_getenv(name, default=None):
        if name == "CUDA_VISIBLE_DEVICES":
            return BadString()
        return original_getenv(name, default)
        
    with patch("os.getenv", side_effect=mock_getenv):
        cpus, gpus, mem = worker.detect_system_resources()
        assert gpus == 1
    
    # 7. Test SLURM_CPUS_ON_NODE valid integer (break block)
    monkeypatch.setenv("SLURM_CPUS_ON_NODE", "4")
    cpus, gpus, mem = worker.detect_system_resources()
    assert cpus == 4
    
    # 8. Test SLURM_CPUS_ON_NODE / SLURM_CPUS_PER_TASK parsing errors
    monkeypatch.setenv("SLURM_CPUS_ON_NODE", "malformed")
    cpus, gpus, mem = worker.detect_system_resources()
    assert cpus is not None # falls back to cpu_count
    
    # 9. Test SLURM_MEM_PER_NODE malformed
    monkeypatch.setenv("SLURM_MEM_PER_NODE", "malformed")
    cpus, gpus, mem = worker.detect_system_resources()
    assert mem is not None

    # 10. Test /proc/meminfo exception handling fallback (mock open)
    # We mock builtins.open to raise an error when "/proc/meminfo" is read
    original_open = open
    def mock_open(file, *args, **kwargs):
        if "/proc/meminfo" in str(file):
            raise PermissionError("Access denied")
        return original_open(file, *args, **kwargs)
        
    with patch("builtins.open", side_effect=mock_open):
        cpus, gpus, mem = worker.detect_system_resources()
        assert mem is not None
        
    # 10. Test sysconf page size error handling fallback
    with patch("os.sysconf", side_effect=ValueError("sysconf not supported")):
        # We also need to mock open to raise exception to get to the sysconf block
        with patch("builtins.open", side_effect=lambda f, *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError())):
            cpus, gpus, mem = worker.detect_system_resources()
            assert mem == 4.0 # default memory fallback

    # 11. Test torch.cuda detection and device count logic
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    monkeypatch.delenv("SLURM_GPUS_ON_NODE", raising=False)
    monkeypatch.delenv("SLURM_STEP_GPUS", raising=False)
    mock_torch = MagicMock()
    mock_torch.cuda.is_available.return_value = True
    mock_torch.cuda.device_count.return_value = 5
    with patch.dict(sys.modules, {"torch": mock_torch}):
        cpus, gpus, mem = worker.detect_system_resources()
        assert gpus == 5

def test_launch_local_workers_parameters_and_errors(sandbox, env_dir):
    from snap_workflow.core.exceptions import ServerNotRunningError
    initialize(env_dir)
    
    # 1. ServerNotRunningError when SERVER_INFO is missing
    with pytest.raises(ServerNotRunningError):
        worker.launch_local_workers(num_workers=1)
        
    # Create SERVER_INFO
    from snap_workflow.core.strings import SERVER_INFO
    server_info = {"port": 1234, "token": "dummy_token"}
    with open(SERVER_INFO, "w") as f:
        json.dump(server_info, f)
        
    # 2. Launch with exclude parameters
    with patch("subprocess.Popen") as mock_popen:
        worker.launch_local_workers(
            num_workers=1,
            stages="stage1",
            sweeps="sweep1",
            exclude_stages="stage2",
            exclude_sweeps="sweep2"
        )
        assert mock_popen.call_count == 1
        args = mock_popen.call_args_list[0][0][0]
        assert "snap_workflow.core.worker" in args
        assert "--exclude_stages" in args
        assert "stage2" in args
        assert "--exclude_sweeps" in args
        assert "sweep2" in args

@pytest.mark.filterwarnings("ignore::RuntimeWarning")
def test_worker_cli_argparse_and_shutdown():
    import sys
    import runpy
    
    # 1. Verify help works correctly (SystemExit will be raised by argparse)
    test_args_help = ["snap_workflow.core.worker", "--help"]
    with patch("sys.argv", test_args_help):
        with pytest.raises(SystemExit):
            runpy.run_module("snap_workflow.core.worker", run_name="__main__")
            
    # 2. Execute main block using mock sys.argv and runpy, mocking urlopen to return shutdown instantly
    test_args = [
        "snap_workflow.core.worker",
        "http://localhost:29999",
        "token_val",
        "--stages", "stage1",
        "--sweeps", "sweep1",
        "--exclude_stages", "stage2",
        "--exclude_sweeps", "sweep2",
        "--host", "custom_host"
    ]
    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_response.read.return_value = json.dumps({"status": "shutdown"}).encode("utf-8")
    
    with patch("urllib.request.urlopen", return_value=mock_response), \
         patch("sys.argv", test_args):
         
        runpy.run_module("snap_workflow.core.worker", run_name="__main__")

# --- Live SSH Connection Tests ---
def test_setup_remote_cluster_ssh(sandbox, env_dir):
    initialize(env_dir)
    if not is_ssh_reachable():
        pytest.skip("Lab_Main SSH connection not reachable (VPN may be disconnected)")
        
    # Attempt to setup directory on Lab_Main
    remote_path = "~/test_snap_setup"
    worker.setup_remote_cluster(
        remote_host="Lab_Main",
        remote_path=remote_path
    )
    
    # Confirm directory exists on Lab_Main via a fast SSH command
    res = subprocess.run(
        ["ssh", "Lab_Main", f"test -d {remote_path} && echo yes"],
        capture_output=True,
        text=True
    )
    assert res.stdout.strip() == "yes"

def test_launch_remote_workers_ssh(sandbox, env_dir):
    initialize(env_dir)
    if not is_ssh_reachable():
        pytest.skip("Lab_Main SSH connection not reachable (VPN may be disconnected)")
        
    remote_path = "~/test_snap_setup"
    
    # Create a mock SERVER_INFO
    from snap_workflow.core.strings import SERVER_INFO
    server_info = {"port": 1234, "token": "dummy_token"}
    with open(SERVER_INFO, "w") as f:
        json.dump(server_info, f)
        
    # We patch Popen to mock tunnel, and sleep to raise KeyboardInterrupt to exit loop cleanly.
    # We patch run to capture and verify sbatch submissions.
    def mock_ssh_run_valid(cmd, **kwargs):
        mock_res = MagicMock()
        if len(cmd) > 2 and "python3 -c" in str(cmd[2]):
            mock_res.stdout = '{"partition": "test"}'
        else:
            mock_res.stdout = "workflow_root\n"
        return mock_res

    with patch("time.sleep", side_effect=KeyboardInterrupt), \
         patch("subprocess.Popen") as mock_popen, \
         patch("subprocess.run", side_effect=mock_ssh_run_valid) as mock_run:
         
        worker.launch_remote_workers(
            remote_host="Lab_Main",
            remote_path=remote_path,
            profile="template",
            num_workers=1,
            concurrency=1
        )
        
        # Verify rsync was called to sync codebase
        assert any("rsync" in c[0][0][0] for c in mock_run.call_args_list)
        # Verify tunnel ssh was opened
        assert any("ssh" in c[0][0][0] and "-R" in c[0][0] for c in mock_popen.call_args_list)
        # Verify sbatch submission command was sent via ssh
        assert any("ssh" in c[0][0][0] and "sbatch" in str(c[0][0][2]) for c in mock_run.call_args_list)

def test_resolve_remote_path(sandbox, env_dir):
    initialize(env_dir)
    
    # 1. Directory doesn't exist
    with patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.stdout = "not_exists\n"
        mock_run.return_value = mock_res
        
        path_res = worker.resolve_remote_path("remote_host", "~/my_path")
        assert path_res == "~/my_path"

    # 2. Directory exists and has .workflow
    with patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.stdout = "workflow_root\n"
        mock_run.return_value = mock_res
        
        path_res = worker.resolve_remote_path("remote_host", "~/my_path")
        assert path_res == "~/my_path"

    # 3. Directory exists and is empty
    with patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.stdout = "empty\n"
        mock_run.return_value = mock_res
        
        path_res = worker.resolve_remote_path("remote_host", "~/my_path")
        assert path_res == "~/my_path"

    # 4. Directory is not empty and not workflow root
    with patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.stdout = "not_empty\n"
        mock_run.return_value = mock_res
        
        # Should append the local project directory name
        path_res = worker.resolve_remote_path("remote_host", "~/my_path")
        from snap_workflow.core import path as core_path
        expected = f"~/my_path/{os.path.basename(os.path.abspath(core_path.get_root()))}"
        assert path_res == expected

def test_set_python_config(sandbox, env_dir):
    initialize(env_dir)
    from snap_workflow.core.stages import add_stage, set_python_config
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    
    # 1. Test set_python_config global
    set_python_config(python_path="/usr/bin/custom_python", is_global=True)
    with open(".workflow/config.json") as f:
        cfg = json.load(f)
    assert cfg["default_python_env"] == "/usr/bin/custom_python"
    
    # 2. Test set_python_config stage
    set_python_config(python_path="/usr/bin/stage_python", stage_names=["stage1"])
    with open("stage1/env.json") as f:
        scfg = json.load(f)
    assert scfg["python_path"] == "/usr/bin/stage_python"

def test_cli_set_python(sandbox, env_dir):
    initialize(env_dir)
    from snap_workflow.cli import main_set
    from snap_workflow.core.stages import add_stage
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    
    main_set("workflow set", ["python", "/bin/my_py", "--global"])
    with open(".workflow/config.json") as f:
        cfg = json.load(f)
    assert cfg["default_python_env"] == "/bin/my_py"
    
    main_set("workflow set", ["python", "/bin/stage_py", "-s", "stage1"])
    with open("stage1/env.json") as f:
        scfg = json.load(f)
    assert scfg["python_path"] == "/bin/stage_py"

def test_remote_preflight_checks(sandbox, env_dir):
    initialize(env_dir)
    from snap_workflow.cli import remote_add_cmd
    from snap_workflow.core.worker import setup_remote_cluster
    
    # 1. Test remote_add_cmd connection failure raises ValueError
    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(255, "ssh")):
        with pytest.raises(ValueError) as exc:
            remote_add_cmd("workflow remote add", ["bad_remote", "--host", "unreachable.host.edu"])
        assert "Cannot connect to remote host" in str(exc.value)

    # 2. Test setup_remote_cluster connection failure raises ValueError
    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(255, "ssh")):
        with pytest.raises(ValueError) as exc:
            setup_remote_cluster("unreachable.host.edu", "~/my_path")
        assert "Cannot connect to remote host" in str(exc.value)



