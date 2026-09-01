import os
import pytest
from unittest.mock import patch
from snap_workflow.core.workflow import initialize
from snap_workflow.remote import io as r_io


def test_remotes_io_and_config(sandbox, tmp_path):
    global_dir = str(tmp_path / "global_config")
    g_remotes_file = os.path.join(global_dir, "remotes.json")

    with patch("snap_workflow.utils.constants.GLOBAL_CONFIG_DIR", global_dir), \
         patch("snap_workflow.utils.constants.GLOBAL_REMOTES_FILE", g_remotes_file):

        # Test remotes when missing
        assert r_io.load_global_remotes() == {}
        assert r_io.load_local_remotes() == {}

        # Save and load global remotes
        remotes_data = {"cluster1": {"host": "user@cluster1", "path": "/home/cluster1"}}
        r_io.save_global_remotes(remotes_data)
        assert r_io.load_global_remotes() == remotes_data

        # Save and load local remotes
        initialize(".")
        local_remotes = {"cluster1": {"path": "/local/override/path"}}
        r_io.save_local_remotes(local_remotes)
        assert r_io.load_local_remotes() == local_remotes

        # Verify load_local_remotes works from inside a subdirectory
        sub_dir = os.path.join(os.getcwd(), "stage1", "spoints")
        os.makedirs(sub_dir, exist_ok=True)
        orig_cwd = os.getcwd()
        try:
            os.chdir(sub_dir)
            assert r_io.load_local_remotes() == local_remotes
        finally:
            os.chdir(orig_cwd)

        # Test get_remotes_info with SSH check mocked
        from snap_workflow.remote import get_remotes_info
        with patch("snap_workflow.remote.ssh.is_remote_ssh_connected", return_value=True):
            info = get_remotes_info()
            assert len(info) == 1
            assert info[0]["name"] == "cluster1"
            assert info[0]["host"] == "user@cluster1"
            assert info[0]["path"] == "/local/override/path"
            assert info[0]["connected"] is True
