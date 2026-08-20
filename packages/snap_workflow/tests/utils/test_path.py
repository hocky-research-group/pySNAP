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
    assert path.from_root() == root

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
        assert path.get_root() == root
        assert os.getcwd() == nested_dir
        assert path.from_root(".workflow") == os.path.join(root, ".workflow")
        assert path.rel_to_root(".") == os.path.relpath(root, nested_dir)
    finally:
        os.chdir(old_cwd)


def test_relpath_and_abspath_join():
    assert path.abspath("file.txt") == os.path.abspath("file.txt")
    assert path.join("a", "b") == os.path.join("a", "b")

    with patch("snap_workflow.utils.path.get_root", side_effect=Exception("no root")):
        rel = path.relpath("/a/b/c", start=None)
        assert rel == os.path.relpath("/a/b/c", os.getcwd())


def test_from_dir_context_manager(tmp_path):
    sub_dir = tmp_path / "sub"
    sub_dir.mkdir()
    start_cwd = os.getcwd()

    with path.FromDir(str(sub_dir)):
        assert os.getcwd() == str(sub_dir)

    assert os.getcwd() == start_cwd


def test_make_sym_broken_link_and_overwrite(tmp_path):
    target = tmp_path / "target.txt"
    target.write_text("hello")
    link = tmp_path / "link.txt"

    path.make_sym(str(target), str(link), relative=False)
    assert link.is_symlink()

    # Broken symlink replacement
    target.unlink()
    new_target = tmp_path / "new_target.txt"
    new_target.write_text("new hello")
    path.make_sym(str(new_target), str(link), relative=False)
    assert link.read_text() == "new hello"

    # Overwrite existing symlink
    another_target = tmp_path / "another.txt"
    another_target.write_text("another")
    path.make_sym(str(another_target), str(link), overwrite=True, relative=False)
    assert link.read_text() == "another"


def test_clear_directory(tmp_path):
    d = tmp_path / "dir_to_clear"
    d.mkdir()
    (d / "f1.txt").write_text("1")
    (d / "sub_dir").mkdir()
    (d / "sub_dir" / "f2.txt").write_text("2")

    path.clear_directory(str(d))
    assert os.listdir(str(d)) == []


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

        another_py = "/another/env/bin/python"
        result2 = path.ensure_default_python_path(another_py, overwrite=False)
        assert result2 == custom_py

        result3 = path.ensure_default_python_path(another_py, overwrite=True)
        assert result3 == another_py


def test_load_python_path_yaml_stage_and_fallbacks(tmp_path):
    global_dir = str(tmp_path / "global_config")
    project_dir = tmp_path / "my_project"
    wf_dir = project_dir / ".workflow"
    wf_dir.mkdir(parents=True)
    stage_dir = project_dir / "sim_stage"
    stage_dir.mkdir(parents=True)

    with patch("snap_workflow.utils.constants.GLOBAL_CONFIG_DIR", global_dir), \
         patch("snap_workflow.utils.path.get_root", return_value=str(project_dir)):
        
        # Test stage env.yaml override
        stage_yaml_py = "/stage/yaml/bin/python"
        with open(stage_dir / "env.yaml", "w") as f:
            f.write(f"python_path: '{stage_yaml_py}'\n")

        assert path.load_python_path(stage="sim_stage") == stage_yaml_py


def test_load_python_path_raises_exception_when_unresolved(tmp_path):
    global_dir = str(tmp_path / "global_config")
    target_file = os.path.join(global_dir, constants.DEFAULT_PYTHON)
    
    with patch("snap_workflow.utils.constants.GLOBAL_CONFIG_DIR", global_dir), \
         patch("snap_workflow.utils.path.get_root", side_effect=Exception("No root")):
        
        if os.path.exists(target_file):
            os.remove(target_file)
            
        with pytest.raises(WorkflowError, match="No valid Python interpreter path found"):
            path.load_python_path()
