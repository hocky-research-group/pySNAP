import json
import pytest
import urllib.error
from unittest.mock import patch, MagicMock
from snap_workflow.dispatcher.base import BaseDispatcher


class ConcreteTestDispatcher(BaseDispatcher):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dispatched_tasks = []
        self.reaped = False
        self.cleaned_up = False
        self.capacity = True

    def has_capacity(self) -> bool:
        return self.capacity

    def dispatch_task(self, task):
        self.dispatched_tasks.append(task)
        self.capacity = False  # after one task, simulate full

    def reap_finished(self):
        self.reaped = True
        self.capacity = True

    def cleanup(self):
        self.cleaned_up = True


def test_base_dispatcher_init():
    d = ConcreteTestDispatcher(
        server_url="http://localhost:8000/",
        token="test_token",
        stages="stage1",
        sweeps="sweep1",
        exclude_stages="stage2",
        exclude_sweeps="sweep2",
        host="my_host",
        idle_delay=0.1
    )
    assert d.server_url == "http://localhost:8000"
    assert d.token == "test_token"
    assert d.stages == "stage1"
    assert d.sweeps == "sweep1"
    assert d.exclude_stages == "stage2"
    assert d.exclude_sweeps == "sweep2"
    assert d.host == "my_host"


def test_send_request_success():
    d = ConcreteTestDispatcher(server_url="http://localhost:8000", token="token")
    mock_resp = MagicMock()
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.read.return_value = json.dumps({"status": "ok"}).encode("utf-8")

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = d.send_request("http://localhost:8000/api", data={"test": 123})
        assert res == {"status": "ok"}


def test_send_request_retries():
    d = ConcreteTestDispatcher(server_url="http://localhost:8000", token="token")
    calls = 0

    def mock_urlopen(req, timeout=None):
        nonlocal calls
        calls += 1
        if calls < 2:
            raise urllib.error.URLError("Temporary error")
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.read.return_value = json.dumps({"status": "recovered"}).encode("utf-8")
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        res = d.send_request("http://localhost:8000/api", retries=3, backoff=0.01)
        assert res == {"status": "recovered"}
        assert calls == 2


def test_request_work_query_params():
    d = ConcreteTestDispatcher(
        server_url="http://localhost:8000",
        token="token",
        stages="stageA",
        sweeps="sweepB",
        exclude_stages="stageC",
        exclude_sweeps="sweepD",
        host="hostX"
    )

    requested_urls = []

    def mock_send_request(url, data=None, retries=5, backoff=1.0):
        requested_urls.append(url)
        return {"status": "shutdown"}

    with patch.object(d, "send_request", side_effect=mock_send_request):
        d.request_work()

    assert len(requested_urls) == 1
    url = requested_urls[0]
    assert "stages=stageA" in url
    assert "sweeps=sweepB" in url
    assert "exclude_stages=stageC" in url
    assert "exclude_sweeps=sweepD" in url
    assert "host=hostX" in url


def test_notify_completion():
    d = ConcreteTestDispatcher(server_url="http://localhost:8000", token="token")
    payloads = []

    def mock_send_request(url, data=None, retries=5, backoff=1.0):
        payloads.append((url, data))
        return {"status": "success"}

    with patch.object(d, "send_request", side_effect=mock_send_request):
        success = d.notify_completion("stage1/spoints/x_5", success=True, returncode=0, extra_data={"foo": "bar"})
        assert success is True
        assert len(payloads) == 1
        assert payloads[0][0] == "http://localhost:8000/update_status"
        assert payloads[0][1]["status"] == "COMPLETED"
        assert payloads[0][1]["foo"] == "bar"


def test_template_run_lifecycle_and_shutdown():
    d = ConcreteTestDispatcher(server_url="http://localhost:8000", token="token", idle_delay=0.01)

    responses = [
        {"status": "spoint", "sweep": "sw1", "stage": "st1", "spoint_dict": {"x": 1}, "spoint_path": "st1/spoints/x_1"},
        {"status": "shutdown"}
    ]

    def mock_request_work():
        if responses:
            return responses.pop(0)
        return {"status": "shutdown"}

    with patch.object(d, "request_work", side_effect=mock_request_work), \
         patch.object(d, "notify_shutdown") as mock_notify_sd:
        d.run()

    assert len(d.dispatched_tasks) == 1
    assert d.dispatched_tasks[0]["stage"] == "st1"
    assert d.reaped is True
    assert d.cleaned_up is True
    assert mock_notify_sd.called
