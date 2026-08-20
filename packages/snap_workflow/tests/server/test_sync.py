import os
import json
import shutil
import pytest
import subprocess
from unittest.mock import patch, MagicMock
from snap_workflow.core.workflow import initialize
from snap_workflow.core.domain.stages import add_stage
from snap_workflow.core.domain.variables import add_variable
from snap_workflow.core.domain.sweeps import add_sweep
from snap_workflow.core.domain import spoints
from snap_workflow.core.domain import status
from snap_workflow.utils import path
from snap_workflow.server import sync
from snap_workflow import server

def test_get_auto_sync_patterns(sandbox, env_dir):
    initialize(env_dir)
    # Write a collect.py with AUTO_SYNC
    add_stage("stage1", sbatch_details=None, stage_variables=[], stage_dependencies=[])
    
    collect_path = os.path.join("stage1", "collect.py")
    with open(collect_path, "w") as f:
        f.write("AUTO_SYNC = ['*.json', 'plots/*']\n")
        f.write("def collect():\n    return {}\n")
        
    patterns = sync.get_auto_sync_patterns("stage1")
    assert patterns == ["*.json", "plots/*"]

def test_pull_spoint_data(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=[], stage_dependencies=[])
    
    collect_path = os.path.join("stage1", "collect.py")
    with open(collect_path, "w") as f:
        f.write("AUTO_SYNC = ['*.json']\n")
        
    with patch("subprocess.run") as mock_run:
        sync.pull_spoint_data("remote", "tanner@cluster", "/home/remote", "stage1/spoints/x_5", "stage1")
        assert mock_run.called
        args = mock_run.call_args[0][0]
        assert "rsync" in args
        assert "--include=*.json" in args
        assert "--exclude=*" in args

def test_push_dependency_data(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=[], stage_dependencies=[])
    
    # Create the local folder to push
    os.makedirs(os.path.join("stage1", "spoints", "x_5"), exist_ok=True)
    
    with patch("subprocess.run") as mock_run:
        sync.push_push = sync.push_dependency_data("remote", "tanner@cluster", "/home/remote", "stage1/spoints/x_5")
        assert mock_run.called
        assert mock_run.call_count >= 1

def test_transit_sync_dependency(sandbox, env_dir):
    initialize(env_dir)
    
    with patch("subprocess.run") as mock_run, \
         patch("shutil.rmtree") as mock_rmtree:
        sync.transit_sync_dependency(
            source_remote="remote",
            source_host="tanner@cluster1",
            source_path="/home/cluster1",
            dest_remote="remote",
            dest_host="tanner@cluster2",
            dest_path="/home/cluster2",
            dep_rel_path="stage1/spoints/x_5",
            stage_name="stage1"
        )
        assert mock_run.call_count >= 2
        pull_args = mock_run.call_args_list[0][0][0]
        assert "tanner@cluster1" in str(pull_args)
        
        push_args = mock_run.call_args_list[2][0][0]
        assert "tanner@cluster2" in str(push_args)
        
        assert mock_rmtree.called

def test_sync_extra_coverage(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=[], stage_dependencies=[])
    
    collect_path = os.path.join("stage1", "collect.py")
    with open(collect_path, "w") as f:
        f.write("raise RuntimeError('isolated load failure')\n")
    patterns = sync.get_auto_sync_patterns("stage1")
    assert patterns == []

    assert sync.measure_directory_size("local", None, None, "nonexistent_dir") == 0

    os.makedirs("stage1/spoints/x_5", exist_ok=True)
    with open("stage1/spoints/x_5/file.txt", "w") as f:
        f.write("hello")
    size = sync.measure_directory_size("local", None, None, "stage1/spoints/x_5")
    assert size == 5

    with patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "1024 /remote/path"
        mock_run.return_value = mock_res
        val = sync.measure_directory_size("remote", "host", "/remote", "stage1/spoints/x_5")
        assert val == 1024

    with patch("subprocess.run", side_effect=Exception("ssh connection error")):
        val = sync.measure_directory_size("remote", "host", "/remote", "stage1/spoints/x_5")
        assert val == 0

    sync.pull_spoint_data("local", "host", "/remote", "stage1/spoints/x_5", "stage1")
    
    with open(collect_path, "w") as f:
        f.write("AUTO_SYNC = []\n")
    with patch("subprocess.run") as mock_run:
        sync.pull_spoint_data("remote", "host", "/remote", "stage1/spoints/x_5", "stage1")
        assert not mock_run.called

    with open(collect_path, "w") as f:
        f.write("AUTO_SYNC = ['*.txt']\n")
    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "rsync")):
        sync.pull_spoint_data("remote", "host", "/remote", "stage1/spoints/x_5", "stage1")

    assert sync.push_dependency_data("local", "host", "/remote", "stage1/spoints/x_5") is None

    sync.push_dependency_data("remote", "host", "/remote", "nonexistent_local_dir")

    with patch("subprocess.run", side_effect=Exception("ssh error")):
        sync.push_dependency_data("remote", "host", "/remote", "stage1/spoints/x_5")

    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [MagicMock(returncode=0), subprocess.CalledProcessError(1, "rsync")]
        sync.push_dependency_data("remote", "host", "/remote", "stage1/spoints/x_5")

    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "rsync")):
        sync.transit_sync_dependency("remote", "h1", "/p1", "remote", "h2", "/p2", "stage1/spoints/x_5", "stage1")

    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [MagicMock(returncode=0), Exception("ssh mkdir error")]
        sync.transit_sync_dependency("remote", "h1", "/p1", "remote", "h2", "/p2", "stage1/spoints/x_5", "stage1")

    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [MagicMock(returncode=0), MagicMock(returncode=0), subprocess.CalledProcessError(1, "rsync")]
        sync.transit_sync_dependency("remote", "h1", "/p1", "remote", "h2", "/p2", "stage1/spoints/x_5", "stage1")

def test_pull_worker_logs(sandbox, env_dir):
    initialize(env_dir)
    assert sync.pull_worker_logs("local", "host", "/remote") is None

    with patch("subprocess.run") as mock_run:
        sync.pull_worker_logs("remote", "user@cluster", "/remote/path")
        assert mock_run.called
        assert "rsync" in mock_run.call_args[0][0]

    with patch("subprocess.run", side_effect=Exception("rsync error")):
        sync.pull_worker_logs("remote", "user@cluster", "/remote/path")

def test_push_workflow_structure(sandbox, env_dir):
    initialize(env_dir)
    assert sync.push_workflow_structure("local") is None
    assert sync.push_workflow_structure("unregistered_remote", None) is None

    with patch("snap_workflow.remote.ssh.ensure_remote_ssh_master"), \
         patch("snap_workflow.remote.ssh.get_control_path_args", return_value=[]), \
         patch("subprocess.run") as mock_run:
        sync.push_workflow_structure("user@cluster", "/remote/path")
        assert mock_run.called

    with patch("snap_workflow.remote.ssh.ensure_remote_ssh_master"), \
         patch("snap_workflow.remote.ssh.get_control_path_args", return_value=[]), \
         patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "rsync")):
        sync.push_workflow_structure("user@cluster", "/remote/path")
