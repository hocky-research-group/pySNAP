import os
import json
import pytest
from unittest.mock import patch, MagicMock

from snap_workflow.cli.server import (
    main_server,
    server_start_cmd,
    server_auto_cmd,
    server_reserve_cmd,
)
from snap_workflow.cli.utils import get_completions
from snap_workflow.core import initialize


def test_main_server_options_dispatch():
    with patch("snap_workflow.cli.server.server_start_cmd") as mock_start, \
         patch("snap_workflow.cli.server.server_auto_cmd") as mock_auto, \
         patch("snap_workflow.cli.server.server_reserve_cmd") as mock_reserve:

        main_server("workflow server", ["start", "--port", "9000"])
        assert mock_start.called

        main_server("workflow server", ["auto", "my_remote"])
        assert mock_auto.called

        main_server("workflow server", ["autoschedule", "my_remote"])
        assert mock_auto.call_count == 2

        main_server("workflow server", ["reserve", "my_cluster", "gpu"])
        assert mock_reserve.called


def test_server_start_cmd():
    with patch("snap_workflow.server.run_server_foreground") as mock_run:
        server_start_cmd("workflow server start", ["--port", "9090", "--host", "127.0.0.1"])
        mock_run.assert_called_once_with(host="127.0.0.1", port=9090)


def test_server_auto_cmd_delegation():
    with patch("snap_workflow.server.auto", return_value={"status": "success", "message": "Autoscheduler started"}) as mock_auto:
        server_auto_cmd("workflow server auto", ["my_workstation", "--stage", "stage1", "--sweep", "sweep1"])
        mock_auto.assert_called_once_with(
            remote="my_workstation",
            stages="stage1",
            sweeps="sweep1",
            exclude_stages="",
            exclude_sweeps=""
        )


def test_server_reserve_cmd_missing_args():
    with pytest.raises(ValueError, match="Usage: 'workflow server reserve <remote> <profile>"):
        server_reserve_cmd("workflow server reserve", ["cluster_only"])


def test_server_reserve_cmd_delegation():
    with patch("snap_workflow.server.reserve_workers", return_value={"status": "success", "message": "Reservation submitted"}) as mock_reserve:
        server_reserve_cmd(
            "workflow server reserve",
            ["cluster1", "gpu", "--num-workers", "4", "--sbatch-args", "qos=high", "--stage", "stage2"]
        )
        mock_reserve.assert_called_once_with(
            remote="cluster1",
            profile="gpu",
            num_workers=4,
            sbatch_args="qos=high",
            stages="stage2",
            sweeps="",
            exclude_stages="",
            exclude_sweeps=""
        )


def test_server_autocompletions(sandbox):
    initialize(force=True)

    # Top-level server options
    comp = get_completions(["server"], prefix="")
    assert "start" in comp
    assert "auto" in comp
    assert "autoschedule" in comp
    assert "reserve" in comp

    # server auto <remote>
    with patch("snap_workflow.utils.io.load_local_remotes", return_value={"cluster1": {}, "ws1": {}}), \
         patch("snap_workflow.utils.io.load_global_remotes", return_value={}):
        comp_remotes = get_completions(["server", "auto"], prefix="")
        assert "local" in comp_remotes
        assert "cluster1" in comp_remotes
        assert "ws1" in comp_remotes

        # server reserve <remote> <profile>
        os.makedirs("sbatch_profiles", exist_ok=True)
        with open("sbatch_profiles/gpu_large.json", "w") as f:
            f.write("{}")
        with open("sbatch_profiles/cpu_small.yaml", "w") as f:
            f.write("{}")

        comp_profiles = get_completions(["server", "reserve", "cluster1"], prefix="")
        assert "gpu_large" in comp_profiles
        assert "cpu_small" in comp_profiles
