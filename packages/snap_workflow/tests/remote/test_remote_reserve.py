import os
import json
import pytest
from unittest.mock import patch, MagicMock
from snap_workflow.remote.reserve import reserve_remote_workers


def test_reserve_remote_workers_success():
    global_remotes = {"my_cluster": {"host": "user@cluster.edu"}}
    local_remotes = {"my_cluster": {"path": "~/sims"}}

    mock_run_res = MagicMock()
    mock_run_res.returncode = 0

    with patch("snap_workflow.remote.reserve.load_global_remotes", return_value=global_remotes), \
         patch("snap_workflow.remote.reserve.load_local_remotes", return_value=local_remotes), \
         patch("snap_workflow.remote.reserve.resolve_remote_path", return_value="/home/user/sims"), \
         patch("snap_workflow.remote.reserve.validate_remote_workspace_python_environments"), \
         patch("snap_workflow.remote.reserve.validate_remote_stage_resources"), \
         patch("snap_workflow.remote.reserve.run_remote_python", return_value=json.dumps({"partition": "gpu"})), \
         patch("snap_workflow.remote.reserve.run_remote_bash", return_value="login01.cluster.edu\n"), \
         patch("snap_workflow.remote.reserve.subprocess.run", return_value=mock_run_res) as mock_sub:

        reserve_remote_workers(
            server_port=8080,
            token="secret_token",
            remote_name="my_cluster",
            profile="gpu",
            num_workers=2,
            sbatch_args="--qos=high",
            stages="stage1",
            sweeps="sweep1"
        )

        assert mock_sub.called
        # Verify the sbatch command sent over SSH
        sbatch_calls = [c[0][0] for c in mock_sub.call_args_list if c[0][0][0] == "ssh" and any("sbatch" in str(arg) for arg in c[0][0])]
        assert len(sbatch_calls) == 2
        ssh_cmd = sbatch_calls[0][-1]
        assert "sbatch" in ssh_cmd
        assert "SERVER_PORT=8080" in ssh_cmd
        assert "SERVER_TOKEN=secret_token" in ssh_cmd
        assert "TUNNEL_HOST=login01.cluster.edu" in ssh_cmd
        assert "--qos=high" in ssh_cmd
