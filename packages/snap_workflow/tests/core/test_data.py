import os
import json
import pickle
import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from snap_workflow.core.workflow import initialize
from snap_workflow.core.domain.stages import add_stage
from snap_workflow.core.domain.variables import add_variable
from snap_workflow.core.domain.sweeps import add_sweep
from snap_workflow.core.data import collect_data, Data_Manager

def test_collect_data_routing(sandbox, env_dir, capsys):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=[], stage_dependencies=[])
    
    # 1. Remove collect.py template to test the "continue if not os.path.isfile" path
    collect_path = os.path.join("stage1", "collect.py")
    if os.path.isfile(collect_path):
        os.remove(collect_path)
    collect_data(stage_names=None, verbose=True)
    captured = capsys.readouterr()
    assert "Collecting stage1" not in captured.out

    # 2. Re-create collect.py to test successful collection paths
    with open(collect_path, "w") as f:
        f.write("def collect():\n    return {'loss': 0.1}\n")
    
    # 3. Test stage_names as a single string (not a list) + verify verbose logs
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=1)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [1]})
    
    collect_data(stage_names="stage1", verbose=True)
    captured = capsys.readouterr()
    assert "Collecting stage1" in captured.out
    assert "Data collection successful" in captured.out

    # 4. Test not verbose and collected (prints Collected stage1 data)
    collect_data(stage_names="stage1", verbose=False)
    captured = capsys.readouterr()
    assert "Collected stage1 data" in captured.out

    # 5. Test stage_name not in stages (continue)
    collect_data(stage_names=["nonexistent_stage"])
    
    # 6. Test spec/loader is None mock path
    with patch("importlib.util.spec_from_file_location", return_value=None):
        collect_data(stage_names=["stage1"])


def test_data_manager_operations(sandbox, env_dir):
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
    
    entries = list(dm)
    assert len(entries) == 3
    assert entries[0]["x"] == 5
    assert entries[0]["y"] == 10.0
    
    match_run = dm.get_run(x=10)
    assert match_run["y"] == 20.0
    
    splits_enum = list(dm.split("x", enum=True))
    assert len(splits_enum) == 3
    assert splits_enum[0][0] == 0
    assert splits_enum[0][1] == 5
    
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
        dm == ("invalid_type", 5)
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
        
    collect_data(stage_names=["stage1"])
    
    dm_path = os.path.join("data", "stage1.dm")
    assert os.path.isfile(dm_path)
    
    dm = Data_Manager(dm_path)
    assert len(dm) == 1
    assert list(dm["metric1"]) == [42.0]
    assert list(dm["x"]) == [5]
