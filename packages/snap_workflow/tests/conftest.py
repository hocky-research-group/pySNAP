import os
import shutil
import tempfile
import pytest
from snap_workflow.server import start_server

@pytest.fixture
def sandbox():
    """Fixture to create and change cwd into a temporary sandbox directory for test run."""
    test_dir = tempfile.mkdtemp()
    original_cwd = os.getcwd()
    os.chdir(test_dir)
    
    yield test_dir
    
    os.chdir(original_cwd)
    shutil.rmtree(test_dir)

@pytest.fixture
def env_dir():
    """Fixture to create a temporary directory simulating a virtual python environment directory."""
    test_env_dir = tempfile.mkdtemp()
    
    yield test_env_dir
    
    shutil.rmtree(test_env_dir)

@pytest.fixture
def workflow_server():
    """Fixture to start manager server in the background and clean up on teardown."""
    servers = []
    def _start(host="127.0.0.1", port=0):
        srv, info = start_server(host, port)
        servers.append(srv)
        return srv, info
        
    yield _start
    
    for srv in servers:
        try:
            from snap_workflow.remote.tunnels import stop_remote_tunnels
            stop_remote_tunnels(srv)
            srv.shutdown()
            srv.server_close()
        except Exception:
            pass
