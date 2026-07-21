import os
import json
import pytest
import pickle
from snap_workflow.core.params.system_params import System_Params

def test_system_params_dir_loading(sandbox):
    # 1. Create a mock parameters directory
    param_dir = "mock_params"
    os.makedirs(param_dir, exist_ok=True)
    
    # Write json files
    with open(os.path.join(param_dir, "variables.json"), "w") as f:
        json.dump({"x": 10, "y": 20}, f)
        
    with open(os.path.join(param_dir, "stage1.json"), "w") as f:
        # stage1 overrides a stage key
        json.dump({
            "stage1": {
                "val": "!vi_x", # reference x, cast as integer
                "negative_val": "!vn_y", # reference y, cast as negative float
                "float_val": "!vf_y" # reference y, cast as float
            }
        }, f)
        
    with open(os.path.join(param_dir, "stage2.json"), "w") as f:
        json.dump({
            "stage2": {
                "math_val": "!m_x + 5" # math parsing
            },
            "run": {
                "var1": {"var_path": ["stage1", "stage1", "val"], "encode": "int"}
            }
        }, f)
        
    # Load parameters
    sp = System_Params(param_dir, stages=["stage1", "stage2"], variables={"x": 10, "y": 20})
    
    # Assert values parsed by directives
    assert sp["stage1", "stage1", "val"] == 10
    assert sp["stage1", "stage1", "negative_val"] == -20.0
    assert sp["stage1", "stage1", "float_val"] == 20.0
    assert sp["stage2", "stage2", "math_val"] == 15
    assert "variables" in sp
    
    # Test __setitem__ / __getitem__ / __contains__
    sp["stage1", "custom_key"] = "hello"
    assert sp["stage1", "custom_key"] == "hello"
    assert "stage1" in sp
    
    # Test set_stages updating values
    sp.set_stages(["stage2"])
    
    # Test run dict getters and decoders
    run_dict = sp.get_run_dict(["var1"])
    assert run_dict == {"var1": 10}
    
    decoded = sp.decode_run_dict({"var1": "100"})
    assert decoded == {"var1": 100}

def test_directive_exceptions(sandbox):
    param_dir = "mock_params"
    os.makedirs(param_dir, exist_ok=True)
    with open(os.path.join(param_dir, "variables.json"), "w") as f:
        json.dump({"x": 10}, f)
        
    sp = System_Params(param_dir)
    
    # Math conflict: math must be the only directive
    with pytest.raises(Exception, match="Conflicting directives: math"):
        sp._parse_directives(["!", "m", "f"], "5")
        
    # Float/Int conflict
    with pytest.raises(Exception, match="Conflicting directives: float and int"):
        sp._parse_directives(["!", "f", "i"], "5")
        
    # Missing variable reference returns raw string
    raw_str = sp._parse_directives(["!", "v"], "nonexistent_var")
    assert raw_str == "!!v_nonexistent_var"

def test_update_parameters(sandbox):
    param_dir = "mock_params"
    os.makedirs(param_dir, exist_ok=True)
    with open(os.path.join(param_dir, "variables.json"), "w") as f:
        json.dump({"x": 10}, f)
    with open(os.path.join(param_dir, "stage1.json"), "w") as f:
        json.dump({
            "stage1": {"val": 5},
            "update": [
                {"update_value": "3.14", "encode": "float", "update_path": ["stage1", "stage1", "val"]}
            ]
        }, f)
        
    sp = System_Params(param_dir, stages=["stage1"])
    sp.update()
    assert sp["stage1", "stage1", "val"] == 3.14
    
    # Test dictionary-based updates
    with open(os.path.join(param_dir, "stage1.json"), "w") as f:
        json.dump({
            "stage1": {"val": 5},
            "update": {
                "up1": {"update_value": "4.2", "encode": "float", "update_path": ["stage1", "stage1", "val"]}
            }
        }, f)
    sp = System_Params(param_dir, stages=["stage1"])
    sp.update()
    assert sp["stage1", "stage1", "val"] == 4.2

def test_pickling_parameters(sandbox):
    param_dir = "mock_params"
    os.makedirs(param_dir, exist_ok=True)
    with open(os.path.join(param_dir, "variables.json"), "w") as f:
        json.dump({"x": 10}, f)
        
    sp = System_Params(param_dir)
    
    # Test single key access/setting
    sp["top_key"] = 500
    assert sp["top_key"] == 500
    
    # Test pickle auto-extension (without .pkl extension)
    pkl_file = "test_params_no_ext"
    sp.pickle(pkl_file)
    assert os.path.isfile(pkl_file + ".pkl")
    
    # Load pickle auto-extension
    sp_loaded = System_Params(pkl_file + ".pkl")
    assert sp_loaded["variables", "x"] == 10

