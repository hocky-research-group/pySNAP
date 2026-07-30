import os
import json
import shutil
import pytest
import subprocess
from unittest.mock import patch, MagicMock
from snap_workflow.core.workflow import initialize
from snap_workflow.core.domain.stages import add_stage
from snap_workflow.core.domain.variables import add_variable
from snap_workflow.core.domain.sweeps import add_sweep, load_sweeps
from snap_workflow.utils import path
from snap_workflow.server import sync
from snap_workflow import worker
from snap_workflow.cli import main_remove, main_reset, main_remote

def test_remove_sweep_soft_safety(sandbox, env_dir):
    """Verify that removing a sweep soft-deletes config, but leaves SPoint user files intact."""
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    
    # Create user data files in the spoint directory
    spoint_dir = os.path.join("stage1", "spoints", "x_5")
    os.makedirs(spoint_dir, exist_ok=True)
    user_file = os.path.join(spoint_dir, "my_result.txt")
    with open(user_file, "w") as f:
        f.write("simulation output data")

    # Perform soft removal (no --hard)
    with patch('builtins.input', return_value="y"):
        main_remove("workflow remove", ["sweep", "-w", "sweep1"])

    # Sweep configuration should be gone
    assert "sweep1" not in load_sweeps()
    # User's simulation result file MUST still exist
    assert os.path.isfile(user_file)
    assert os.path.isdir(spoint_dir)

def test_remove_sweep_hard_confirmation_decline(sandbox, env_dir):
    """Verify that removing a sweep hard with confirmation 'n' declines and does not delete anything."""
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    
    spoint_dir = os.path.join("stage1", "spoints", "x_5")
    os.makedirs(spoint_dir, exist_ok=True)
    user_file = os.path.join(spoint_dir, "my_result.txt")
    with open(user_file, "w") as f:
        f.write("simulation output data")

    # Confirm decline: first confirm 'y' (for removal), second confirm 'n' (for hard deletion warning)
    # Or 'n' on the first prompt
    with patch('builtins.input', side_effect=["y", "n"]):
        with pytest.raises(SystemExit):
            main_remove("workflow remove", ["sweep", "-w", "sweep1", "--hard"])

    # No files should be deleted
    assert os.path.isfile(user_file)
    assert "sweep1" in load_sweeps()

def test_reset_sweep_hard_confirmation_decline(sandbox, env_dir):
    """Verify that resetting a sweep hard with confirmation 'n' declines and preserves data."""
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    
    spoint_dir = os.path.join("stage1", "spoints", "x_5")
    os.makedirs(spoint_dir, exist_ok=True)
    user_file = os.path.join(spoint_dir, "my_result.txt")
    with open(user_file, "w") as f:
        f.write("simulation output data")

    # Confirm decline on reset hard
    with patch('builtins.input', side_effect=["n"]):
        with pytest.raises(SystemExit):
            main_reset("workflow reset", ["sweep", "-w", "sweep1", "--hard"])

    # No files should be deleted
    assert os.path.isfile(user_file)

def test_rsync_no_delete_in_sync_commands():
    """Verify that no rsync command executed in sync.py uses the --delete option."""
    # We inspect the code programmatically to ensure --delete is never used in rsync commands.
    sync_code = None
    with open(sync.__file__, "r") as f:
        sync_code = f.read()

    # Verify that rsync commands in sync.py never have "--delete"
    assert "--delete" not in sync_code

    worker_code = None
    with open(worker.__file__, "r") as f:
        worker_code = f.read()

    # Verify that rsync codebase sync commands in worker.py never have "--delete"
    assert "--delete" not in worker_code

def test_transit_sync_leaves_local_workspace_untouched(sandbox, env_dir):
    """Verify that remote-to-remote staging does not touch or clean up active local project files."""
    initialize(env_dir)
    
    # Create active simulation directory locally
    active_dir = os.path.join("stage1", "spoints", "x_5")
    os.makedirs(active_dir, exist_ok=True)
    local_file = os.path.join(active_dir, "local_user_work.txt")
    with open(local_file, "w") as f:
        f.write("local work")

    # Perform transit sync (both remote)
    with patch("subprocess.run") as mock_run:
        sync.transit_sync_dependency(
            source_remote="remote",
            source_host="host1",
            source_path="/remote1",
            dest_remote="remote",
            dest_host="host2",
            dest_path="/remote2",
            dep_rel_path="stage1/spoints/x_5",
            stage_name="stage1"
        )
        
    # Local workspace files MUST NOT be deleted
    assert os.path.isfile(local_file)

def test_cli_outside_workflow_aborts_safely(tmp_path):
    """Verify that running workflow commands outside a workflow directory aborts safely with no deletions or writes."""
    non_workflow_dir = os.path.join(tmp_path, "empty_dir")
    os.makedirs(non_workflow_dir, exist_ok=True)
    
    # Change directory to non-workflow folder
    start_dir = os.getcwd()
    os.chdir(non_workflow_dir)
    try:
        from snap_workflow.cli import reset_sweep_cmd
        with pytest.raises(Exception, match="Not in a workflow system"):
            reset_sweep_cmd("workflow reset sweep", ["sweep1"])
            
        # Ensure no folders/files were created
        assert os.listdir(non_workflow_dir) == []
    finally:
        os.chdir(start_dir)

def test_template_no_overwrite(sandbox, env_dir):
    """Verify that workflow initialization templates cannot be overwritten by re-initialization as it is rejected."""
    initialize(env_dir)
    
    # Modify run_worker.sh with custom user configurations
    worker_sh = os.path.join(".workflow", "workers", "run_worker.sh")
    assert os.path.isfile(worker_sh)
    with open(worker_sh, "w") as f:
        f.write("# CUSTOM USER CONFIGURATION")

    # Run initialize again should be rejected with ValueError
    with pytest.raises(ValueError, match="already within workflow setup"):
        initialize(env_dir)
    
    # Verify that the custom configuration remains intact
    with open(worker_sh, "r") as f:
        content = f.read()
    assert content == "# CUSTOM USER CONFIGURATION"

def test_clear_directory_boundary_protection(sandbox, env_dir):
    """Verify that resetting or clearing SPoints never deletes files outside the targeted SPoint directory."""
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    
    # Create the target SPoint directory and a file inside it
    spoint_dir = os.path.join("stage1", "spoints", "x_5")
    os.makedirs(spoint_dir, exist_ok=True)
    spoint_file = os.path.join(spoint_dir, "output.txt")
    with open(spoint_file, "w") as f:
        f.write("simulation data")
        
    # Create a random file outside the SPoint folder boundary (at the parent spoints/ folder)
    outside_file = os.path.join("stage1", "spoints", "important_report.txt")
    with open(outside_file, "w") as f:
        f.write("user report")
        
    # Run a hard sweep reset with --force
    main_reset("workflow reset", ["sweep", "-w", "sweep1", "--hard", "--force"])
    
    # File inside SPoint is cleared/deleted as expected
    assert not os.path.isfile(spoint_file)
    # The file OUTSIDE the SPoint folder boundary MUST still exist intact
    assert os.path.isfile(outside_file)
    with open(outside_file, "r") as f:
        assert f.read() == "user report"

