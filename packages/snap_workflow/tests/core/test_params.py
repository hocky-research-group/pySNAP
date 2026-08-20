import os
import sys
import json
import pickle
import warnings
import pytest
from unittest.mock import patch

from snap_workflow.core.workflow import initialize
from snap_workflow.core.domain import stages, sweeps, variables, spoints, params, status
from snap_workflow.core.params.system_params import System_Params
from snap_workflow.core.params.tools import dict_defines, decode, get_options, recursive_print
from snap_workflow.cli.verbs import main_reset
from snap_workflow.cli.params import main_convert

# --- Params Tools Tests ---

def test_dict_defines():
    assert dict_defines({"a": 1}, "a") is True
    assert dict_defines({"a": None}, "a") is False
    assert dict_defines({"b": 1}, "a") is False

def test_decode_basic():
    assert decode("5", "int") == 5
    assert decode("3.14", "float") == 3.14
    assert decode("hello", "direct") == "hello"
    assert decode(5, "negative") == -5

def test_decode_list_and_tuple():
    assert decode([1, 2], "tuple") == (1, 2)
    assert decode(["5", "3.14"], ["int", "float"]) == [5, 3.14]

def test_decode_dict():
    val = {"a": "5", "b": "direct_val"}
    enc = {"a": "int"}
    assert decode(val, enc) == {"a": 5, "b": "direct_val"}

def test_decode_nested_encodings():
    assert decode("5", ["int", "negative"]) == -5

def test_decode_json_file(sandbox):
    json_path = "test.json"
    with open(json_path, "w") as f:
        json.dump({"x": 10}, f)
    
    assert decode(json_path, "json") == {"x": 10}

def test_decode_invalid():
    with pytest.raises(ValueError, match="Can't decode encoding type"):
        decode(5, "unsupported_encoding")

def test_get_options():
    assert get_options({}) == {}
    info = {
        "options": {"val": "10"},
        "options_encoding": {"val": "int"}
    }
    assert get_options(info) == {"val": 10}

def test_recursive_print():
    data = {
        "stage1": {
            "substage": {
                "leaf": 1
            }
        }
    }
    with patch('sys.stdout') as mock_stdout:
        recursive_print(data)
        assert mock_stdout.write.called

# --- System Params Tests ---

@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_system_params_dir_loading(sandbox):
    param_dir = "mock_params"
    os.makedirs(param_dir, exist_ok=True)
    
    with open(os.path.join(param_dir, "variables.json"), "w") as f:
        json.dump({"x": 10, "y": 20}, f)
        
    with open(os.path.join(param_dir, "stage1.json"), "w") as f:
        json.dump({
            "stage1": {
                "val": "!vi_x",
                "negative_val": "!vn_y",
                "float_val": "!vf_y"
            }
        }, f)
        
    with open(os.path.join(param_dir, "stage2.json"), "w") as f:
        json.dump({
            "stage2": {
                "math_val": "!m_x + 5"
            },
            "run": {
                "var1": {"var_path": ["stage1", "stage1", "val"], "encode": "int"}
            }
        }, f)
        
    sp = System_Params(param_dir, stages=["stage1", "stage2"], variables={"x": 10, "y": 20})
    
    assert sp["stage1", "stage1", "val"] == 10
    assert sp["stage1", "stage1", "negative_val"] == -20.0
    assert sp["stage1", "stage1", "float_val"] == 20.0
    assert sp["stage2", "stage2", "math_val"] == 15
    assert "variables" in sp
    
    sp["stage1", "custom_key"] = "hello"
    assert sp["stage1", "custom_key"] == "hello"
    assert "stage1" in sp
    
    sp.set_stages(["stage2"])
    
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
    
    with pytest.raises(Exception, match="Conflicting directives: math"):
        sp._parse_directives(["!", "m", "f"], "5")
        
    with pytest.raises(Exception, match="Conflicting directives: float and int"):
        sp._parse_directives(["!", "f", "i"], "5")
        
    raw_str = sp._parse_directives(["!", "v"], "nonexistent_var")
    assert raw_str == "!!v_nonexistent_var"

@pytest.mark.filterwarnings("ignore::DeprecationWarning")
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
    
    sp["top_key"] = 500
    assert sp["top_key"] == 500
    
    pkl_file = "test_params_no_ext"
    sp.pickle(pkl_file)
    assert os.path.isfile(pkl_file + ".pkl")
    
    sp_loaded = System_Params(pkl_file + ".pkl")
    assert sp_loaded["variables", "x"] == 10

def test_invalid_param_path():
    sp = System_Params("invalid_path_to_params")
    assert sp.params == {}

