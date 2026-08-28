import pytest
import os
import json
import subprocess
from unittest.mock import patch, MagicMock
from snap_workflow.remote import exec as exec_module
from snap_workflow.utils import constants


def test_get_remote_host_and_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert exec_module.get_remote_host("local") == "local"
    assert exec_module.get_remote_path("local") == "."
    
    # Unregistered remote raises ValueError
    monkeypatch.setattr("snap_workflow.utils.io.load_global_remotes", lambda: {})
    with pytest.raises(ValueError, match="is not registered globally"):
        exec_module.get_remote_host("nonexistent")
        
    monkeypatch.setattr("snap_workflow.utils.io.load_global_remotes", lambda: {"cluster1": {"host": "myhost"}})
    assert exec_module.get_remote_host("cluster1") == "myhost"
    
    # Unset local remote raises ValueError
    monkeypatch.setattr("snap_workflow.utils.io.load_local_remotes", lambda: {})
    with pytest.raises(ValueError, match="has not been set up locally"):
        exec_module.get_remote_path("cluster1")
        
    monkeypatch.setattr("snap_workflow.utils.io.load_local_remotes", lambda: {"cluster1": {"path": "/scratch/sims"}})
    assert exec_module.get_remote_path("cluster1") == "/scratch/sims"


def test_run_command_local_and_remote():
    # Local command execution
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(args=["ls"], returncode=0, stdout="out")
        res = exec_module.run_command("local", ["ls", "-la"])
        assert res.returncode == 0
        mock_run.assert_called_with(["ls", "-la"])
        
        # Local string command
        exec_module.run_command("local", "echo hello")
        mock_run.assert_called_with("echo hello", shell=True)

    # Remote command execution
    with patch("snap_workflow.remote.exec.get_remote_host", return_value="user@hpc.edu"), \
         patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="remote_out")
        res = exec_module.run_command("cluster1", ["ls", "-la"])
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "ssh"
        assert "user@hpc.edu" in call_args
        assert "ls -la" in call_args


def test_has_slurm():
    # Local check with sbatch present
    with patch("shutil.which", return_value="/usr/bin/sbatch"):
        assert exec_module.has_slurm("local") is True
        
    # Local check without sbatch
    with patch("shutil.which", return_value=None):
        assert exec_module.has_slurm("local") is False
        
    # Remote check with sbatch present
    with patch("snap_workflow.remote.exec.run_command", return_value=subprocess.CompletedProcess(args=[], returncode=0)):
        assert exec_module.has_slurm("cluster1") is True
        
    # Remote check without sbatch
    with patch("snap_workflow.remote.exec.run_command", return_value=subprocess.CompletedProcess(args=[], returncode=1)):
        assert exec_module.has_slurm("cluster1") is False

    # Remote check raising exception
    with patch("snap_workflow.remote.exec.run_command", side_effect=RuntimeError("SSH fail")):
        assert exec_module.has_slurm("cluster1") is False


def test_detect_target_resources():
    # Local detection
    with patch("snap_workflow.dispatcher.detect_system_resources", return_value=(16, 2, 64.0)):
        assert exec_module.detect_target_resources("local") == (16, 2, 64.0)
        
    # Remote detection success
    mock_res = subprocess.CompletedProcess(args=[], returncode=0, stdout="[32, 4, 128.5]\n")
    with patch("snap_workflow.remote.exec.run_command", return_value=mock_res):
        assert exec_module.detect_target_resources("cluster1") == (32, 4, 128.5)
        
    # Remote detection failure raises RuntimeError
    with patch("snap_workflow.remote.exec.run_command", side_effect=Exception("Timeout")), \
         patch("snap_workflow.remote.ssh.run_remote_bash", side_effect=Exception("SSH down")):
        with pytest.raises(RuntimeError, match="Failed to query hardware resources on remote"):
            exec_module.detect_target_resources("cluster1")
