import os
import json
import pytest
from unittest.mock import patch, MagicMock

from snap_workflow.core.workflow import initialize
from snap_workflow.dispatcher.runner import detect_system_resources, dispatcher_loop, notify_dispatcher_shutdown, main
from snap_workflow.utils.constants import SERVER_INFO


def test_detect_system_resources():
    with patch("os.cpu_count", return_value=8), \
         patch.dict(os.environ, {"CUDA_VISIBLE_DEVICES": "0,1"}, clear=True):
        cpus, gpus, mem = detect_system_resources()
        assert cpus == 8
        assert gpus == 2
        assert mem > 0


def test_detect_system_resources_slurm_env():
    with patch.dict(os.environ, {"SLURM_CPUS_ON_NODE": "16", "SLURM_GPUS_ON_NODE": "4"}, clear=True):
        cpus, gpus, mem = detect_system_resources()
        assert cpus == 16
        assert gpus == 4


def test_dispatcher_loop_loads_server_info_automatically(sandbox):
    initialize(force=True)
    server_info = {
        "host": "127.0.0.1",
        "port": 9123,
        "token": "tok_auto_test",
        "url": "http://127.0.0.1:9123"
    }
    with open(SERVER_INFO, "w") as f:
        json.dump(server_info, f)

    # Dispatcher immediately receives shutdown
    calls = []
    def mock_send(*args, **kwargs):
        if args and isinstance(args[0], str):
            calls.append(args[0])
        elif len(args) > 1 and isinstance(args[1], str):
            calls.append(args[1])
        return {"status": "shutdown"}

    with patch("snap_workflow.dispatcher.base.BaseDispatcher.send_request", side_effect=mock_send):
        dispatcher_loop()
        assert any("request_work" in c for c in calls)
        assert any("http://127.0.0.1:9123" in c for c in calls)