@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_system_params_corner_cases(sandbox):
    param_dir = "mock_params"
    os.makedirs(param_dir, exist_ok=True)
    
    with open(os.path.join(param_dir, "stage1.json"), "w") as f:
        json.dump({"stage1": {"val": ""}}, f)
    sp = System_Params(param_dir)
    assert not hasattr(sp, "variables") or len(sp.variables) == 0
    
    with open(os.path.join(param_dir, "stage1.json"), "w") as f:
        json.dump({"stage1": {"val": "!_empty_part"}}, f)
    sp = System_Params(param_dir)
    
    with pytest.raises(Exception, match="Unexpected collection of items"):
        sp._find_directives({1, 2, 3})
        
    with open(os.path.join(param_dir, "bad.json"), "w") as f:
        f.write("invalid json contents")
    with pytest.raises(Exception, match="Failed parsing bad.json"):
        System_Params(param_dir)
        
    os.remove(os.path.join(param_dir, "bad.json"))
    sp = System_Params(param_dir)
    sp.set_stages("stage1")
    sp.set_stages("nonexistent_stage")
    
    sp.set_directives()
    
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
    
    sp2 = System_Params("test_direct_no_ext.pkl")
    sp2._load_pickle("test_direct_no_ext")

def test_system_params_yaml_cases(sandbox):
    param_dir = "mock_params"
    os.makedirs(param_dir, exist_ok=True)
    
    with open(os.path.join(param_dir, "stage_yaml.yaml"), "w") as f:
        f.write("stage_yaml:\n  val: 200\n")
        
    sp = System_Params(param_dir)
    assert sp["stage_yaml", "stage_yaml", "val"] == 200
    
    with open(os.path.join(param_dir, "bad.yaml"), "w") as f:
        f.write("stage_yaml:\n  val: [invalid yaml")
    with pytest.raises(Exception, match="Failed parsing bad.yaml"):
        System_Params(param_dir)
        
    os.remove(os.path.join(param_dir, "bad.yaml"))
    
    with patch.dict(sys.modules, {"yaml": None}):
        with pytest.raises(ImportError, match="The 'pyyaml' package is required"):
            System_Params(param_dir)

def test_system_params_recursive_and_missing_keys(sandbox):
    param_dir = "mock_params"
    os.makedirs(param_dir, exist_ok=True)
    
    subdir = os.path.join(param_dir, "subdir")
    os.makedirs(subdir, exist_ok=True)
    with open(os.path.join(subdir, "nested.json"), "w") as f:
        json.dump({"nested": {"val": 300}}, f)
        
    sp = System_Params(param_dir)
    assert sp["subdir", "nested", "nested", "val"] == 300
    
    assert len(sp.params["variables"]) == 0
    del sp.params["variables"]
    sp.update_variables({"x": 100})
    assert sp.params["variables"]["x"] == 100
    
    sp.update()

def test_system_params_init_from_dict_and_list():
    data = {
        "box": {
            "shrink": {"method": "linear", "rate": 0.01},
        },
        "polymers": [
            {"type": "A", "length": 100},
        ],
    }

    sp = System_Params(data)
    assert id(sp.params) == id(data)

    assert isinstance(sp["box"], dict)
    assert isinstance(sp["box", "shrink"], dict)
    assert sp["box", "shrink", "method"] == "linear"

    shrink_sp = System_Params(sp["box", "shrink"])
    assert shrink_sp["method"] == "linear"
    assert id(shrink_sp.params) == id(data["box"]["shrink"])

def test_system_params_pop():
    data = {
        "box": {
            "shrink": {"method": "linear", "rate": 0.01},
            "status": "active",
        },
        "polymers": [
            {"type": "A", "length": 100},
            {"type": "B", "length": 50},
        ],
        "simple_key": 42,
    }

    sp = System_Params(data)

    shrink_dict = sp.pop("box", "shrink")
    assert isinstance(shrink_dict, dict)
    assert shrink_dict["method"] == "linear"
    assert "shrink" not in data["box"]
    assert "shrink" not in sp["box"]

    shrink_sp = System_Params(shrink_dict)
    assert shrink_sp["method"] == "linear"

    poly0 = sp.pop("polymers", 0)
    assert isinstance(poly0, dict)
    assert poly0["type"] == "A"
    assert len(data["polymers"]) == 1

    status_val = sp.pop(("box", "status"))
    assert status_val == "active"
    assert "status" not in data["box"]

    simple = sp.pop("simple_key")
    assert simple == 42
    assert "simple_key" not in sp

    fallback = sp.pop("nonexistent", default="fallback_val")
    assert fallback == "fallback_val"

    fallback_nested = sp.pop("box", "nonexistent", default=999)
    assert fallback_nested == 999

    with pytest.raises(KeyError):
        sp.pop("nonexistent_key")

def test_set_stages_deprecation_warning(sandbox):
    param_dir = "mock_params"
    os.makedirs(param_dir, exist_ok=True)
    with open(os.path.join(param_dir, "stage1.json"), "w") as f:
        json.dump({"stage1": {"val": 1}}, f)

    sp = System_Params(param_dir)
    with pytest.deprecated_call():
        sp.set_stages("stage1")

