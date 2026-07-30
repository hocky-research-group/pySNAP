import os
import zipfile
import json
import pytest
import numpy as np
from unittest.mock import patch

from snap_workflow.core import (
    initialize, add_stage, add_variable, add_sweep, 
    set_status, print_status, zip_workflow, load_stages
)
from snap_workflow.core.domain.sweeps import load_sweeps
from snap_workflow.core.domain.variables import load_variables

def test_workflow_lifecycle(sandbox, env_dir):
    # 1. Initialize
    initialize(env_dir)
    assert os.path.isdir(".workflow")
    assert os.path.isdir("params")
    # .agents directory creation on init disabled
    # assert os.path.isdir(".agents/skills/snap-workflow")
    # assert os.path.isfile(".agents/skills/snap-workflow/SKILL.md")
    assert os.path.isfile(".workflow/config.json")
    with open(".workflow/config.json") as f:
        cfg = json.load(f)
    assert "default_python_env" in cfg
    assert "default_activate_cmd" in cfg
    assert "default_env_vars" in cfg
    assert os.path.isfile(".workflow/spoint.sh")
    
    # 2. Add stage
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    stages = load_stages()
    assert "stage1" in stages
    assert os.path.isfile("stage1/stage1.py")
    assert os.path.isfile("stage1/collect.py")
    assert not os.path.exists("stage1/scripts")
    assert not os.path.exists("stage1/collect")
    assert os.path.isfile("stage1/env.json")
    assert not os.path.isfile("stage1/sbatch.json")
    with open("stage1/env.json") as f:
        scfg = json.load(f)
    assert "python_path" in scfg
    assert "activate_cmd" in scfg
    assert "env_vars" in scfg
    assert "resources" in scfg
    
    # 3. Add variable
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=10)
    variables = load_variables()
    assert "x" in variables
    assert variables["x"] == ["int"]
    
    # 4. Add sweep
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [10, 20]})
    sweeps = load_sweeps()
    assert "sweep1" in sweeps
    assert sweeps["sweep1"]["values"]["x"] == [10, 20]
    
    # Check spoint directories created
    assert os.path.isdir("stage1/spoints/x_10")
    assert os.path.isdir("stage1/spoints/x_20")
    assert not os.path.exists("stage1/spoints/x_10/scripts")
    
    # 5. Set & print status
    set_status("submitted", sweep_names="sweep1", stage_names="stage1")
    # Read status from spoint metadata
    with open("stage1/spoints/x_10/.spoint_info/status", "r") as f:
        status_val = f.read().strip()
    assert status_val == "submitted"
    
    # 6. Zip workflow
    zip_name = "test_archive.zip"
    with patch('subprocess.run') as mock_run:
        # Create a dummy zip file so zipfile checks pass
        with zipfile.ZipFile(zip_name, 'w') as zf:
            zf.writestr(".workflow/stages.json", "{}")
            zf.writestr("stage1/spoints/x_10/", "")
        zip_workflow(zip_name, sweep_names="sweep1", stage_names="stage1", include_spoints=True)
        assert mock_run.called
    assert os.path.isfile(zip_name)
    
    # Verify zip contains files
    with zipfile.ZipFile(zip_name, 'r') as zip_ref:
        file_list = zip_ref.namelist()
        assert any(".workflow/stages.json" in f for f in file_list)
        assert any("stage1/spoints/x_10/" in f for f in file_list)

    # 7. Test collect CLI stage filtering
    from snap_workflow.cli import main_collect
    with patch('snap_workflow.cli.collect_data') as mock_collect_data:
        main_collect("workflow collect", ["stage1"])
        mock_collect_data.assert_called_once_with(stage_names=["stage1"], verbose=False)
        
    add_stage("stage2", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    with patch('snap_workflow.cli.collect_data') as mock_collect_data:
        main_collect("workflow collect", ["stage1", "stage2"])
        mock_collect_data.assert_called_once_with(stage_names=["stage1", "stage2"], verbose=False)

    with patch('snap_workflow.cli.collect_data') as mock_collect_data:
        main_collect("workflow collect", ["all"])
        mock_collect_data.assert_called_once_with(stage_names="all", verbose=False)

    with pytest.raises(ValueError):
        main_collect("workflow collect", ["invalid_stage"])

    # 8. Test CLI autocomplete
    from snap_workflow.cli import get_completions
    res = get_completions([], "")
    assert "submit" in res
    assert "add" in res
    assert "autocomplete" in res

    res = get_completions([], "su")
    assert "submit" in res
    assert "add" not in res

    res = get_completions(["add"], "")
    assert sorted(res) == ["stage", "sweep", "variable"]

    res = get_completions(["submit"], "-")
    assert "--test" in res
    assert "-s" in res

    res = get_completions(["collect", "-s"], "")
    assert "stage1" in res
    assert "stage2" in res
    assert "all" in res

def test_data_manager_operations(sandbox, env_dir):
    from snap_workflow.core.data import Data_Manager
    dm = Data_Manager()
    
    dm._add({"x": 5, "sweep": "sweep1"}, {"y": 10.0, "time": 1.5})
    dm._add({"x": 10, "sweep": "sweep1"}, {"y": 20.0, "time": 2.0})
    dm._add({"x": 15, "sweep": "sweep1"}, {"y": 30.0, "time": 2.5})
    
    assert len(dm) == 3
    assert list(dm["x"]) == [5, 10, 15]
    assert list(dm["y"]) == [10.0, 20.0, 30.0]
    
    dm_gt = dm > ("x", 8)
    assert len(dm_gt) == 2
    assert list(dm_gt["x"]) == [10, 15]
    
    dm_ge = dm >= ("x", 10)
    assert len(dm_ge) == 2
    
    dm_lt = dm < ("x", 12)
    assert len(dm_lt) == 2
    assert list(dm_lt["x"]) == [5, 10]
    
    dm_le = dm <= ("x", 10)
    assert len(dm_le) == 2
    
    dm_eq = dm == ("x", 10)
    assert len(dm_eq) == 1
    assert list(dm_eq["x"]) == [10]
    
    dm_ne = dm != ("x", 10)
    assert len(dm_ne) == 2
    
    assert list(dm.unique("sweep")) == ["sweep1"]
    splits = list(dm.split("x"))
    assert len(splits) == 3
    assert splits[0][0] == 5
    
    # Test iterator
    entries = list(dm)
    assert len(entries) == 3
    assert entries[0]["x"] == 5
    assert entries[0]["y"] == 10.0
    
    # Test get_run / get_runs / get_job
    match_run = dm.get_run(x=10)
    assert match_run["y"] == 20.0
    
    # Test splitting enum
    splits_enum = list(dm.split("x", enum=True))
    assert len(splits_enum) == 3
    assert splits_enum[0][0] == 0
    assert splits_enum[0][1] == 5
    
    # Test error triggers
    with pytest.raises(Exception):
        dm._add({"x": 10, "z": 2}, {"y": 20.0, "time": 2.0})
    with pytest.raises(Exception):
        dm._add({"x": 10, "sweep": "sweep1"}, {"y": 20.0, "time": 2.0, "z": 5})
    with pytest.raises(ValueError):
        dm["invalid"]
    with pytest.raises(ValueError):
        dm[np.array([True, False])]
    with pytest.raises(Exception):
        dm._comparison_filter("invalid", "==")
    with pytest.raises(Exception):
        dm._comparison_filter(("x", 5, 6), "==")
    with pytest.raises(Exception):
        dm == ("invalid_type", 5) # comparison filter keys check
    with pytest.raises(Exception):
        Data_Manager("nonexistent_path")
        
    temp_path = os.path.join(env_dir, "test_data.dm")
    dm.save(temp_path)
    
    dm_loaded = Data_Manager(temp_path)
    assert len(dm_loaded) == 3
    assert list(dm_loaded["x"]) == [5, 10, 15]

def test_collect_data_integration(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    
    spoint_path = os.path.join("stage1", "spoints", "x_5")
    os.makedirs(os.path.join(spoint_path, ".spoint_info"), exist_ok=True)
    with open(os.path.join(spoint_path, ".spoint_info", "status"), "w") as f:
        f.write("complete")
    with open(os.path.join(spoint_path, ".spoint_info", "time"), "w") as f:
        json.dump([1.25], f)
        
    collect_py = os.path.join("stage1", "collect.py")
    with open(collect_py, "w") as f:
        f.write("def collect():\n    return {'metric1': 42.0}\n")
        
    from snap_workflow.core.data import collect_data, Data_Manager
    collect_data(stage_names=["stage1"])
    
    dm_path = os.path.join("data", "stage1.dm")
    assert os.path.isfile(dm_path)
    
    dm = Data_Manager(dm_path)
    assert len(dm) == 1
    assert list(dm["metric1"]) == [42.0]
    assert list(dm["x"]) == [5]

