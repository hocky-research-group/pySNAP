import os
import shutil
import pytest
from unittest.mock import patch
from snap_workflow.core.workflow import initialize
from snap_workflow.core.domain.stages import add_stage
from snap_workflow.core.domain.variables import add_variable
from snap_workflow.core.domain.sweeps import (
    add_sweep, remove_sweep, reset_sweep, print_sweeps, rename_and_unlink_spoints
)
from snap_workflow.core.domain import spoints
from snap_workflow.utils.exceptions import SweepAlreadyExistsError, SweepNotFoundError

def test_sweep_errors(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    
    # 1. Add existing sweep throws exception
    with pytest.raises(SweepAlreadyExistsError):
        add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
        
    # 2. Remove nonexistent sweep
    with pytest.raises(SweepNotFoundError):
        remove_sweep("nonexistent_sweep")
        
    # 3. Reset nonexistent sweep
    with pytest.raises(SweepNotFoundError):
        reset_sweep("nonexistent_sweep")
        
    # 4. Reset existing sweep successfully
    reset_sweep("sweep1", hard=True)

def test_hard_remove_sweep(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    
    spoint_path = os.path.join("stage1", "spoints", "x_5")
    assert os.path.isdir(spoint_path)
    
    # Remove hard should clear directory
    remove_sweep("sweep1", hard=True)
    assert not os.path.isdir(spoint_path)

def test_print_sweeps(sandbox, env_dir, capsys):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    
    print_sweeps()
    captured = capsys.readouterr()
    assert "NAME" in captured.out
    assert "STAGES" in captured.out
    assert "VARIABLES & VALUES" in captured.out
    assert "sweep1" in captured.out
    assert "stage1" in captured.out
    assert "x: [5]" in captured.out

def test_rename_and_unlink_spoints(sandbox, env_dir):
    initialize(env_dir)
    # Stage 1 has parent, Stage 2 has dependency on Stage 1
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_stage("stage2", sbatch_details=None, stage_variables=["x", "y"], stage_dependencies=["stage1"])
    add_variable("x", ["int"], add_to_stages=["stage1", "stage2"], default_val=5)
    add_variable("y", ["int"], add_to_stages=["stage2"], default_val=10)
    
    add_sweep("sweep1", include_stages=["stage1", "stage2"], variable_values={"x": [5], "y": [10]})
    
    # Rename old spoints from y_10 -> y_20
    rename_and_unlink_spoints(
        sweep_name="sweep1",
        add_to_stages=["stage2"],
        new_var_name="y",
        new_val=20
    )
    
    # Old path should be moved
    old_path = os.path.join("stage2", "spoints", "x_5_y_10")
    new_path = os.path.join("stage2", "spoints", "x_5_y_20")
    assert not os.path.isdir(old_path)
    assert os.path.isdir(new_path)
    
    # Test error condition when directory is missing
    shutil.rmtree(new_path)
    with pytest.raises(Exception, match="Broke renaming spoint paths"):
        rename_and_unlink_spoints(
            sweep_name="sweep1",
            add_to_stages=["stage2"],
            new_var_name="y",
            new_val=30
        )

def test_sweeps_still_defined(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    add_sweep("sweep2", include_stages=["stage1"], variable_values={"x": [5]})
    
    spoint_path = os.path.join("stage1", "spoints", "x_5")
    assert os.path.isdir(spoint_path)
    
    # Remove sweep1 hard. Since x_5 is still defined in sweep2, it should NOT be deleted!
    remove_sweep("sweep1", hard=True)
    assert os.path.isdir(spoint_path)

def test_initialize_sweep_exception(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    
    with patch("snap_workflow.core.domain.sweeps.params.set_params", side_effect=RuntimeError("mock params exception")), \
         patch("builtins.print") as mock_print:
        add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
        assert mock_print.called

def test_rename_and_unlink_spoints_convergent_and_exists(sandbox, env_dir):
    initialize(env_dir)
    # stage1 (x) is parent, stage2 (y) is child
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_stage("stage2", sbatch_details=None, stage_variables=["y"], stage_dependencies=["stage1"])
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    add_variable("y", ["int"], add_to_stages=["stage2"], default_val=10)
    
    add_sweep("sweep1", include_stages=["stage1", "stage2"], variable_values={"x": [5], "y": [10]})
    
    # Verify the dependent symlink is created
    symlink_path = os.path.join("stage2", "spoints", "y_10", "stage1", "x_5")
    assert os.path.islink(symlink_path)
    
    # Rename old spoints from y_10 -> y_20.
    # Because x is a convergent variable, stage2/spoints/y_20/stage1/x_5 should be unlinked.
    rename_and_unlink_spoints(
        sweep_name="sweep1",
        add_to_stages=["stage2"],
        new_var_name="y",
        new_val=20
    )
    
    new_symlink_path = os.path.join("stage2", "spoints", "y_20", "stage1", "x_5")
    assert not os.path.exists(new_symlink_path)
    
    # 2. Test branch where new_spoint_path already exists (and old path does not exist)
    new_path = os.path.join("stage2", "spoints", "y_20")
    os.makedirs(new_path, exist_ok=True)
    
    # Should continue without moving or raising error
    rename_and_unlink_spoints(
        sweep_name="sweep1",
        add_to_stages=["stage2"],
        new_var_name="y",
        new_val=20
    )

