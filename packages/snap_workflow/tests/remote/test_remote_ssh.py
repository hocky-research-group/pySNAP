import os
import pytest
from unittest.mock import patch, MagicMock
from snap_workflow.remote import ssh

def test_get_control_path_args():
    args = ssh.get_control_path_args()
    assert "-o" in args
    assert any("ControlPath=" in arg for arg in args)

def test_run_remote_python():
    with patch("snap_workflow.remote.ssh.ensure_remote_ssh_master"), \
         patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "hello\n"
        mock_run.return_value = mock_res
        
        out = ssh.run_remote_python("remote_host", "print('hello')", python_cmd="python3.11")
        assert out == "hello\n"

    with patch("snap_workflow.remote.ssh.ensure_remote_ssh_master"), \
         patch("subprocess.run") as mock_run:
        mock_fail = MagicMock()
        mock_fail.returncode = 1
        mock_fail.stdout = ""
        mock_fail.stderr = "command not found"
        
        mock_succ = MagicMock()
        mock_succ.returncode = 0
        mock_succ.stdout = "fallback_ok\n"
        
        mock_run.side_effect = [mock_fail, mock_succ]
        out_fallback = ssh.run_remote_python("remote_host", "print('fallback')")
        assert out_fallback == "fallback_ok\n"

    with patch("snap_workflow.remote.ssh.ensure_remote_ssh_master"), \
         patch("subprocess.run") as mock_run:
        mock_fail = MagicMock()
        mock_fail.returncode = 1
        mock_fail.stdout = ""
        mock_fail.stderr = "SyntaxError"
        mock_run.return_value = mock_fail
        
        with pytest.raises(RuntimeError) as exc:
            ssh.run_remote_python("remote_host", "bad_code", python_cmd="python3")
        assert "SyntaxError" in str(exc.value)

def test_run_remote_bash():
    with patch("snap_workflow.remote.ssh.ensure_remote_ssh_master"), \
         patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "bash_ok\n"
        mock_run.return_value = mock_res
        
        out = ssh.run_remote_bash("remote_host", "echo bash_ok")
        assert out == "bash_ok\n"

    with patch("snap_workflow.remote.ssh.ensure_remote_ssh_master"), \
         patch("subprocess.run") as mock_run:
        mock_fail = MagicMock()
        mock_fail.returncode = 1
        mock_fail.stdout = None
        mock_fail.stderr = "bash error"
        mock_run.return_value = mock_fail
        
        with pytest.raises(RuntimeError) as exc:
            ssh.run_remote_bash("remote_host", "bad_script")
        assert "bash error" in str(exc.value)

def test_ensure_remote_ssh_master():
    ssh.ensure_remote_ssh_master("local")
    ssh.ensure_remote_ssh_master(None)

    with patch("snap_workflow.utils.io.load_global_remotes", return_value={"c1": {"host": "user@c1"}}), \
         patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_run.return_value = mock_res
        ssh.ensure_remote_ssh_master("c1")
        assert mock_run.called

    ssh_dir = os.path.expanduser("~/.config/snap_workflow/ssh")
    os.makedirs(ssh_dir, exist_ok=True)
    fake_sock = os.path.join(ssh_dir, "mux_fake_test_sock")
    with open(fake_sock, "w") as f:
        f.write("sock")
    try:
        with patch("snap_workflow.utils.io.load_global_remotes", return_value={"c1": {"host": "user@c1"}}), \
             patch("subprocess.run") as mock_run:
            mock_fail = MagicMock()
            mock_fail.returncode = 1
            mock_run.return_value = mock_fail
            ssh.ensure_remote_ssh_master("c1")
            assert mock_run.called
    finally:
        if os.path.exists(fake_sock):
            os.remove(fake_sock)

def test_is_remote_ssh_connected():
    assert ssh.is_remote_ssh_connected("local") is True
    assert ssh.is_remote_ssh_connected(None) is True

    with patch("snap_workflow.utils.io.load_global_remotes", return_value={"c1": {"host": "user@c1"}}), \
         patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_run.return_value = mock_res
        assert ssh.is_remote_ssh_connected("c1") is True

    with patch("subprocess.run", side_effect=Exception("ssh error")):
        assert ssh.is_remote_ssh_connected("c1") is False

def test_trigger_alert_sound():
    with patch("subprocess.run") as mock_run, \
         patch("shutil.which", return_value="/usr/bin/paplay"):
        ssh.trigger_alert_sound()
        assert mock_run.called
