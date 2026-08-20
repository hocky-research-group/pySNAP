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


def test_submit_worker_without_server_info_file(wf_init):
    if os.path.isfile(SERVER_INFO):
        os.remove(SERVER_INFO)
    with pytest.raises(ValueError, match="Manager server is not running locally"):
        server.submit_worker("local", "default")


def test_submit_worker_local_success(wf_init):
    info_data = {"port": 8080, "token": "test_token_123"}
    with open(SERVER_INFO, "w") as f:
        json.dump(info_data, f)

    mock_res = {"status": "ok", "message": "Worker submitted successfully"}
    with patch("snap_workflow.worker.send_request", return_value=mock_res) as mock_send:
        res = server.submit_worker(remote="local", profile="my_profile", num_workers=2, sbatch_args="--qos=high")
        assert res == mock_res
        mock_send.assert_called_once_with(
            "http://127.0.0.1:8080/submit_worker",
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


def test_submit_auto_local_success(wf_init):
    info_data = {"url": "http://127.0.0.1:9090", "token": "test_token_auto"}
    with open(SERVER_INFO, "w") as f:
        json.dump(info_data, f)

    mock_res = {"status": "ok", "message": "Auto-scheduler initiated"}
    with patch("snap_workflow.worker.send_request", return_value=mock_res) as mock_send:
        res = server.submit_auto("local", stages="stage1,stage2")
        assert res == mock_res
        mock_send.assert_called_once_with(
            "http://127.0.0.1:9090/submit_auto",
            "test_token_auto",
            data={
                "remote": "local",
                "stages": "stage1,stage2",
                "sweeps": "",
                "exclude_stages": "",
                "exclude_sweeps": ""
            }
        )


def test_submit_worker_unregistered_remote_fails(wf_init):
    info_data = {"port": 8080, "token": "test_token"}
    with open(SERVER_INFO, "w") as f:
        json.dump(info_data, f)

    with patch("snap_workflow.utils.io.load_global_remotes", return_value={}), \
         patch("snap_workflow.utils.io.load_local_remotes", return_value={}):
        with pytest.raises(ValueError, match="Remote 'unknown_remote' is not registered"):
            server.submit_worker("unknown_remote", "profile1")

        with pytest.raises(ValueError, match="Remote 'unknown_remote' is not registered"):
            server.submit_auto("unknown_remote")


def test_submit_remote_registered_success(wf_init):
    info_data = {"port": 8080, "token": "test_token"}
    with open(SERVER_INFO, "w") as f:
        json.dump(info_data, f)

    remotes = {"my_cluster": {"host": "cluster.edu"}}
    mock_res = {"status": "ok"}

    with patch("snap_workflow.utils.io.load_global_remotes", return_value=remotes), \
         patch("snap_workflow.utils.io.load_local_remotes", return_value={}), \
         patch("snap_workflow.remote.setup.validate_remote_stage_resources"), \
         patch("snap_workflow.server.submit.ensure_remote_tunnel"), \
         patch("snap_workflow.worker.send_request", return_value=mock_res):
        
        res1 = server.submit_worker("my_cluster", profile="lonestar")
        assert res1 == mock_res

        res2 = server.submit_auto("my_cluster")
        assert res2 == mock_res
