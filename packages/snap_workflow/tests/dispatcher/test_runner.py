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
