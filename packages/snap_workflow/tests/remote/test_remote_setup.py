import os
import json
import pytest
import subprocess
from unittest.mock import patch, MagicMock

from snap_workflow.core.workflow import initialize
from snap_workflow.core.domain.stages import add_stage
from snap_workflow.remote import setup as remote_setup
from snap_workflow.utils.version import __version__ as local_version

def test_get_template():
    tmpl = remote_setup.get_template("validate_resources.py")
    assert "RESOLVED_PATH" in tmpl

def test_validate_remote_stage_resources(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=[], stage_dependencies=[])
    env_file = os.path.join("stage1", "env.json")
    with open(env_file, "r") as f:
        env_data = json.load(f)
    env_data["resources"] = {"cpus": 1, "gpus": 0, "mem": "1G"}
    with open(env_file, "w") as f:
        json.dump(env_data, f)
    
    # 1. Local validation
    remote_setup.validate_remote_stage_resources("local")
    
    # 2. Remote python validation success (with kwargs)
    with patch("snap_workflow.remote.setup.run_remote_python", return_value="ok"):
        remote_setup.validate_remote_stage_resources("cluster_host", "/path", stages="st1", sweeps="sw1")

    # 3. Remote python failure with bash fallback success
    with patch("snap_workflow.remote.setup.run_remote_python", side_effect=Exception("python3 command not found")), \
         patch("snap_workflow.remote.setup.run_remote_bash", return_value="ok"):
        remote_setup.validate_remote_stage_resources("cluster_host", "/path")

    # 4. Remote python failure with bash fallback failure -> raises ValueError
    with patch("snap_workflow.remote.setup.run_remote_python", side_effect=Exception("python3 command not found")), \
         patch("snap_workflow.remote.setup.run_remote_bash", side_effect=Exception("Remote python execution failed: validation error")):
        with pytest.raises(ValueError) as exc:
            remote_setup.validate_remote_stage_resources("cluster_host", "/path")
        assert "validation error" in str(exc.value)

def test_resolve_remote_path(sandbox, env_dir):
    initialize(env_dir)
    def mock_run_check(cmd, *args, **kwargs):
        res = MagicMock()
        if "not_exists" in cmd[2]:
            res.stdout = "not_exists\n"
        elif "empty" in cmd[2]:
            res.stdout = "empty\n"
        else:
            res.stdout = "not_empty\n"
        return res

    with patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.stdout = "not_exists\n"
        mock_run.return_value = mock_res
        assert remote_setup.resolve_remote_path("cluster_host", "~/sims") == "~/sims"

        mock_res.stdout = "not_empty\n"
        res_path = remote_setup.resolve_remote_path("cluster_host", "~/sims")
        assert res_path.endswith("/sims/" + os.path.basename(os.getcwd()))

        mock_run.side_effect = Exception("ssh error")
        res_path_err = remote_setup.resolve_remote_path("cluster_host", "~/sims")
        assert res_path_err.endswith("/sims/" + os.path.basename(os.getcwd()))

def test_validate_remote_snap_workflow_version():
    # Matching version
    with patch("snap_workflow.remote.setup.run_remote_python", return_value=f"{local_version}\n"):
        remote_setup.validate_remote_snap_workflow_version("cluster_host")

    # Mismatched version
    with patch("snap_workflow.remote.setup.run_remote_python", return_value="0.0.1\n"):
        with pytest.raises(ValueError) as exc:
            remote_setup.validate_remote_snap_workflow_version("cluster_host")
        assert "version mismatch" in str(exc.value)

    # Missing python/snap_workflow
    with patch("snap_workflow.remote.setup.run_remote_python", side_effect=Exception("ModuleNotFoundError")):
        with pytest.raises(ValueError) as exc:
            remote_setup.validate_remote_snap_workflow_version("cluster_host")
        assert "not installed" in str(exc.value)

def test_validate_remote_workspace_python_environments():
    with patch("snap_workflow.remote.setup.run_remote_python", return_value=json.dumps(["/usr/bin/python3"])), \
         patch("snap_workflow.remote.setup.validate_remote_snap_workflow_version") as mock_val:
        remote_setup.validate_remote_workspace_python_environments("cluster_host", "/path")
        assert mock_val.called

    with patch("snap_workflow.remote.setup.run_remote_python", side_effect=Exception("script error")), \
         patch("snap_workflow.remote.setup.validate_remote_snap_workflow_version") as mock_val:
        remote_setup.validate_remote_workspace_python_environments("cluster_host", "/path")
        assert mock_val.called

