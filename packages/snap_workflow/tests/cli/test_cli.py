import os
import pytest
from unittest.mock import patch

from snap_workflow.cli.workflow import main_init
from snap_workflow.cli.verbs import main_add, main_print, main_set, main_remove, main_reset
from snap_workflow.core import load_stages
from snap_workflow.core.domain.sweeps import load_sweeps

@patch('builtins.input')
def test_cli_lifecycle(mock_input, sandbox, env_dir):
    # 1. Test CLI initialization
    # Prompts: 
    # - Confirm initialization: 'y'
    # - Env path: env_dir
    mock_input.side_effect = ["y", "json", env_dir]
    try:
        main_init("workflow init", [])
    except SystemExit:
        pass # Expect SystemExit on successful CLI termination
        
    assert os.path.isdir(".workflow")
    
    # 2. Test CLI add stage
    # Subcommand: workflow add stage -n stageA
    # Prompts:
    # - Sbatch submission (y/n)? -> 'n'
    # - Stage dependencies -> '' (none)
    mock_input.side_effect = ["n", ""]
    main_add("workflow add", ["stage", "-n", "stageA"])
    
    stages = load_stages()
    assert "stageA" in stages
    
    # 3. Test CLI add variable
    # Subcommand: workflow add variable -n x -t int
    # Prompts:
    # - Include in stageA (y/n)? -> 'y'
    mock_input.side_effect = ["y"]
    main_add("workflow add", ["variable", "-n", "x", "-t", "int"])
    
    # 4. Test CLI add sweep
    # Subcommand: workflow add sweep -n sweepA
    # Prompts:
    # - Include stageA in sweep (y/n)? -> 'y'
    # - Values for variable x -> '10 20'
    mock_input.side_effect = ["y", "10 20"]
    main_add("workflow add", ["sweep", "-n", "sweepA"])
    
    sweeps = load_sweeps()
    assert "sweepA" in sweeps
    assert sweeps["sweepA"]["values"]["x"] == ["10", "20"]
    
    # 5. Test CLI print sweeps
    # Subcommand: workflow print sweeps
    with patch('sys.stdout') as mock_stdout:
        main_print("workflow print", ["sweeps"])
        
    # 6. Test CLI set status
    # Subcommand: workflow set status submitted -w sweepA -s stageA
    main_set("workflow set", ["status", "submitted", "-w", "sweepA", "-s", "stageA"])
    
    # 7. Test CLI remove sweep
    # Subcommand: workflow remove sweep -w sweepA
    # Prompts:
    # - Confirm removal (y/n)? -> 'y'
    mock_input.side_effect = ["y"]
    main_remove("workflow remove", ["sweep", "-w", "sweepA"])
    
    sweeps = load_sweeps()
    assert "sweepA" not in sweeps

@patch('builtins.input')
def test_cli_noun_verb_lifecycle(mock_input, sandbox, env_dir):
    from snap_workflow.cli.stage import main_stage
    from snap_workflow.cli.sweep import main_sweep
    from snap_workflow.cli.workflow import main_variable
    from snap_workflow.cli.spoint import main_status
    mock_input.side_effect = ["y", "json", env_dir]
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

