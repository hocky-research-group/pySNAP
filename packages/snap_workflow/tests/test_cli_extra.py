import os
import pytest
from unittest.mock import patch
from snap_workflow.core import initialize, add_stage, add_variable, add_sweep
from snap_workflow.core.sweeps import load_sweeps
from snap_workflow.cli import (
    main_init, main_update, main_zip, main_reset, main_plot, main_autocomplete
)

def test_cli_autocomplete(sandbox):
    # Test valid shell
    with pytest.raises(SystemExit):
        main_autocomplete("workflow autocomplete", ["bash"])
        
    with pytest.raises(SystemExit):
        main_autocomplete("workflow autocomplete", ["zsh"])
        
    # Test invalid shell
    with pytest.raises(ValueError, match="Supported shells"):
        main_autocomplete("workflow autocomplete", ["fish"])

def test_cli_update(sandbox, env_dir):
    initialize(env_dir)
    with pytest.raises(SystemExit):
        main_update("workflow update", [])

def test_cli_zip(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    
    # Test valid zip execution
    with patch('subprocess.run') as mock_sub:
        main_zip("workflow zip", ["test_archive", "-w", "sweep1", "-s", "stage1"])
        assert mock_sub.called
    
    # Test invalid args raise ValueError
    with pytest.raises(ValueError, match="Usage"):
        main_zip("workflow zip", [])
    with pytest.raises(ValueError, match="Usage"):
        main_zip("workflow zip", ["a", "b"])

def test_cli_reset(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    
    # 1. Test reset errors
    with patch('builtins.input', side_effect=["sweep1", "stage1"]):
        main_reset("workflow reset", ["errors"])
        
    # 2. Test reset params
    with patch('builtins.input', side_effect=["sweep1", "stage1"]):
        main_reset("workflow reset", ["params"])
        
    # 3. Test reset sweep
    with patch('builtins.input', side_effect=["sweep1"]):
        main_reset("workflow reset", ["sweep"])

    # 4. Test reset sweep --hard with confirmation 'y'
    with patch('builtins.input', side_effect=["sweep1", "y"]):
        main_reset("workflow reset", ["sweep", "--hard"])

    # 5. Test reset sweep --hard with confirmation 'n'
    with patch('builtins.input', side_effect=["sweep1", "n"]):
        with pytest.raises(SystemExit):
            main_reset("workflow reset", ["sweep", "--hard"])

    # 6. Test reset sweep --hard with --force / -f (should bypass confirmation)
    main_reset("workflow reset", ["sweep", "-w", "sweep1", "--hard", "--force"])
    main_reset("workflow reset", ["sweep", "-w", "sweep1", "--hard", "-f"])

def test_cli_remove_force(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    
    # Add sweep to remove
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    from snap_workflow.cli import main_remove

    # Remove with --force (should bypass confirmation)
    main_remove("workflow remove", ["sweep", "-w", "sweep1", "--force"])
    assert "sweep1" not in load_sweeps()

    # Re-add and remove with -f (should bypass confirmation)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    main_remove("workflow remove", ["sweep", "-w", "sweep1", "-f"])
    assert "sweep1" not in load_sweeps()

def test_cli_plot(sandbox):
    # Plot should just pass and do nothing/not raise exception
    main_plot("workflow plot", [])

@patch('builtins.input')
def test_cli_init_declined(mock_input, sandbox, env_dir):
    mock_input.side_effect = ["n"]
    with pytest.raises(SystemExit):
        main_init("workflow init", [])
