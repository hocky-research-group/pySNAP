import os
import pytest
from unittest.mock import patch

from snap_workflow.core.workflow import initialize
from snap_workflow.core.domain.stages import add_stage
from snap_workflow.core.domain.sweeps import add_sweep
from snap_workflow.cli.utils import parse_remaining, execute_option, get_csv_arg, get_data_format, get_script_path, get_completions, get_shell_completion_script
from snap_workflow.cli import prompts


def test_parse_remaining():
    args = ["stage1", "-w", "sweep1", "-s", "stage1", "stage2", "--force"]
    positionals, kwargs = parse_remaining(args)
    assert positionals == ["stage1"]
    assert kwargs["w"] == "sweep1"
    assert kwargs["s"] == ["stage1", "stage2"]
    assert kwargs["force"] is True


def test_get_csv_arg():
    assert get_csv_arg({"stages": ["a", "b"]}, ["s", "stages"]) == "a,b"
    assert get_csv_arg({"s": "single"}, ["s", "stages"]) == "single"
    assert get_csv_arg({}, ["s", "stages"]) == ""


def test_execute_option(sandbox):
    called = {}

    def opt_a(parsed_cmd, args):
        called["a"] = True

    options = {"action_a": opt_a}

    # Direct match in args
    execute_option("test_key", options, "workflow test", ["action_a"])
    assert called.get("a") is True

    # Via kwargs / input collector
    called.clear()
    with patch("builtins.input", return_value="action_a"):
        execute_option("test_key", options, "workflow test", [])
        assert called.get("a") is True


def test_get_data_format():
    assert get_data_format({"format": "json"}) == "json"
    with patch("builtins.input", return_value="yaml"):
        assert get_data_format({}) == "yaml"


def test_get_script_path(tmp_path):
    f = tmp_path / "run.py"
    f.write_text("print(1)")

    assert get_script_path({"f": str(f)}) == str(f)


def test_get_completions_advanced(sandbox):
    initialize(sandbox)
    add_stage("stage1", sbatch_details=None, stage_variables=[], stage_dependencies=[])
    add_sweep("sweep1", include_stages=["stage1"], variable_values={})

    # Flag completions
    flags = get_completions(prefix="--dr")
    assert flags == ["--dry-run"]

    # Stage completions
    st_comp = get_completions(args=["workflow", "-s"], prefix="st")
    assert st_comp == ["stage1"]

    # Sweep completions
    sw_comp = get_completions(args=["workflow", "-w"], prefix="sw")
    assert sw_comp == ["sweep1"]

    # Remote subcommand completions
    rem_comp = get_completions(args=["remote"], prefix="s")
    assert sorted(rem_comp) == ["setup", "sync"]

    # Shell scripts
    assert get_shell_completion_script("zsh") == "#compdef workflow\n"
    assert get_shell_completion_script("bash") == "_workflow_completion"
    assert get_completions("zsh") == "#compdef workflow\n"


def test_prompts_prompt_each_stage(sandbox):
    initialize(sandbox)
    assert prompts.prompt_each_stage("Check stages:") == []

    add_stage("stage1", sbatch_details=None, stage_variables=[], stage_dependencies=[])
    add_stage("stage2", sbatch_details=None, stage_variables=[], stage_dependencies=[])

    with patch("builtins.input", side_effect=["y", "n"]):
        selected = prompts.prompt_each_stage("Check stages:")
        assert selected == ["stage1"]


def test_prompts_get_new_stage_name(sandbox):
    initialize(sandbox)
    assert prompts.get_new_stage_name({"n": "stage1"}) == "stage1"

    with patch("builtins.input", return_value="stage2"):
        assert prompts.get_new_stage_name({}) == "stage2"


def test_prompts_get_existing_stage_name(sandbox):
    initialize(sandbox)
    add_stage("stage1", sbatch_details=None, stage_variables=[], stage_dependencies=[])

    assert prompts.get_existing_stage_name({"s": "stage1"}) == "stage1"

    with patch("builtins.input", return_value="stage1"):
        assert prompts.get_existing_stage_name({}, default="stage1") == "stage1"
