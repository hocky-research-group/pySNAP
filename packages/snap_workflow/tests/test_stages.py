import os
import json
import pytest
from unittest.mock import patch, MagicMock
from snap_workflow.core.workflow import initialize
from snap_workflow.core.stages import (
    load_stages,
    add_stage,
    print_stages,
    get_dependent_stages,
    validate_stage_resources
)
from snap_workflow.core.exceptions import StageAlreadyExistsError

def test_load_stages_filtering(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=[], stage_dependencies=[])
    add_stage("stage2", sbatch_details=None, stage_variables=[], stage_dependencies=[])

    # 1. list containing "all"
    assert len(load_stages(["stage1", "all"])) == 2
    
    # 2. list filtering
    filtered_dict = load_stages(["stage1"])
    assert len(filtered_dict) == 1
    assert "stage1" in filtered_dict
    assert "stage2" not in filtered_dict

    # 3. string equal to "all"
    assert len(load_stages("all")) == 2

    # 4. string filtering (returns the specific stage info dict directly)
    stage_info = load_stages("stage1")
    assert isinstance(stage_info, dict)
    assert "variables" in stage_info

def test_add_stage_duplicate(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=[], stage_dependencies=[])
    
    # Duplicate add stage throws StageAlreadyExistsError
    with pytest.raises(StageAlreadyExistsError):
        add_stage("stage1")

def test_print_stages(sandbox, env_dir, capsys):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=[], stage_dependencies=[])
    print_stages()
    captured = capsys.readouterr()
    assert "stage1" in captured.out

def test_make_new_stage_files_local_config_exception(sandbox, env_dir):
    initialize(env_dir)
    
    # Mock load_json to fail for local_config to cover exception branch
    from snap_workflow.core import io as core_io
    original_load_json = core_io.load_json
    def mock_load_json(path, *args, **kwargs):
        if "config.json" in str(path):
            raise RuntimeError("mock read config error")
        # otherwise run normally
        return original_load_json(path, *args, **kwargs)
        
    with patch("snap_workflow.core.io.load_json", side_effect=mock_load_json):
        add_stage("stage_error", sbatch_details=None, stage_variables=[], stage_dependencies=[])
        assert os.path.isfile("stage_error/env.json")

def test_get_dependent_stages(sandbox, env_dir):
    initialize(env_dir)
    # Stage without dependent_stages key (to cover line 119)
    # We will manually inject a stage without dependent_stages
    stages_data = {
        "stage_no_deps": {
            "variables": []
        }
    }
    with open(".workflow/stages.json", "w") as f:
        json.dump(stages_data, f)
        
    deps = get_dependent_stages("stage_no_deps")
    assert deps == []

    # Verify nested dependencies loop
    stages_data_nested = {
        "stageA": {
            "variables": [],
            "dependent_stages": ["stageB"]
        },
        "stageB": {
            "variables": [],
            "dependent_stages": []
        }
    }
    with open(".workflow/stages.json", "w") as f:
        json.dump(stages_data_nested, f)
        
    deps_nested = get_dependent_stages("stageA")
    assert "stageB" in deps_nested

def test_validate_stage_resources_failures(sandbox, env_dir):
    initialize(env_dir)
    
    # 1. stage1 exists but has no env file (FileNotFoundError -> continue)
    add_stage("stage1", sbatch_details=None, stage_variables=[], stage_dependencies=[])
    os.remove("stage1/env.json")
    validate_stage_resources() # Should run without exception

    # 2. env file has invalid JSON (Exception -> ValueError)
    os.makedirs("stage1", exist_ok=True)
    with open("stage1/env.json", "w") as f:
        f.write("invalid json")
    with pytest.raises(ValueError) as exc:
        validate_stage_resources()
    assert "Failed to load environment file" in str(exc.value)

    # 3. Non-integer resources (cpu_val = -1 casting fallback exceptions)
    with open("stage1/env.json", "w") as f:
        json.dump({
            "resources": {
                "cpus": "invalid_int",
                "gpus": 1,
                "mem": "16G"
            }
        }, f)
    with pytest.raises(ValueError) as exc:
        validate_stage_resources()
    assert "Resource values cannot be -1" in str(exc.value)

    # 4. Non-integer gpus (gpu_val = -1 casting fallback exceptions)
    with open("stage1/env.json", "w") as f:
        json.dump({
            "resources": {
                "cpus": 4,
                "gpus": "invalid_gpu",
                "mem": "16G"
            }
        }, f)
    with pytest.raises(ValueError) as exc:
        validate_stage_resources()
    assert "Resource values cannot be -1" in str(exc.value)
