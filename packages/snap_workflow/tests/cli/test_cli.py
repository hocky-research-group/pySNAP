import os
import pytest
from unittest.mock import patch

from snap_workflow.core import initialize, load_stages, add_stage, add_variable, add_sweep
from snap_workflow.core.domain.sweeps import load_sweeps
from snap_workflow.cli.workflow import main_init, main_zip, main_autocomplete, main_variable
from snap_workflow.cli.stage import main_stage
from snap_workflow.cli.sweep import main_sweep
from snap_workflow.cli.status import main_status
from snap_workflow.cli.spoint import main_spoint
from snap_workflow.cli.python import main_python
from snap_workflow.cli.utils import get_completions


@patch('builtins.input')
def test_cli_lifecycle(mock_input, sandbox, env_dir):
    # 1. Test CLI initialization
    mock_input.side_effect = ["y", "json"]
    try:
        main_init("workflow init", [])
    except SystemExit:
        pass # Expect SystemExit on successful CLI termination
        
    assert os.path.isdir(".workflow")
    
    # 2. Test CLI add stage
    mock_input.side_effect = ["n", ""]
    main_stage("workflow stage", ["add", "-n", "stageA"])
    
    stages = load_stages()
    assert "stageA" in stages
    
    # 3. Test CLI add variable
    mock_input.side_effect = ["y"]
    main_variable("workflow variable", ["add", "-n", "x", "-t", "int"])
    
    # 4. Test CLI add sweep
    mock_input.side_effect = ["y", "10 20"]
    main_sweep("workflow sweep", ["add", "-n", "sweepA"])
    
    sweeps = load_sweeps()
    assert "sweepA" in sweeps
    assert sweeps["sweepA"]["values"]["x"] == [10, 20]
    
    # 5. Test CLI print sweeps
    with patch('sys.stdout'):
        main_sweep("workflow sweep", ["print"])
        
    # 6. Test CLI set status
    main_status("workflow status", ["set", "submitted", "-w", "sweepA", "-s", "stageA"])
    
    # 7. Test CLI remove sweep
    mock_input.side_effect = ["y"]
    main_sweep("workflow sweep", ["remove", "-w", "sweepA"])
    
    sweeps = load_sweeps()
    assert "sweepA" not in sweeps


@patch('builtins.input')
def test_cli_noun_verb_lifecycle(mock_input, sandbox, env_dir):
    mock_input.side_effect = ["y", "json"]
    try:
        main_init("workflow init", [])
    except SystemExit:
        pass

    # Noun-first stage add: workflow stage add -n stageA
    mock_input.side_effect = ["n", ""]
    main_stage("workflow stage", ["add", "-n", "stageA"])
    assert "stageA" in load_stages()

    # Noun-first variable add: workflow variable add -n x -t int
    mock_input.side_effect = ["y"]
    main_variable("workflow variable", ["add", "-n", "x", "-t", "int"])

    # Noun-first sweep add: workflow sweep add -n sweepA
    mock_input.side_effect = ["y", "10 20"]
    main_sweep("workflow sweep", ["add", "-n", "sweepA"])
    sweeps = load_sweeps()
    assert "sweepA" in sweeps

    # Noun-first status print: workflow status print
    main_status("workflow status", ["print", "sweepA"])

    # Noun-first sweep remove: workflow sweep remove -w sweepA
    mock_input.side_effect = ["y"]
    main_sweep("workflow sweep", ["remove", "-w", "sweepA"])
    assert "sweepA" not in load_sweeps()


def test_cli_autocomplete(sandbox):
    with pytest.raises(SystemExit):
        main_autocomplete("workflow autocomplete", ["bash"])
        
    with pytest.raises(SystemExit):
        main_autocomplete("workflow autocomplete", ["zsh"])
        
    with pytest.raises(ValueError, match="Supported shells"):
        main_autocomplete("workflow autocomplete", ["fish"])


