import os
import json
import shutil
import pytest
import subprocess
from unittest.mock import patch, MagicMock
from snap_workflow.core.workflow import initialize
from snap_workflow.core.stages import add_stage
from snap_workflow.core.variables import add_variable
from snap_workflow.core.sweeps import add_sweep
from snap_workflow.core import spoints
from snap_workflow.core import status
from snap_workflow.core import path
from snap_workflow.core import sync
from snap_workflow.core import server

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
        # Check that both ssh mkdir and rsync push were called
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
        # Check transit pull from cluster1
        pull_args = mock_run.call_args_list[0][0][0]
        assert "tanner@cluster1" in str(pull_args)
        
        # Check transit push to cluster2
        push_args = mock_run.call_args_list[2][0][0] # Index 2 because index 1 is mkdir
        assert "tanner@cluster2" in str(push_args)
        
        # Check cleanup call
        assert mock_rmtree.called

def test_data_locality_scheduling(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_stage("stage2", sbatch_details=None, stage_variables=["x"], stage_dependencies=["stage1"])
    add_variable("x", ["int"], add_to_stages=["stage1", "stage2"], default_val=5)
    add_sweep("sweep1", include_stages=["stage1", "stage2"], variable_values={"x": [5]})
    
    spoint_dict = {"x": 5}
    dep_rel_path = os.path.join("stage1", "spoints", "x_5")
    
    # 1. Mock registry with Parent A (stage1) on workstation1, size 1.5 GB (> 1 GB)
    metadata = {
        dep_rel_path: {"host": "workstation1", "size_bytes": 1_500_000_000}
    }
    server.save_spoint_metadata(metadata)
    
    # Test checking for target host 'workstation1' (parent is local, so runnable)
    runnable, status_str, detail = server.check_data_locality_eligibility("sweep1", "stage2", spoint_dict, "workstation1")
    assert runnable
    assert status_str == "runnable"
    
    # Test checking for target host 'workstation2' (parent is on workstation1 and size > 1 GB, so deferred)
    runnable, status_str, detail = server.check_data_locality_eligibility("sweep1", "stage2", spoint_dict, "workstation2")
    assert not runnable
    assert status_str == "deferred"
    
    # 2. Mock registry with small size (500 MB)
    metadata[dep_rel_path]["size_bytes"] = 500_000_000
    server.save_spoint_metadata(metadata)
    
    # Test checking for workstation2 (parent is on workstation1 but size < 1 GB, so syncable)
    runnable, status_str, detail = server.check_data_locality_eligibility("sweep1", "stage2", spoint_dict, "workstation2")
    assert runnable
    assert status_str == "sync_needed"
    assert detail == [(dep_rel_path, "workstation1", 500_000_000)]

def test_sync_extra_coverage(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=[], stage_dependencies=[])
    
    # 1. get_auto_sync_patterns exception logic
    collect_path = os.path.join("stage1", "collect.py")
    with open(collect_path, "w") as f:
        f.write("raise RuntimeError('isolated load failure')\n")
    patterns = sync.get_auto_sync_patterns("stage1")
    assert patterns == []

    # 2. measure_directory_size local non-existent dir
    assert sync.measure_directory_size("local", None, None, "nonexistent_dir") == 0

    # 3. measure_directory_size local valid dir
    os.makedirs("stage1/spoints/x_5", exist_ok=True)
    with open("stage1/spoints/x_5/file.txt", "w") as f:
        f.write("hello")
    size = sync.measure_directory_size("local", None, None, "stage1/spoints/x_5")
    assert size == 5

    # 4. measure_directory_size remote success
    with patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "1024 /remote/path"
        mock_run.return_value = mock_res
        val = sync.measure_directory_size("remote", "host", "/remote", "stage1/spoints/x_5")
        assert val == 1024

    # 5. measure_directory_size remote failure / exception
    with patch("subprocess.run", side_effect=Exception("ssh connection error")):
        val = sync.measure_directory_size("remote", "host", "/remote", "stage1/spoints/x_5")
        assert val == 0

    # 6. pull_spoint_data local check and no patterns check
    # local remote returns early
    sync.pull_spoint_data("local", "host", "/remote", "stage1/spoints/x_5", "stage1")
    
    # no patterns defined check
    with open(collect_path, "w") as f:
        f.write("AUTO_SYNC = []\n")
    with patch("subprocess.run") as mock_run:
        sync.pull_spoint_data("remote", "host", "/remote", "stage1/spoints/x_5", "stage1")
        assert not mock_run.called

    # 7. pull_spoint_data CalledProcessError handling
    with open(collect_path, "w") as f:
        f.write("AUTO_SYNC = ['*.txt']\n")
    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "rsync")):
        sync.pull_spoint_data("remote", "host", "/remote", "stage1/spoints/x_5", "stage1")

    # 8. push_dependency_data local check
    assert sync.push_dependency_data("local", "host", "/remote", "stage1/spoints/x_5") is None

    # 9. push_dependency_data nonexistent local source dir
    sync.push_dependency_data("remote", "host", "/remote", "nonexistent_local_dir")

    # 10. push_dependency_data remote parent mkdir failure
    with patch("subprocess.run", side_effect=Exception("ssh error")):
        sync.push_dependency_data("remote", "host", "/remote", "stage1/spoints/x_5")

    # 11. push_dependency_data rsync CalledProcessError
    with patch("subprocess.run") as mock_run:
        # First call is ssh mkdir (succeeds), second call is rsync (fails)
        mock_run.side_effect = [MagicMock(returncode=0), subprocess.CalledProcessError(1, "rsync")]
        sync.push_dependency_data("remote", "host", "/remote", "stage1/spoints/x_5")

    # 12. transit_sync_dependency pull CalledProcessError
    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "rsync")):
        sync.transit_sync_dependency("remote", "h1", "/p1", "remote", "h2", "/p2", "stage1/spoints/x_5", "stage1")

    # 13. transit_sync_dependency dest remote mkdir failure
    with patch("subprocess.run") as mock_run:
        # First pull succeeds, mkdir fails
        mock_run.side_effect = [MagicMock(returncode=0), Exception("ssh mkdir error")]
        sync.transit_sync_dependency("remote", "h1", "/p1", "remote", "h2", "/p2", "stage1/spoints/x_5", "stage1")

    # 14. transit_sync_dependency dest push CalledProcessError
    with patch("subprocess.run") as mock_run:
        # First pull succeeds, mkdir succeeds, push fails
        mock_run.side_effect = [MagicMock(returncode=0), MagicMock(returncode=0), subprocess.CalledProcessError(1, "rsync")]
        sync.transit_sync_dependency("remote", "h1", "/p1", "remote", "h2", "/p2", "stage1/spoints/x_5", "stage1")

def test_transit_sync_path_isolation(sandbox, env_dir):
    initialize(env_dir)
    
    # 1. Both remote: uses .workflow/tmp/sync/
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
        assert mock_rmtree.called
        cleanup_path = mock_rmtree.call_args[0][0]
        assert ".workflow/tmp/sync/stage1/spoints/x_5" in cleanup_path.replace("\\", "/")

    # 2. Source is local, dest is remote: uses standard project path
    with patch("subprocess.run") as mock_run, \
         patch("shutil.rmtree") as mock_rmtree:
        sync.transit_sync_dependency(
            source_remote="local",
            source_host=None,
            source_path=None,
            dest_remote="remote",
            dest_host="tanner@cluster2",
            dest_path="/home/cluster2",
            dep_rel_path="stage1/spoints/x_5",
            stage_name="stage1"
        )
        # Should not clean up because source_remote is local
        assert not mock_rmtree.called

