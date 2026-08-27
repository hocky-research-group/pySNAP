import os
import json
import pytest
from unittest.mock import patch, MagicMock
from snap_workflow import server
from snap_workflow.core.workflow import initialize
from snap_workflow.utils.constants import SERVER_INFO


@pytest.fixture
def wf_init(sandbox):
    initialize(force=True)


def test_reserve_workers_without_server_info_file(wf_init):
    if os.path.isfile(SERVER_INFO):
        os.remove(SERVER_INFO)
    with patch("snap_workflow.utils.exec.has_slurm", return_value=True):
        with pytest.raises(ValueError, match="Manager server is not running locally"):
            server.reserve_workers("local", "default")


def test_reserve_workers_non_slurm_error(wf_init):
    info_data = {"port": 8080, "token": "test_token_123"}
    with open(SERVER_INFO, "w") as f:
        json.dump(info_data, f)

    with patch("snap_workflow.utils.exec.has_slurm", return_value=False):
        with pytest.raises(ValueError, match="does not have Slurm \\('sbatch'\\)"):
            server.reserve_workers("local", "cpu")


def test_reserve_workers_local_success(wf_init):
    info_data = {"port": 8080, "token": "test_token_123"}
    with open(SERVER_INFO, "w") as f:
        json.dump(info_data, f)

    mock_res = {"status": "ok", "message": "Worker submitted successfully"}
    with patch("snap_workflow.utils.exec.has_slurm", return_value=True), \
         patch("snap_workflow.server.api.send_request", return_value=mock_res) as mock_send:
        res = server.reserve_workers(remote="local", profile="my_profile", num_workers=2, sbatch_args="--qos=high")
        assert res == mock_res
        mock_send.assert_called_once_with(
            "http://127.0.0.1:8080/reserve",
            "test_token_123",
            data={
                "name": "local",
                "profile": "my_profile",
                "num_workers": 2,
                "sbatch_args": "--qos=high",
                "stages": "",
                "sweeps": "",
                "exclude_stages": "",
                "exclude_sweeps": ""
            }
        )


def test_auto_local_success(wf_init):
    info_data = {"url": "http://127.0.0.1:9090", "token": "test_token_auto"}
    with open(SERVER_INFO, "w") as f:
        json.dump(info_data, f)

    mock_res = {"status": "ok", "message": "Auto-scheduler initiated"}
    with patch("snap_workflow.server.api.send_request", return_value=mock_res) as mock_send:
        res = server.auto("local", stages="stage1,stage2")
        assert res == mock_res
        mock_send.assert_called_once_with(
            "http://127.0.0.1:9090/auto",
            "test_token_auto",
            data={
                "remote": "local",
                "stages": "stage1,stage2",
                "sweeps": "",
                "exclude_stages": "",
                "exclude_sweeps": ""
            }
        )


def test_reserve_workers_unregistered_remote_fails(wf_init):
    info_data = {"port": 8080, "token": "test_token"}
    with open(SERVER_INFO, "w") as f:
        json.dump(info_data, f)

    with patch("snap_workflow.utils.exec.has_slurm", return_value=True), \
         patch("snap_workflow.utils.io.load_global_remotes", return_value={}), \
         patch("snap_workflow.utils.io.load_local_remotes", return_value={}):
        with pytest.raises(ValueError, match="Remote 'unknown_remote' is not registered"):
            server.reserve_workers("unknown_remote", "profile1")

        with pytest.raises(ValueError, match="Remote 'unknown_remote' is not registered"):
            server.auto("unknown_remote")


def test_reserve_remote_registered_success(wf_init):
    info_data = {"port": 8080, "token": "test_token"}
    with open(SERVER_INFO, "w") as f:
        json.dump(info_data, f)

    remotes = {"my_cluster": {"host": "cluster.edu"}}
    mock_res = {"status": "ok"}

    with patch("snap_workflow.utils.exec.has_slurm", return_value=True), \
         patch("snap_workflow.utils.io.load_global_remotes", return_value=remotes), \
         patch("snap_workflow.utils.io.load_local_remotes", return_value={}), \
         patch("snap_workflow.remote.setup.validate_remote_stage_resources") as mock_val, \
         patch("snap_workflow.server.api.ensure_remote_tunnel") as mock_tunnel, \
         patch("snap_workflow.server.api.send_request", return_value=mock_res):
        
        res1 = server.reserve_workers("my_cluster", profile="lonestar", stages="st1", sweeps="gamma_sweep")
        assert res1 == mock_res
        mock_val.assert_called_with("cluster.edu", stages="st1", sweeps="gamma_sweep")
        mock_tunnel.assert_called_with("my_cluster")

        res2 = server.auto("my_cluster", stages="st1", sweeps="gamma_sweep")
        assert res2 == mock_res
