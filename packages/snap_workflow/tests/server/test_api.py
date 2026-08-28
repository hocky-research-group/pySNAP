import os
import json
import pytest
from unittest.mock import patch
from snap_workflow import server
from snap_workflow.core.workflow import initialize
from snap_workflow.utils.constants import SERVER_INFO


@pytest.fixture
def wf_init(sandbox):
    initialize(force=True)


def test_load_server_info_missing_file(wf_init):
    from snap_workflow.utils import io
    if os.path.isfile(SERVER_INFO):
        os.remove(SERVER_INFO)
    with pytest.raises(ValueError, match="Manager server is not running locally"):
        io.load_server_info()


def test_load_server_info_success(wf_init):
    from snap_workflow.utils import io
    info_data = {"port": 8080, "token": "test_token_123"}
    with open(SERVER_INFO, "w") as f:
        json.dump(info_data, f)

    url, token = io.load_server_info()
    assert url == "http://127.0.0.1:8080"
    assert token == "test_token_123"


def test_get_server_status_and_shutdown(wf_init):
    info_data = {"url": "http://127.0.0.1:9090", "token": "test_token_status"}
    with open(SERVER_INFO, "w") as f:
        json.dump(info_data, f)

    mock_status_res = {"status": "ok", "active_leases": {}}
    mock_shutdown_res = {"status": "shutdown"}

    with patch("snap_workflow.server.api.send_request", side_effect=[mock_status_res, mock_shutdown_res]) as mock_send:
        st = server.get_server_status()
        assert st == mock_status_res
        mock_send.assert_called_with("http://127.0.0.1:9090/status", "test_token_status", timeout=10)

        shut = server.shutdown_server()
        assert shut == mock_shutdown_res
        mock_send.assert_called_with("http://127.0.0.1:9090/shutdown", "test_token_status", timeout=10)


def test_server_api_connection_error_raises_value_error(wf_init):
    info_data = {"url": "http://127.0.0.1:9090", "token": "test_token_error"}
    with open(SERVER_INFO, "w") as f:
        json.dump(info_data, f)

    with patch("snap_workflow.server.api.send_request", return_value=None):
        with pytest.raises(ValueError, match="Failed to communicate with workflow server"):
            server.get_server_status()

        with pytest.raises(ValueError, match="Failed to communicate with workflow server"):
            server.shutdown_server()
