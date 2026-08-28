import os
import json
import pytest
from unittest.mock import patch, MagicMock

from snap_workflow.server.tunnels import (
    get_ssh_control_dir,
    stop_remote_tunnels,
    ensure_remote_tunnel,
    provision_remote_server_info,
    cleanup_remote_server_info,
    _ACTIVE_TUNNELS
)


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

    with patch("snap_workflow.server.tunnels.cleanup_remote_server_info") as mock_clean:
        stop_remote_tunnels(server)

        assert mock_proc1.terminate.called
        assert mock_proc1.wait.called
        assert not mock_proc2.terminate.called
        assert len(server.active_tunnels) == 0
        assert mock_clean.call_count == 2


def test_stop_remote_tunnels_timeout_kill():
    import subprocess
    server = MagicMock()
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.wait.side_effect = subprocess.TimeoutExpired(cmd="ssh", timeout=2)

    server.active_tunnels = {"remote1": mock_proc}

    with patch("snap_workflow.server.tunnels.cleanup_remote_server_info"):
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
         patch("snap_workflow.server.tunnels.provision_remote_server_info") as mock_prov, \
         patch("snap_workflow.server.tunnels.time.sleep"):
        res = ensure_remote_tunnel(server, "my_remote")
        assert res == mock_new_proc
        assert server.active_tunnels["my_remote"] == mock_new_proc
        assert mock_prov.called


def test_ensure_remote_tunnel_single_arg_without_server():
    mock_new_proc = MagicMock()
    mock_new_proc.poll.return_value = None

    with patch("snap_workflow.utils.io.load_global_remotes", return_value={"my_remote": {"host": "example.com"}}), \
         patch("snap_workflow.utils.io.load_local_remotes", return_value={}), \
         patch("snap_workflow.server.tunnels.subprocess.Popen", return_value=mock_new_proc), \
         patch("snap_workflow.server.tunnels.provision_remote_server_info") as mock_prov, \
         patch("snap_workflow.server.tunnels.time.sleep"):
        res = ensure_remote_tunnel("my_remote")
        assert res == mock_new_proc
        assert mock_prov.called


def test_provision_and_cleanup_remote_server_info():
    global_remotes = {"cluster1": {"host": "user@cluster.edu"}}
    local_remotes = {"cluster1": {"path": "/home/user/sims"}}

    with patch("snap_workflow.utils.io.load_global_remotes", return_value=global_remotes), \
         patch("snap_workflow.utils.io.load_local_remotes", return_value=local_remotes), \
         patch("snap_workflow.remote.ssh.run_remote_bash", return_value="login01.cluster.edu\n") as mock_bash:

        server_mock = MagicMock()
        server_mock.server_port = 8888
        server_mock.token = "secret123"

        provision_remote_server_info("cluster1", server_obj=server_mock)

        assert mock_bash.called
        # Check that bash script wrote server json
        calls = [c[0][1] for c in mock_bash.call_args_list]
        write_call = [cmd for cmd in calls if "cat << 'EOF' > /home/user/sims/.workflow/server" in cmd]
        assert len(write_call) > 0
        assert "login01.cluster.edu" in write_call[0]
        assert "8888" in write_call[0]
        assert "secret123" in write_call[0]

        mock_bash.reset_mock()
        cleanup_remote_server_info("cluster1")
        clean_calls = [c[0][1] for c in mock_bash.call_args_list]
        assert any("rm -f /home/user/sims/.workflow/server" in cmd for cmd in clean_calls)
