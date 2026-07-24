import os
import json
import pytest
from unittest.mock import patch
import snap_workflow.core.io as io
import snap_workflow.core.workflow as workflow
import snap_workflow.core.stages as stages
import snap_workflow.core.spoints as spoints
import snap_workflow.core.server as server
import snap_workflow.cli as cli
from snap_workflow.core.workflow import initialize

def test_load_save_config_fallbacks(sandbox, env_dir):
    initialize(env_dir)
    import yaml
    
    # Save/load JSON config
    obj_json = {"type": "json", "val": 1}
    io.save_config("test_conf", obj_json, format="json")
    assert os.path.isfile(".workflow/test_conf.json")
    assert io.load_config("test_conf") == obj_json
    
    # Save/load YAML config
    obj_yaml = {"type": "yaml", "val": 2}
    io.save_config("test_conf_yml", obj_yaml, format="yaml")
    assert os.path.isfile(".workflow/test_conf_yml.yaml")
    assert io.load_config("test_conf_yml") == obj_yaml

def test_workflow_init_yaml(sandbox, env_dir):
    # Patch preference to return yaml
    with patch("snap_workflow.core.io.get_default_format", return_value="yaml"):
        workflow.initialize(env_dir)
        
        # Verify variables.yaml was created instead of variables.json
        assert os.path.isfile("params/variables.yaml")
        assert not os.path.isfile("params/variables.json")

def test_stage_add_yaml(sandbox, env_dir):
    with patch("snap_workflow.core.io.get_default_format", return_value="yaml"):
        workflow.initialize(env_dir)
        
        sbatch_details = {"partition": "default_part", "num_jobs": 1, "multi_submission": False}
        stages.add_stage("stage_yaml", sbatch_details=sbatch_details, stage_variables=["x"], stage_dependencies=[])
        
        # Verify env.yaml is created instead of json, and standalone sbatch.yaml is NOT created
        assert os.path.isfile("stage_yaml/env.yaml")
        assert not os.path.isfile("stage_yaml/sbatch.yaml")
        assert not os.path.isfile("stage_yaml/env.json")
        assert not os.path.isfile("stage_yaml/sbatch.json")
        
        # Write resources and custom sbatch nested options inside env.yaml
        import yaml
        with open("stage_yaml/env.yaml", "w") as f:
            yaml.safe_dump({
                "resources": {"cpus": 4, "gpus": 1, "mem": "16G"},
                "sbatch": {"time": "24:00:00", "partition": "gpu_part"}
            }, f)
            
        # validate_stage_resources should run without exceptions
        stages.validate_stage_resources()
        
        details = spoints.get_submission_details("stage_yaml", {"sbatch_details": {
            "num_jobs": 1,
            "multi_submission": False,
            "partition": "default_part"
        }})
        assert details["sbatch_flags"]["--partition"] == "gpu_part"
        assert details["sbatch_flags"]["--time"] == "24:00:00"

def test_cli_init_prompt_json(sandbox, env_dir):
    # Test main_init interactive prompt defaulting to json
    with patch("snap_workflow.core.io.Input_Collector.collect", side_effect=["y", "json", env_dir]):
        temp_config = os.path.join(env_dir, "config.json")
        with patch("snap_workflow.cli.GLOBAL_CONFIG_DIR", env_dir), \
             patch("snap_workflow.core.io.GLOBAL_CONFIG_DIR", env_dir):
            with pytest.raises(SystemExit):
                cli.main_init("init", [])
            
            # Check global configuration saved "json"
            assert os.path.isfile(temp_config)
            with open(temp_config, 'r') as f:
                assert json.load(f)["default_format"] == "json"

def test_cli_init_prompt_yaml(sandbox, env_dir):
    # Test main_init interactive prompt choosing yaml
    with patch("snap_workflow.core.io.Input_Collector.collect", side_effect=["y", "yaml", env_dir]):
        temp_config = os.path.join(env_dir, "config.json")
        with patch("snap_workflow.cli.GLOBAL_CONFIG_DIR", env_dir), \
             patch("snap_workflow.core.io.GLOBAL_CONFIG_DIR", env_dir):
            with pytest.raises(SystemExit):
                cli.main_init("init", [])
            
            # Check global configuration saved "yaml"
            assert os.path.isfile(temp_config)
            with open(temp_config, 'r') as f:
                assert json.load(f)["default_format"] == "yaml"
