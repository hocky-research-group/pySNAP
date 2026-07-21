import os
import json
import numpy as np
import pytest

from snap_workflow.core.data import Data_Manager
from snap_workflow.core.params.system_params import System_Params

def test_add_and_indexing():
    dm = Data_Manager()
    # Add some records
    dm._add({"x": 1, "y": 2}, {"loss": 0.5, "accuracy": 0.9})
    dm._add({"x": 2, "y": 4}, {"loss": 0.2, "accuracy": 0.95})
    
    assert len(dm) == 2
    assert list(dm.var_names) == ["x", "y"]
    assert list(dm.data_names) == ["accuracy", "loss"]
    
    # Test getting variables as numpy arrays
    assert (dm["x"] == np.array([1, 2])).all()
    assert (dm["loss"] == np.array([0.5, 0.2])).all()
    
    # Test indexing with comparison operator (equal)
    filtered = dm == ("x", 2)
    assert len(filtered) == 1
    assert filtered["y"][0] == 4

def test_comparison_filters():
    dm = Data_Manager()
    dm._add({"x": 5}, {"value": 10})
    dm._add({"x": 10}, {"value": 20})
    dm._add({"x": 15}, {"value": 30})
    
    # Test GT (>)
    gt = dm > ("x", 5)
    assert len(gt) == 2
    assert (gt["value"] == np.array([20, 30])).all()
    
    # Test LT (<)
    lt = dm < ("x", 15)
    assert len(lt) == 2
    
    # Test NEQ (!=)
    neq = dm != ("x", 10)
    assert len(neq) == 2
    assert (neq["x"] == np.array([5, 15])).all()

def test_json_and_yaml_parsing(sandbox):
    # Create a parameters directory
    os.makedirs(os.path.join(sandbox, "params"), exist_ok=True)
    
    # Write variables.json
    var_data = {
        "pi": 3.1415
    }
    with open(os.path.join(sandbox, "params", "variables.json"), "w") as f:
        json.dump(var_data, f)

    # Write config.json
    config_json_data = {
        "two_pi": "!m_2*pi"
    }
    with open(os.path.join(sandbox, "params", "json_config.json"), "w") as f:
        json.dump(config_json_data, f)
        
    # Write config.yaml
    try:
        import yaml
        yaml_installed = True
    except ImportError:
        yaml_installed = False
        
    if yaml_installed:
        config_data = """
        sim:
          steps: "!i_1000.5"
          factor: "!f_1.5"
          name: "!str_test_combo"
        """
        with open(os.path.join(sandbox, "params", "yaml_config.yaml"), "w") as f:
            f.write(config_data)
            
    # Load System_Params
    params = System_Params(os.path.join(sandbox, "params"), variables={"pi": 3.1415})
    
    # Test parsing variables and directives
    assert abs(params["variables"]["pi"] - 3.1415) < 1e-6
    assert abs(params["json_config"]["two_pi"] - 6.283) < 1e-6
    
    if yaml_installed:
        assert params["yaml_config"]["sim"]["steps"] == 1000
        assert abs(params["yaml_config"]["sim"]["factor"] - 1.5) < 1e-6
        assert params["yaml_config"]["sim"]["name"] == "testcombo"
