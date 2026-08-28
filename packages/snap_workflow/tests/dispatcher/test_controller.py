import os
import pytest
from unittest.mock import patch, MagicMock
from snap_workflow.dispatcher.controller import DispatcherController


def test_dispatcher_controller_properties():
    c_local = DispatcherController(target_name="local", mode="subprocess")
    assert c_local.is_remote is False
    assert c_local.ssh_active is True
    assert c_local.is_active is False

    c_remote = DispatcherController(target_name="lonestar", mode="slurm")
    assert c_remote.is_remote is True
    assert c_remote.ssh_active is False


def test_dispatcher_controller_start_local():
    controller = DispatcherController(
        target_name="local",
        mode="subprocess",
        server_url="http://127.0.0.1:8080",
        token="test_token",
        num_workers=2,
        stages="stage1",
        sweeps="sweep1"
    )

    mock_proc = MagicMock()
    mock_proc.pid = 9991
    mock_proc.poll.return_value = None

    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        controller.start()
        assert mock_popen.call_count == 2
        assert controller.is_active is True
        assert len(controller.procs) == 2

        first_cmd = mock_popen.call_args_list[0][0][0]
        assert "snap_workflow.dispatcher.runner" in first_cmd
        assert "--stages" in first_cmd

        status = controller.get_status()
        assert status["target"] == "local"
        assert status["is_active"] is True
        assert status["pids"] == [9991, 9991]

        controller.stop()
        assert mock_proc.terminate.called
        assert len(controller.procs) == 0


def test_dispatcher_controller_start_remote_slurm():
    mock_server = MagicMock()
    mock_server.server_port = 9001
    mock_tunnel_proc = MagicMock()
    mock_tunnel_proc.poll.return_value = None
    mock_server.active_tunnels = {"lonestar": mock_tunnel_proc}
    mock_server.tunnels = {"lonestar": mock_tunnel_proc}

    controller = DispatcherController(
        target_name="lonestar",
        mode="slurm",
        token="token123",
        server_instance=mock_server
    )

    mock_proc = MagicMock()
    mock_proc.pid = 7771
    mock_proc.poll.return_value = None

    with patch("snap_workflow.server.tunnels.ensure_remote_tunnel") as mock_tunnel, \
         patch("snap_workflow.dispatcher.controller.get_remote_host", return_value="lonestar"), \
         patch("snap_workflow.dispatcher.controller.get_remote_path", return_value="~/my_project"), \
         patch("subprocess.Popen", return_value=mock_proc) as mock_popen:

        controller.start()
        assert mock_tunnel.called
        assert mock_popen.called
        cmd_args = mock_popen.call_args[0][0]
        assert "snap_workflow.dispatcher.slurm" in cmd_args
        assert "--remote-host" in cmd_args
        assert "lonestar" in cmd_args
        assert controller.is_remote is True
        assert controller.ssh_active is True

        controller.stop()
        assert mock_proc.terminate.called


def test_dispatcher_controller_start_remote_subprocess():
    mock_server = MagicMock()
    mock_server.server_port = 9001
    mock_tunnel_proc = MagicMock()
    mock_tunnel_proc.poll.return_value = None
    mock_server.active_tunnels = {"workstation": mock_tunnel_proc}
    mock_server.tunnels = {"workstation": mock_tunnel_proc}

    controller = DispatcherController(
        target_name="workstation",
        mode="subprocess",
        token="token123",
        server_instance=mock_server
    )

    mock_ssh_proc = MagicMock()
    mock_ssh_proc.pid = 8881
    mock_ssh_proc.poll.return_value = None

    with patch("snap_workflow.server.tunnels.ensure_remote_tunnel") as mock_tunnel, \
         patch("snap_workflow.dispatcher.controller.get_remote_host", return_value="workstation"), \
         patch("snap_workflow.dispatcher.controller.get_remote_path", return_value="~/my_project"), \
         patch("subprocess.Popen", return_value=mock_ssh_proc) as mock_popen:

        controller.start()
        assert mock_tunnel.called
        assert mock_popen.called
        ssh_args = mock_popen.call_args[0][0]
        assert ssh_args[0] == "ssh"
        assert "workstation" in ssh_args
        assert "snap_workflow.dispatcher.runner" in ssh_args[-1]
        assert controller.is_remote is True
        assert controller.ssh_active is True

        controller.stop()
        assert mock_ssh_proc.terminate.called