# --- Convert & Reset Params Tests ---

def test_params_hashing_and_drift_warning(sandbox):
    initialize(sandbox)

    with open("params/solver.json", "w") as f:
        json.dump({"tolerance": 1e-5}, f)

    stages.add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    variables.add_variable("x", ["int"], add_to_stages=["stage1"], default_val=10)
    sweeps.add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [10, 20]})

    sp_path = spoints.get_spoint_path("stage1", {"x": 10})
    params_obj = params.load_params(sp_path)

    assert hasattr(params_obj, "source_hash")
    assert params_obj.source_hash is not None

    with open("params/solver.json", "w") as f:
        json.dump({"tolerance": 1e-9}, f)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        params.load_params(sp_path)
        assert any("source hash mismatch" in str(item.message) for item in w)

def test_export_and_convert_params(sandbox):
    initialize(sandbox)

    with open("params/config.json", "w") as f:
        json.dump({"steps": 100}, f)

    stages.add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    variables.add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    sweeps.add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})

    sp_path = spoints.get_spoint_path("stage1", {"x": 5})

    params_obj = params.load_params(sp_path)
    json_path = params_obj.export_readable(os.path.join(sp_path, "params.json"), format="json")
    yaml_path = params_obj.export_readable(os.path.join(sp_path, "params.yaml"), format="yaml")

    assert os.path.isfile(json_path)
    assert os.path.isfile(yaml_path)

    with open(json_path, "r") as f:
        data = json.load(f)
        assert data["params"]["config"]["steps"] == 100
        assert data["variables"]["x"] == 5

    res = params.convert_params(sweep_name="sweep1", stage_name="stage1", format="json")
    assert len(res) == 1
    assert os.path.isfile(res[0])

def test_reset_spoint_cwd(sandbox):
    initialize(sandbox)

    stages.add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    variables.add_variable("x", ["int"], add_to_stages=["stage1"], default_val=10)
    sweeps.add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [10]})

    sp_path = spoints.get_spoint_path("stage1", {"x": 10})

    with pytest.raises(ValueError, match="is not an SPoint directory"):
        spoints.reset_spoint(sandbox)

    start_dir = os.getcwd()
    os.chdir(sp_path)
    try:
        with open("output.txt", "w") as f:
            f.write("simulation result")
        status.write_status("complete", ".")

        spoints.reset_spoint(".", hard=False)
        assert status.load_status(".") == "initialized"
        assert os.path.isfile("output.txt")

        spoints.reset_spoint(".", hard=True)
        assert status.load_status(".") == "initialized"
        assert not os.path.exists("output.txt")
        assert os.path.exists(".spoint_info/var.dat")
    finally:
        os.chdir(start_dir)

def test_reset_spoint_cli(sandbox):
    initialize(sandbox)

    stages.add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    variables.add_variable("x", ["int"], add_to_stages=["stage1"], default_val=15)
    sweeps.add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [15]})

    sp_path = spoints.get_spoint_path("stage1", {"x": 15})

    with pytest.raises(SystemExit) as exc_info:
        main_reset("workflow reset", ["spoint"])
    assert exc_info.value.code == 1

    start_dir = os.getcwd()
    os.chdir(sp_path)
    try:
        with open("result.dat", "w") as f:
            f.write("12345")

        main_reset("workflow reset", ["spoint"])
        assert status.load_status(".") == "initialized"
        assert os.path.isfile("result.dat")

        main_reset("workflow reset", ["spoint", "--hard", "--force"])
        assert status.load_status(".") == "initialized"
        assert not os.path.exists("result.dat")
    finally:
        os.chdir(start_dir)

def test_reset_spoint_relinks_dependencies(sandbox):
    initialize(sandbox)

    stages.add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    stages.add_stage("stage2", sbatch_details=None, stage_variables=["x"], stage_dependencies=["stage1"])
    variables.add_variable("x", ["int"], add_to_stages=["stage1", "stage2"], default_val=10)
    sweeps.add_sweep("sweep1", include_stages=["stage1", "stage2"], variable_values={"x": [10]})

    sp2_path = spoints.get_spoint_path("stage2", {"x": 10})
    start_dir = os.getcwd()
    os.chdir(sp2_path)
    try:
        dep_link = os.path.join(".", "stage1")
        assert os.path.exists(dep_link) or os.path.islink(dep_link)

        spoints.reset_spoint(".", hard=True)

        assert status.load_status(".") == "initialized"
        assert os.path.islink(dep_link) or os.path.exists(dep_link)

        main_convert("workflow convert", ["params", "--format", "json"])
        assert os.path.isfile("params.json")
    finally:
        os.chdir(start_dir)
