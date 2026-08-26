import os
import pytest
from unittest.mock import patch, MagicMock

from snap_workflow.server.tunnels import get_ssh_control_dir, stop_remote_tunnels, ensure_remote_tunnel, _ACTIVE_TUNNELS


@pytest.fixture(autouse=True)
def clear_tunnels():
    _ACTIVE_TUNNELS.clear()
    yield
    _ACTIVE_TUNNELS.clear()


def test_get_ssh_control_dir():
    ssh_dir = get_ssh_control_dir()
    assert os.path.isabs(ssh_dir)
    assert os.path.exists(ssh_dir)
    assert ssh_dir.endswith(os.path.join(".config", "snap_workflow", "ssh"))


def test_stop_remote_tunnels():
    server = MagicMock()
    mock_proc1 = MagicMock()
    mock_proc1.poll.return_value = None  # running
    
    mock_proc2 = MagicMock()
    mock_proc2.poll.return_value = 0  # exited

    server.active_tunnels = {
        "remote1": mock_proc1,
        "remote2": mock_proc2
    }

    stop_remote_tunnels(server)

    assert mock_proc1.terminate.called
    assert mock_proc1.wait.called
    assert not mock_proc2.terminate.called
    assert len(server.active_tunnels) == 0


def test_stop_remote_tunnels_timeout_kill():
    import subprocess
    server = MagicMock()
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.wait.side_effect = subprocess.TimeoutExpired(cmd="ssh", timeout=2)

    server.active_tunnels = {"remote1": mock_proc}

    stop_remote_tunnels(server)

    assert mock_proc.terminate.called
    assert mock_proc.kill.called
    assert len(server.active_tunnels) == 0


def test_ensure_remote_tunnel_unregistered_remote():
    server = MagicMock()
    with patch("snap_workflow.utils.io.load_global_remotes", return_value={}), \
         patch("snap_workflow.utils.io.load_local_remotes", return_value={}):
        with pytest.raises(ValueError, match="is not registered"):
            ensure_remote_tunnel(server, "unknown_remote")


def test_ensure_remote_tunnel_terminated_process_restart():
    server = MagicMock()
    old_proc = MagicMock()
    old_proc.poll.return_value = 1  # terminated
    old_proc.pid = 1234
    server.active_tunnels = {"my_remote": old_proc}

    mock_new_proc = MagicMock()
    mock_new_proc.poll.return_value = None

    with patch("snap_workflow.utils.io.load_global_remotes", return_value={"my_remote": {"host": "example.com"}}), \
         patch("snap_workflow.utils.io.load_local_remotes", return_value={}), \
         patch("snap_workflow.server.tunnels.subprocess.Popen", return_value=mock_new_proc), \
         patch("snap_workflow.server.tunnels.time.sleep"):
        res = ensure_remote_tunnel(server, "my_remote")
        assert res == mock_new_proc
        assert server.active_tunnels["my_remote"] == mock_new_proc


def test_ensure_remote_tunnel_single_arg_without_server():
    mock_new_proc = MagicMock()
    mock_new_proc.poll.return_value = None

    with patch("snap_workflow.utils.io.load_global_remotes", return_value={"my_remote": {"host": "example.com"}}), \
         patch("snap_workflow.utils.io.load_local_remotes", return_value={}), \
         patch("snap_workflow.server.tunnels.subprocess.Popen", return_value=mock_new_proc), \
         patch("snap_workflow.server.tunnels.time.sleep"):
        res = ensure_remote_tunnel("my_remote")
        assert res == mock_new_proc
