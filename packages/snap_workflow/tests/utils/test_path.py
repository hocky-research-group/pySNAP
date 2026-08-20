import os
import sys
import pytest
from unittest.mock import patch

from snap_workflow.utils import constants, path, io
from snap_workflow.utils.exceptions import WorkflowError


def test_get_root_and_path_helpers(sandbox, env_dir):
    os.makedirs(os.path.join(sandbox, ".workflow"), exist_ok=True)
    root = path.get_root()
    assert os.path.isabs(root)
    assert os.path.isdir(os.path.join(root, ".workflow"))

    # Test from_root
    assert path.from_root(".workflow") == os.path.join(root, ".workflow")
    assert path.from_root("sub", "file.txt") == os.path.join(root, "sub", "file.txt")

    # Test isfile, isdir, exists
    assert path.isdir(".workflow")
    assert path.exists(".workflow")
    
    test_file = path.from_root(".workflow", "test.txt")
    with open(test_file, "w") as f:
        f.write("test")
    assert path.isfile(".workflow", "test.txt")
    assert path.exists(".workflow", "test.txt")

    # Test path resolution from nested directory
    nested_dir = os.path.join(sandbox, "nested", "sub_dir")
    os.makedirs(nested_dir, exist_ok=True)
    
    old_cwd = os.getcwd()
    try:
        os.chdir(nested_dir)
        # get_root should find workflow root without changing os.getcwd()
        assert path.get_root() == root
        assert os.getcwd() == nested_dir
        assert path.from_root(".workflow") == os.path.join(root, ".workflow")
    finally:
        os.chdir(old_cwd)


def test_get_default_python_file(tmp_path):
    global_dir = str(tmp_path / "global_config")
    with patch("snap_workflow.utils.constants.GLOBAL_CONFIG_DIR", global_dir):
        expected_file = os.path.join(global_dir, constants.DEFAULT_PYTHON)
        assert path.get_default_python_file() == expected_file


def test_ensure_default_python_path(tmp_path):
    global_dir = str(tmp_path / "global_config")
    with patch("snap_workflow.utils.constants.GLOBAL_CONFIG_DIR", global_dir):
        custom_py = "/custom/env/bin/python"
        result = path.ensure_default_python_path(custom_py)
        assert result == custom_py
        
        target_file = path.get_default_python_file()
        assert os.path.isfile(target_file)
        with open(target_file, "r") as f:
            content = f.read().strip()
        assert content == custom_py

        # Second call with overwrite=False preserves existing custom_py
        another_py = "/another/env/bin/python"
        result2 = path.ensure_default_python_path(another_py, overwrite=False)
        assert result2 == custom_py
        with open(target_file, "r") as f:
            assert f.read().strip() == custom_py

        # Call with overwrite=True replaces custom_py
        result3 = path.ensure_default_python_path(another_py, overwrite=True)
        assert result3 == another_py
        with open(target_file, "r") as f:
            assert f.read().strip() == another_py


def test_load_python_path_hierarchy(tmp_path):
    global_dir = str(tmp_path / "global_config")
    project_dir = tmp_path / "my_project"
    wf_dir = project_dir / ".workflow"
    wf_dir.mkdir(parents=True)
    stage_dir = project_dir / "sim_stage"
    stage_dir.mkdir(parents=True)

    with patch("snap_workflow.utils.constants.GLOBAL_CONFIG_DIR", global_dir), \
         patch("snap_workflow.utils.path.get_root", return_value=str(project_dir)):
        
        # 1. Global level fallback
        global_py = "/global/python/bin/python"
        path.ensure_default_python_path(global_py)
        assert path.load_python_path() == global_py
        assert path.load_python_path(stage="sim_stage") == global_py

        # 2. Project level override
        project_py = "/project/python/bin/python"
        io.save_json(str(wf_dir / "config.json"), {"default_python_env": project_py}, full_path=True)
        assert path.load_python_path() == project_py
        assert path.load_python_path(stage="sim_stage") == project_py

        # 3. Stage level override
        stage_py = "/stage/python/bin/python"
        io.save_json(str(stage_dir / "env.json"), {"python_path": stage_py}, full_path=True)
        assert path.load_python_path(stage="sim_stage") == stage_py
        # Calling without stage should still yield project level
        assert path.load_python_path() == project_py


def test_load_python_path_raises_exception_when_unresolved(tmp_path):
    global_dir = str(tmp_path / "global_config")
    target_file = os.path.join(global_dir, constants.DEFAULT_PYTHON)
    
    with patch("snap_workflow.utils.constants.GLOBAL_CONFIG_DIR", global_dir), \
         patch("snap_workflow.utils.path.get_root", side_effect=Exception("No root")):
        
        if os.path.exists(target_file):
            os.remove(target_file)
            
        with pytest.raises(WorkflowError, match="No valid Python interpreter path found"):
            path.load_python_path()