def test_launch_remote_workers_server_side(sandbox, env_dir):
    initialize(env_dir)
    with patch("snap_workflow.utils.io.load_global_remotes", return_value={"c1": {"host": "user@c1"}}), \
         patch("snap_workflow.utils.io.load_local_remotes", return_value={"c1": {"path": "~/sims"}}), \
         patch("snap_workflow.remote.setup.resolve_remote_path", return_value="~/sims"), \
         patch("snap_workflow.remote.setup.validate_remote_workspace_python_environments"), \
         patch("snap_workflow.remote.setup.validate_remote_stage_resources"), \
         patch("snap_workflow.remote.setup.run_remote_python", return_value=json.dumps({"cpus-per-task": 4})), \
         patch("snap_workflow.remote.setup.run_remote_bash", return_value="login01\n"), \
         patch("subprocess.run") as mock_run:
        
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_run.return_value = mock_res
        
        remote_setup.launch_remote_workers_server_side(
            server_port=9000,
            token="secret_token",
            remote_name="c1",
            profile="cpu",
            num_workers=2
        )
        assert mock_run.called

def test_launch_remote_workers_unregistered_remotes(sandbox, env_dir):
    initialize(env_dir)
    with patch("snap_workflow.utils.io.load_global_remotes", return_value={}):
        with pytest.raises(ValueError) as exc:
            remote_setup.launch_remote_workers_server_side(9000, "token", "unregistered", "cpu")
        assert "not registered globally" in str(exc.value)

    with patch("snap_workflow.utils.io.load_global_remotes", return_value={"c1": {"host": "host"}}), \
         patch("snap_workflow.utils.io.load_local_remotes", return_value={}):
        with pytest.raises(ValueError) as exc:
            remote_setup.launch_remote_workers_server_side(9000, "token", "c1", "cpu")
        assert "not been set up locally" in str(exc.value)

def test_launch_remote_workers_fixme_and_missing_profile(sandbox, env_dir):
    initialize(env_dir)
    with patch("snap_workflow.utils.io.load_global_remotes", return_value={"c1": {"host": "user@c1"}}), \
         patch("snap_workflow.utils.io.load_local_remotes", return_value={"c1": {"path": "~/sims"}}), \
         patch("snap_workflow.remote.setup.resolve_remote_path", return_value="~/sims"), \
         patch("snap_workflow.remote.setup.validate_remote_workspace_python_environments"), \
         patch("snap_workflow.remote.setup.validate_remote_stage_resources"), \
         patch("snap_workflow.remote.setup.run_remote_python", side_effect=Exception("profile error")), \
         patch("snap_workflow.remote.setup.run_remote_bash", side_effect=Exception("profile bash error")):
        with pytest.raises(ValueError) as exc:
            remote_setup.launch_remote_workers_server_side(9000, "token", "c1", "bad_profile")
        assert "was not found" in str(exc.value)

    with patch("snap_workflow.utils.io.load_global_remotes", return_value={"c1": {"host": "user@c1"}}), \
         patch("snap_workflow.utils.io.load_local_remotes", return_value={"c1": {"path": "~/sims"}}), \
         patch("snap_workflow.remote.setup.resolve_remote_path", return_value="~/sims"), \
         patch("snap_workflow.remote.setup.validate_remote_workspace_python_environments"), \
         patch("snap_workflow.remote.setup.validate_remote_stage_resources"), \
         patch("snap_workflow.remote.setup.run_remote_python", return_value=json.dumps({"partition": "FIXME_PARTITION"})):
        with pytest.raises(ValueError) as exc:
            remote_setup.launch_remote_workers_server_side(9000, "token", "c1", "fixme_profile")
        assert "unconfigured 'FIXME'" in str(exc.value)

def test_setup_remote_cluster(sandbox, env_dir):
    initialize(env_dir)
    with patch("subprocess.run") as mock_run, \
         patch("snap_workflow.remote.setup.resolve_remote_path", return_value="~/sims"), \
         patch("snap_workflow.remote.setup.run_remote_python", return_value="ok"), \
         patch("snap_workflow.remote.setup.run_remote_bash", return_value="ok"):
        
        mock_res = MagicMock()
        mock_res.stdout = "ok\n"
        mock_res.returncode = 0
        mock_run.return_value = mock_res
        
        res_path = remote_setup.setup_remote_cluster("cluster_host", "~/sims")
        assert res_path == "~/sims"

def test_setup_remote_cluster_failures(sandbox, env_dir):
    initialize(env_dir)
    with patch("subprocess.run", side_effect=Exception("ssh connection failed")):
        with pytest.raises(ValueError) as exc:
            remote_setup.setup_remote_cluster("cluster_host", "~/sims")
        assert "Cannot connect to remote host" in str(exc.value)