def test_cli_zip(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    
    with patch('subprocess.run') as mock_sub:
        main_zip("workflow zip", ["test_archive", "-w", "sweep1", "-s", "stage1"])
        assert mock_sub.called
    
    with pytest.raises(ValueError, match="Usage"):
        main_zip("workflow zip", [])
    with pytest.raises(ValueError, match="Usage"):
        main_zip("workflow zip", ["a", "b"])


def test_cli_reset(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    
    with patch('builtins.input', side_effect=["sweep1", "stage1"]):
        main_status("workflow status", ["reset", "errors"])
        
    with patch('builtins.input', side_effect=["sweep1"]):
        main_spoint("workflow spoint", ["reset"])

    with patch('builtins.input', side_effect=["sweep1", "y"]):
        main_spoint("workflow spoint", ["reset", "--hard"])

    with patch('builtins.input', side_effect=["sweep1", "n"]):
        with pytest.raises(SystemExit):
            main_spoint("workflow spoint", ["reset", "--hard"])

    main_spoint("workflow spoint", ["reset", "-w", "sweep1", "--hard", "--force"])
    main_spoint("workflow spoint", ["reset", "-w", "sweep1", "--hard", "-f"])

    main_spoint("workflow spoint", ["reset", "sweep1"])
    main_spoint("workflow spoint", ["reset", "sweep1", "--hard", "--force"])


def test_cli_python(sandbox, env_dir, capsys):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=[], stage_dependencies=[])

    main_python("workflow python", [])
    captured = capsys.readouterr()
    assert "Global Fallback" in captured.out
    assert "Project Default" in captured.out

    main_python("workflow python", ["set"])
    main_python("workflow python", ["set", "-s", "stage1"])


def test_cli_remove_force(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})

    main_sweep("workflow sweep", ["remove", "-w", "sweep1", "--force"])
    assert "sweep1" not in load_sweeps()

    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    main_sweep("workflow sweep", ["remove", "-w", "sweep1", "-f"])
    assert "sweep1" not in load_sweeps()


def test_get_completions_noun_verb():
    assert "stage" in get_completions([], "")
    assert "sweep" in get_completions([], "")
    assert "variable" in get_completions([], "")
    assert "status" in get_completions([], "")
    assert "spoint" in get_completions([], "")
    assert "python" in get_completions([], "")
    assert "build" not in get_completions([], "")
    assert "update" not in get_completions([], "")

    assert get_completions(["stage"], "") == ["add", "print"]
    assert get_completions(["sweep"], "") == ["add", "print", "remove"]
    assert get_completions(["variable"], "") == ["add", "print"]
    assert get_completions(["status"], "") == ["print", "set", "reset"]
    assert get_completions(["spoint"], "") == ["reset", "submit"]
    assert get_completions(["python"], "") == ["print", "set"]


def test_cli_status_and_spoint(sandbox, env_dir, capsys):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})

    # Bare 'workflow status' defaults to print
    main_status("workflow status", [])
    captured = capsys.readouterr()
    assert "Sweep: " in captured.out or "sweep1" in captured.out

    # 'workflow status print'
    main_status("workflow status", ["print"])
    captured = capsys.readouterr()
    assert "Sweep: " in captured.out or "sweep1" in captured.out

    # 'workflow status set'
    main_status("workflow status", ["set", "complete"])
    main_status("workflow status", ["print"])
    captured = capsys.readouterr()
    assert "complete" in captured.out

    # 'workflow status reset errors'
    main_status("workflow status", ["set", "error"])
    main_status("workflow status", ["reset", "errors"])
    main_status("workflow status", ["print"])
    captured = capsys.readouterr()
    assert "initialized" in captured.out

    # 'workflow status reset' with --from error
    main_status("workflow status", ["set", "error"])
    main_status("workflow status", ["reset", "--from", "error"])
    main_status("workflow status", ["print"])
    captured = capsys.readouterr()
    assert "initialized" in captured.out

    # 'workflow status set <from_status> <to_status>' (2 positional args)
    main_status("workflow status", ["set", "initialized", "running"])
    main_status("workflow status", ["print"])
    captured = capsys.readouterr()
    assert "running" in captured.out

    main_status("workflow status", ["set", "running", "complete"])
    main_status("workflow status", ["print"])
    captured = capsys.readouterr()
    assert "complete" in captured.out


def test_cli_variable_print(sandbox, env_dir, capsys):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    add_variable("y", ["float"], add_to_stages=["stage1"], default_val=1.5)

    main_variable("workflow variable", ["print"])
    captured = capsys.readouterr()
    assert "NAME" in captured.out
    assert "TYPE" in captured.out
    assert "STAGES" in captured.out
    assert "x" in captured.out
    assert "int" in captured.out
    assert "stage1" in captured.out
    assert "y" in captured.out


@patch('builtins.input')
def test_cli_init_declined(mock_input, sandbox, env_dir):
    mock_input.side_effect = ["n"]
    with pytest.raises(SystemExit):
        main_init("workflow init", [])
