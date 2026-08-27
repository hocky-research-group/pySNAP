import os
import pytest
from unittest.mock import patch, MagicMock

from snap_workflow.core.workflow import setup_agent_skills, initialize, check_existing_root, zip_workflow
from snap_workflow.core.domain.stages import add_stage
from snap_workflow.core.domain.variables import add_variable
from snap_workflow.core.domain.sweeps import add_sweep


def test_check_existing_root_outside(sandbox):
    assert check_existing_root() is False


def test_setup_agent_skills_base(sandbox):
    setup_agent_skills()
    assert os.path.exists(".agents/skills/snap-workflow/SKILL.md")


def test_setup_agent_skills_optional_packages(sandbox):
    mock_sim_spec = MagicMock()
    mock_sim_spec.submodule_search_locations = ["/fake/sim_path"]

    mock_ana_spec = MagicMock()
    mock_ana_spec.submodule_search_locations = ["/fake/ana_path"]

    def fake_find_spec(name):
        if name == "snap_simulate":
            return mock_sim_spec
        elif name == "snap_analyze":
            return mock_ana_spec
        return None

    def fake_isfile(path):
        if "SKILL.md" in path:
            return True
        return os.path.isfile(path)

    with patch("importlib.util.find_spec", side_effect=fake_find_spec), \
         patch("shutil.copy") as mock_copy, \
         patch("os.path.isfile", side_effect=fake_isfile):
        setup_agent_skills()
        assert mock_copy.called


def test_initialize_custom_env_path(sandbox, tmp_path):
    global_dir = str(tmp_path / "global_config")
    custom_py = "/custom/python/bin/python"
    with patch("snap_workflow.utils.constants.GLOBAL_CONFIG_DIR", global_dir):
        initialize(env_path=custom_py, force=True)
        from snap_workflow.utils import path
        assert path.load_python_path() == custom_py


def test_zip_workflow_spoints_iteration(sandbox):
    initialize(force=True)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=10)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [10, 20]})

    with patch("subprocess.run") as mock_run:
        zip_workflow("archive.zip", sweep_names="sweep1", stage_names="stage1", include_spoints=True)
        assert mock_run.called
        calls = [c[0][0] for c in mock_run.call_args_list]
        assert any(any("stage1/spoints" in item for item in cmd) for cmd in calls)


def test_initialize_sbatch_profiles_with_slurm(sandbox):
    with patch("snap_workflow.utils.exec.has_slurm", return_value=True):
        initialize(force=True)
        assert os.path.isdir("sbatch_profiles")
        assert os.path.isfile(os.path.join("sbatch_profiles", "cpu.json"))
        assert os.path.isfile(os.path.join("sbatch_profiles", "gpu.json"))


def test_initialize_sbatch_profiles_without_slurm(sandbox):
    with patch("snap_workflow.utils.exec.has_slurm", return_value=False):
        initialize(force=True)
        assert not os.path.exists("sbatch_profiles")
