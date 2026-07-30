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

    # 7. Test collect module raising an exception
    with open(collect_path, "w") as f:
        f.write("def collect():\n    raise ValueError('runtime collect error')\n")
    collect_data(stage_names="stage1", verbose=True)
    captured = capsys.readouterr()
    assert "Failed to collect data" in captured.out
    assert "runtime collect error" in captured.out

def test_data_manager_class(sandbox, env_dir):
    initialize(env_dir)
    
    # 1. Data_Manager instantiation without file path
    dm = Data_Manager()
    assert dm.var_names is None
    assert len(dm.var_vals) == 0
    assert len(dm) == 0

    # 2. Add data points
    var_dict = {"x": 5}
    data_dict = {"loss": 0.1, "accuracy": 0.9}
    dm._add(var_dict, data_dict)
    assert len(dm) == 1
    assert dm.var_names == ["x"]
    assert dm.data_names == ["accuracy", "loss"] # sorted alphabetically

    # 3. Save / load pickle DM file
    dm.save("stage1_data") # appends .dm
    assert os.path.isfile("stage1_data.dm")

    # Move to data/ to test candidate lookup logic
    import shutil
    os.makedirs("data", exist_ok=True)
    shutil.move("stage1_data.dm", "data/stage1_data.dm")

    # Load file using path without .dm extension to test extension appending and candidate lookup fallback
    dm2 = Data_Manager("stage1_data")
    assert dm2.var_names == ["x"]
    assert dm2.data_names == ["accuracy", "loss"]

    # Load non-existent file triggers ValueError
    with pytest.raises(ValueError):
        Data_Manager("nonexistent_data")

    # Test candidate lookup Exception handler path
    with patch("snap_workflow.utils.path.get_root", side_effect=RuntimeError("no root")):
        with pytest.raises(ValueError):
            Data_Manager("nonexistent_data")

    # 4. Data Mismatches
    # Var mismatch - num variables mismatch
    with pytest.raises(Exception) as exc:
        dm._verify_variables({"x": 5, "y": 10})
    assert "Variable Mismatch" in str(exc.value)

    # Var mismatch - names mismatch
    with pytest.raises(Exception) as exc:
        dm._verify_variables({"y": 5})
    assert "Variable Mismatch" in str(exc.value)

    # Data mismatch - num data mismatch
    with pytest.raises(Exception) as exc:
        dm._verify_data({"loss": 0.1})
    assert "Data Mismatch" in str(exc.value)

    # Data mismatch - names mismatch
    with pytest.raises(Exception) as exc:
        dm._verify_data({"loss": 0.1, "val_loss": 0.2})
    assert "Data Mismatch" in str(exc.value)

    # Direct verification with None
    dm_empty = Data_Manager()
    dm_empty.num_vars = 1
    dm_empty._verify_variables({"x": 5})
    assert dm_empty.var_names == ["x"]
    
    dm_empty2 = Data_Manager()
    dm_empty2.num_data = 1
    dm_empty2._verify_data({"loss": 0.1})
    assert dm_empty2.data_names == ["loss"]

def test_data_manager_queries(sandbox, env_dir):
    dm = Data_Manager()
    dm._add({"x": 5, "y": 1}, {"loss": 0.5})
    dm._add({"x": 10, "y": 2}, {"loss": 0.2})
    dm._add({"x": 15, "y": 3}, {"loss": 0.1})

    # 1. Unique values
    assert np.array_equal(dm.unique("x"), np.array([5, 10, 15]))

    # 2. Get item string (returns numpy arrays)
    assert np.array_equal(dm["x"], np.array([5, 10, 15]))
    assert np.array_equal(dm["loss"], np.array([0.5, 0.2, 0.1]))
    with pytest.raises(ValueError):
        _ = dm["nonexistent_key"]

    # 3. Get run / get runs queries
    runs = dm.get_run(x=10)
    assert runs["loss"] == 0.2
    assert runs["y"] == 2
    
    # get_run returning list
    runs_list = dm.get_runs(x=20) # nonexistent, returns empty list
    assert runs_list == []

    # get_run with unknown query keys (should ignore/skip)
    runs_all = dm.get_run(unknown_key=10)
    assert len(runs_all) == 3

    # 4. Separate other checks
    assert dm._seperate_other(("x", 5)) == ("x", 5)
    with pytest.raises(Exception) as exc:
        dm._seperate_other("x")
    assert "Data_Manager can only be compared to tuple" in str(exc.value)
    
    with pytest.raises(Exception) as exc:
        dm._seperate_other((5, 10))
    assert "Data_Manager can only be compared to tuple" in str(exc.value)

    # 5. Operators logic
    dm_filter = dm > ("x", 8)
    assert len(dm_filter) == 2
    assert np.array_equal(dm_filter["x"], np.array([10, 15]))
    
    assert len(dm >= ("x", 10)) == 2
    assert len(dm < ("x", 10)) == 1
    assert len(dm <= ("x", 10)) == 2
    assert len(dm == ("x", 10)) == 1
    assert len(dm != ("x", 10)) == 2

    # Operator validation exceptions (len != 2)
    with pytest.raises(Exception) as exc:
        _ = dm > ("x",)
    assert "applied via comparison when comparing with iterables of length 2" in str(exc.value).lower()

    # 6. Separate split generators
    splits = list(dm.split("x", enum=True))
    assert len(splits) == 3
    assert splits[0][0] == 0
    assert splits[0][1] == 5
    assert len(splits[0][2]) == 1

    splits_no_enum = list(dm.split("x", enum=False))
    assert len(splits_no_enum) == 3
    assert splits_no_enum[0][0] == 5
    assert len(splits_no_enum[0][1]) == 1

    # 7. __getitem__ np.ndarray / tuple filters
    dm.np_updated = False
    arr_filter = np.array([True, False, True])
    filtered_dm = dm[arr_filter]
    assert len(filtered_dm) == 2
    assert np.array_equal(filtered_dm["x"], np.array([5, 15]))

    # Multiple conditions tuple filter
    multi_filter = (np.array([True, True, True]), np.array([True, False, True]))
    filtered_dm_multi = dm[multi_filter]
    assert len(filtered_dm_multi) == 2
    assert np.array_equal(filtered_dm_multi["x"], np.array([5, 15]))
    
    # 8. Empty args error
    with pytest.raises(Exception) as exc:
        _ = dm[()]
    assert "Cannot interpret nothing" in str(exc.value)

    # 9. Array filter length mismatch
    with pytest.raises(ValueError):
        _ = dm[np.array([True, False])]
        
    with pytest.raises(ValueError):
        dm._filter([np.array([True, False])])
        
    # Iteration loop cover
    items = list(dm)
    assert len(items) == 3
    assert items[0]["x"] == 5