def test_dispatcher_loop_reconnect_backoff(sandbox):
    initialize(force=True)
    server_info = {
        "host": "127.0.0.1",
        "port": 9123,
        "token": "tok_backoff",
        "url": "http://127.0.0.1:9123"
    }
    with open(SERVER_INFO, "w") as f:
        json.dump(server_info, f)

    call_count = 0
    def mock_send(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return None  # First call simulated tunnel drop
        return {"status": "shutdown"}  # Reconnected on second call

    with patch("snap_workflow.dispatcher.base.BaseDispatcher.send_request", side_effect=mock_send), \
         patch("time.sleep"):
        dispatcher_loop(idle_delay=0.01)
        assert call_count >= 2


def test_main_cli_execution():
    with patch("snap_workflow.dispatcher.runner.dispatcher_loop") as mock_loop, \
         patch("snap_workflow.dispatcher.runner.notify_dispatcher_shutdown") as mock_notify, \
         patch("sys.argv", ["runner.py", "http://localhost:8080", "secret_tok", "--cpus", "4"]):
        main()
        assert mock_loop.called
        assert mock_notify.called


def test_subprocess_dispatcher_cleanup_and_reap(sandbox):
    from snap_workflow.dispatcher.runner import SubprocessDispatcher
    from snap_workflow.core.domain import status as status_module
    initialize(force=True)

    dispatcher = SubprocessDispatcher(
        server_url="http://127.0.0.1:8080",
        token="tok123",
        cpus_total=4,
        host="Lonestar"
    )

    mock_proc = MagicMock()
    mock_proc.poll.return_value = 0
    mock_proc.wait.return_value = 0

    sp_dir = os.path.join(os.getcwd(), "stage1", "spoints", "x_10")
    os.makedirs(os.path.join(sp_dir, ".spoint_info"), exist_ok=True)
    status_module.write_status("incomplete", sp_dir)

    dispatcher.active_jobs[sp_dir] = {
        "proc": mock_proc,
        "sweep": "sw1",
        "stage": "stage1",
        "spoint_dict": {"x": 10},
        "spoint_path": sp_dir,
        "assigned_cpus": [0],
        "assigned_gpus": []
    }

    reported = []
    def mock_send_req(url, data=None, **kwargs):
        reported.append((url, data))
        return {"status": "ok"}

    with patch.object(dispatcher, "send_request", side_effect=mock_send_req):
        dispatcher.cleanup()
        assert mock_proc.send_signal.called
        assert mock_proc.wait.called
        assert len(reported) == 1
        assert reported[0][1]["status"] == "incomplete"
        assert len(dispatcher.active_jobs) == 0


def test_subprocess_dispatcher_assigned_spoints_completion(sandbox):
    from snap_workflow.dispatcher.runner import SubprocessDispatcher
    from snap_workflow.core.domain import status as status_module
    initialize(force=True)

    sp_dir = os.path.join(os.getcwd(), "stage1", "spoints", "x_10")
    os.makedirs(os.path.join(sp_dir, ".spoint_info"), exist_ok=True)
    status_module.write_status("complete", sp_dir)

    dispatcher = SubprocessDispatcher(
        server_url="http://127.0.0.1:8080",
        token="tok123",
        cpus_total=4,
        host="Lonestar",
        assigned_spoints=[sp_dir]
    )

    assert len(dispatcher.assigned_spoints) == 1
    assert len(dispatcher.pending_assigned) == 1

    mock_proc = MagicMock()
    mock_proc.poll.return_value = 0

    dispatcher.active_jobs[sp_dir] = {
        "proc": mock_proc,
        "sweep": "sw1",
        "stage": "stage1",
        "spoint_dict": {"x": 10},
        "spoint_path": sp_dir,
        "assigned_cpus": [0],
        "assigned_gpus": []
    }

    with patch.object(dispatcher, "send_request", return_value={"status": "ok"}):
        dispatcher.reap_finished()
        assert len(dispatcher.active_jobs) == 0
        assert sp_dir in dispatcher.completed_assigned
        assert dispatcher.shutdown_requested is True


def test_subprocess_dispatcher_standalone_mode(sandbox):
    from snap_workflow.dispatcher.runner import SubprocessDispatcher
    from snap_workflow.core.domain import status as status_module
    initialize(force=True)

    sp_dir1 = os.path.join(os.getcwd(), "stage1", "spoints", "x_10")
    sp_dir2 = os.path.join(os.getcwd(), "stage1", "spoints", "x_20")
    os.makedirs(os.path.join(sp_dir1, ".spoint_info"), exist_ok=True)
    os.makedirs(os.path.join(sp_dir2, ".spoint_info"), exist_ok=True)
    status_module.write_status("initialized", sp_dir1)
    status_module.write_status("initialized", sp_dir2)

    dispatcher = SubprocessDispatcher(
        server_url=None,
        token=None,
        cpus_total=4,
        host="slurm_node",
        assigned_spoints=[sp_dir1, sp_dir2]
    )

    assert dispatcher.server_url is None
    assert len(dispatcher.assigned_spoints) == 2

    # Request first task in standalone mode
    task1 = dispatcher.request_work()
    assert task1 is not None
    assert task1["status"] == "spoint"
    assert task1["stage"] == "stage1"
    assert task1["spoint_dict"] in ({"x": "10"}, {"x": "20"})

    # Mock subprocess run for dispatch
    mock_proc1 = MagicMock()
    mock_proc1.pid = 12345
    mock_proc1.poll.return_value = None

    with patch("subprocess.Popen", return_value=mock_proc1):
        dispatcher.dispatch_task(task1)
        assert task1["spoint_path"] in dispatcher.active_jobs

    # Request second task
    task2 = dispatcher.request_work()
    assert task2 is not None
    assert task2["spoint_dict"] in ({"x": "10"}, {"x": "20"})
    assert task2["spoint_dict"] != task1["spoint_dict"]

    mock_proc2 = MagicMock()
    mock_proc2.pid = 12346
    mock_proc2.poll.return_value = None

    with patch("subprocess.Popen", return_value=mock_proc2):
        dispatcher.dispatch_task(task2)
        assert task2["spoint_path"] in dispatcher.active_jobs

    # No more pending assigned tasks
    task3 = dispatcher.request_work()
    assert task3 is None

    # Simulate completion of both jobs
    mock_proc1.poll.return_value = 0
    mock_proc2.poll.return_value = 0
    status_module.write_status("complete", sp_dir1)
    status_module.write_status("complete", sp_dir2)

    dispatcher.reap_finished()
    assert len(dispatcher.active_jobs) == 0
    assert len(dispatcher.completed_assigned) == 2
    assert dispatcher.shutdown_requested is True