def test_invalid_param_path():
    with pytest.raises(Exception, match="neither a file nor directory"):
        System_Params("invalid_path_to_params")

def test_system_params_corner_cases(sandbox):
    param_dir = "mock_params"
    os.makedirs(param_dir, exist_ok=True)
    
    # 1. Test missing variables key load
    with open(os.path.join(param_dir, "stage1.json"), "w") as f:
        json.dump({"stage1": {"val": ""}}, f) # empty string check
    sp = System_Params(param_dir)
    assert not hasattr(sp, "variables") or len(sp.variables) == 0
    
    # 2. Test empty parts string directives
    with open(os.path.join(param_dir, "stage1.json"), "w") as f:
        json.dump({"stage1": {"val": "!_empty_part"}}, f)
    sp = System_Params(param_dir)
    
    # 3. Test unexpected collection exception in find_directives
    with pytest.raises(Exception, match="Unexpected collection of items"):
        sp._find_directives({1, 2, 3})
        
    # 4. Test JSON parsing failure build error
    with open(os.path.join(param_dir, "bad.json"), "w") as f:
        f.write("invalid json contents")
    with pytest.raises(Exception, match="Failed parsing bad.json"):
        System_Params(param_dir)
        
    # 5. Test set_stages single stage string conversion & nonexistent stage continue
    os.remove(os.path.join(param_dir, "bad.json"))
    sp = System_Params(param_dir)
    sp.set_stages("stage1")
    sp.set_stages("nonexistent_stage")
    
    # 6. Test set_directives method
    sp.set_directives()
    
    # 7. Test string starting with underscore split logic in find_directives (line 98 continue)
    with open(os.path.join(param_dir, "stage1.json"), "w") as f:
        json.dump({"stage1": {"val": "_starts_with_underscore"}}, f)
    sp = System_Params(param_dir)
    assert sp["stage1", "stage1", "val"] == "_starts_with_underscore"

def test_system_params_direct_pickle_no_ext(sandbox):
    param_dir = "mock_params"
    os.makedirs(param_dir, exist_ok=True)
    with open(os.path.join(param_dir, "variables.json"), "w") as f:
        json.dump({"x": 10}, f)
    sp = System_Params(param_dir)
    sp.pickle("test_direct_no_ext")
    
    # Call _load_pickle directly with a path lacking .pkl to hit line 18
    sp2 = System_Params("test_direct_no_ext.pkl")
    sp2._load_pickle("test_direct_no_ext")

def test_system_params_yaml_cases(sandbox):
    import sys
    from unittest.mock import patch
    param_dir = "mock_params"
    os.makedirs(param_dir, exist_ok=True)
    
    # 1. Test successful YAML build
    with open(os.path.join(param_dir, "stage_yaml.yaml"), "w") as f:
        f.write("stage_yaml:\n  val: 200\n")
        
    sp = System_Params(param_dir)
    assert sp["stage_yaml", "stage_yaml", "val"] == 200
    
    # 2. Test YAML parsing error
    with open(os.path.join(param_dir, "bad.yaml"), "w") as f:
        f.write("stage_yaml:\n  val: [invalid yaml")
    with pytest.raises(Exception, match="Failed parsing bad.yaml"):
        System_Params(param_dir)
        
    os.remove(os.path.join(param_dir, "bad.yaml"))
    
    # 3. Test pyyaml missing ImportError
    with patch.dict(sys.modules, {"yaml": None}):
        with pytest.raises(ImportError, match="The 'pyyaml' package is required"):
            System_Params(param_dir)

def test_system_params_recursive_and_missing_keys(sandbox):
    param_dir = "mock_params"
    os.makedirs(param_dir, exist_ok=True)
    
    # Nested directory parameter building
    subdir = os.path.join(param_dir, "subdir")
    os.makedirs(subdir, exist_ok=True)
    with open(os.path.join(subdir, "nested.json"), "w") as f:
        json.dump({"nested": {"val": 300}}, f)
        
    sp = System_Params(param_dir)
    assert sp["subdir", "nested", "nested", "val"] == 300
    
    # update_variables when variables key is empty/missing
    assert len(sp.params["variables"]) == 0
    del sp.params["variables"]
    sp.update_variables({"x": 100})
    assert sp.params["variables"]["x"] == 100
    
    # update() when update key is missing
    sp.update() # returns early cleanly


