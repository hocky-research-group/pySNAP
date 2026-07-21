import os
import json
import pytest
import time
from unittest.mock import patch
from snap_workflow.core.workflow import initialize
from snap_workflow.core.stages import add_stage
from snap_workflow.core.variables import add_variable
from snap_workflow.core.sweeps import add_sweep
from snap_workflow.core import spoints
from snap_workflow.core import status

def test_spoint_still_defined(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    
    # 1. Test spoint still defined
    spoint_dict = {"x": 5}
    # It is defined in sweep1
    assert spoint_still_defined_wrapper("sweep2", "stage1", spoint_dict) is True

    # Call with a variable value that is not in any other sweeps
    assert spoint_still_defined_wrapper("sweep1", "stage1", {"x": 99}) is False

def spoint_still_defined_wrapper(sname, stage_name, spoint_dict):
    return spoints.spoint_still_defined(sname, stage_name, spoint_dict)

def test_spoint_manager_lifecycle(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    
    spoint_path = os.path.join("stage1", "spoints", "x_5")
    os.makedirs(os.path.join(spoint_path, ".spoint_info"), exist_ok=True)
    with open(os.path.join(spoint_path, ".spoint_info", "status"), "w") as f:
        f.write("initialized")
    with open(os.path.join(spoint_path, ".spoint_info", "time"), "w") as f:
        json.dump([], f)
    with open(os.path.join(spoint_path, ".spoint_info", "progress"), "w") as f:
        f.write("None")
        
    orig_cwd = os.getcwd()
    os.chdir(spoint_path)
    try:
        # A. Normal complete run
        stop_called = False
        def my_stop():
            nonlocal stop_called
            stop_called = True
            
        with spoints.SPoint_Manager(stop_func=my_stop) as sm:
            assert status.load_status() == "running"
            sm.set_progress("step1")
            assert sm.check_progress("step1")
            assert sm.check_progress(None) is False
            
        assert status.load_status() == "complete"
        assert not stop_called

        # B. Interrupted run (KeyboardInterrupt)
        with pytest.raises(KeyboardInterrupt):
            with spoints.SPoint_Manager(stop_func=my_stop) as sm:
                raise KeyboardInterrupt
                
        assert status.load_status() == "incomplete"
        assert stop_called
        
        # C. Error run (Exception)
        stop_called = False
        with pytest.raises(ValueError):
            with spoints.SPoint_Manager(stop_func=my_stop) as sm:
                raise ValueError("Dummy")
                
        assert status.load_status() == "error"
        assert stop_called
        
        # C2. Error run without stop_func (covers line 430 return)
        with pytest.raises(ValueError):
            with spoints.SPoint_Manager(stop_func=None) as sm:
                raise ValueError("Dummy")
        
        # D. stop_func/save_func raises error handling
        def bad_save():
            raise RuntimeError("Bad save")
        with pytest.raises(ValueError):
            with spoints.SPoint_Manager(save_func=bad_save) as sm:
                raise ValueError("Dummy")
        assert status.load_status() == "error"

        with pytest.raises(ValueError):
            with spoints.SPoint_Manager(stop_func=bad_save) as sm:
                raise ValueError("Dummy")
        assert status.load_status() == "error"
        
        # E. check_progress helper
        with spoints.SPoint_Manager() as sm:
            assert sm.check_progress("step2") is False
            sm.set_save_func(my_stop)
            assert sm.save_func == my_stop
            assert sm.stop_func == my_stop
            
            # test legacy setter/getter compatibility
            sm.set_stop_func(my_stop)
            assert sm.stop_func == my_stop
            assert sm.save_func == my_stop
            
            # F. load_params and track_nvidia
            with patch("snap_workflow.core.params.load_params", return_value={"param": 1}):
                assert sm.load_params() == {"param": 1}
            with pytest.raises(NotImplementedError):
                sm._track_nvidia()
    finally:
        os.chdir(orig_cwd)

def test_spoint_string_and_dict_helpers():
    # Empty get_spoint_string
    assert spoints.get_spoint_string({}) == "."
    
    # Parse spoint string '.'
    assert spoints.parse_spoint_string(".") == {}
    
    # Parse standard string
    assert spoints.parse_spoint_string("var1_val1_var2_val2") == {"var1": "val1", "var2": "val2"}
    
    # create_spoint_dict with None
    assert spoints.create_spoint_dict(["var1"], None) == {}

def test_load_spoint(sandbox, env_dir):
    initialize(env_dir)
    # create folders
    os.makedirs(".spoint_info", exist_ok=True)
    with open(".spoint_info/var.dat", "w") as f:
        f.write(".")
    assert spoints.load_spoint(".") == {}

def test_spoint_still_defined_mismatches(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    
    # sweep1 defines x=[5]
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    # sweep2 defines x=[6] but does not include stage1
    add_sweep("sweep2", include_stages=[], variable_values={"x": [6]})
    # sweep3 defines x=[7] and includes stage1, but value is 7
    add_sweep("sweep3", include_stages=["stage1"], variable_values={"x": [7]})
    
    # x=5 is defined in sweep1
    assert spoints.spoint_still_defined("sweep2", "stage1", {"x": 5}) is True
    # x=9 is not defined anywhere
    assert spoints.spoint_still_defined("sweep1", "stage1", {"x": 9}) is False

def test_iter_spoints_mismatches(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    # sweep1 has stage1, but sweep2 does not have stage1
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    add_sweep("sweep2", include_stages=[], variable_values={"x": [5]})
    
    results = list(spoints.iter_spoints(sweep_names="all", stage_names="stage1"))
    # Only sweep1 should yield stage1
    assert len(results) == 1
    assert results[0][0] == "sweep1"

def test_link_dependent_combo(sandbox, env_dir):
    initialize(env_dir)
    # Stage variables: parent has x, y. children have x (conv_vars y) or x, y (no conv_vars).
    add_stage("stage_parent", sbatch_details=None, stage_variables=["x", "y"], stage_dependencies=[])
    add_stage("stage_child", sbatch_details=None, stage_variables=["x"], stage_dependencies=["stage_parent"])
    add_stage("stage_child_no_conv", sbatch_details=None, stage_variables=["x", "y"], stage_dependencies=["stage_parent"])
    
    add_variable("x", ["int"], add_to_stages=["stage_parent", "stage_child", "stage_child_no_conv"], default_val=5)
    add_variable("y", ["int"], add_to_stages=["stage_parent", "stage_child_no_conv"], default_val=10)
    add_sweep("sweep1", include_stages=["stage_parent", "stage_child", "stage_child_no_conv"], variable_values={"x": [5], "y": [10]})
    
    # 1. Test non-convergent (len(conv_vars) == 0): child_no_conv depends on parent
    spoint_path_no_conv = spoints.get_spoint_path("stage_child_no_conv", {"x": 5, "y": 10})
    os.makedirs(spoint_path_no_conv, exist_ok=True)
    dep_info_no_conv = spoints.get_dependent_spoint_info("stage_child_no_conv", "sweep1", {"x": 5, "y": 10})
    spoints.link_dependent_combo("stage_child_no_conv", {"x": 5, "y": 10}, dep_info_no_conv)
    
    # 2. Test convergent (len(conv_vars) != 0) with existing directory to clear via shutil.rmtree
    spoint_path_conv = spoints.get_spoint_path("stage_child", {"x": 5})
    os.makedirs(spoint_path_conv, exist_ok=True)
    # create existing directory to force line 391 shutil.rmtree
    os.makedirs(os.path.join(spoint_path_conv, "stage_parent"), exist_ok=True)
    
    dep_info_conv = spoints.get_dependent_spoint_info("stage_child", "sweep1", {"x": 5})
    spoints.link_dependent_combo("stage_child", {"x": 5}, dep_info_conv)
    assert os.path.isdir(os.path.join(spoint_path_conv, "stage_parent"))

def test_submit_spoints_logic(sandbox, env_dir, capsys):
    initialize(env_dir)
    # Stage with sbatch
    sbatch_details = {
        "num_jobs": 1,
        "multi_submission": True,
        "partition": "test_part",
        "--array": "1-2"
    }
    add_stage("stage_sbatch", sbatch_details=sbatch_details, stage_variables=["x"], stage_dependencies=[])
    # Stage without sbatch (local execution fallback)
    add_stage("stage_local", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    
    add_variable("x", ["int"], add_to_stages=["stage_sbatch", "stage_local"], default_val=5)
    add_sweep("sweep1", include_stages=["stage_sbatch", "stage_local"], variable_values={"x": [5, 6]})
    
    # Write configured resources to avoid validation errors
    os.makedirs("stage_sbatch", exist_ok=True)
    os.makedirs("stage_local", exist_ok=True)
    with open("stage_sbatch/env.json", "w") as f:
        json.dump({"resources": {"cpus": 1, "gpus": 0, "mem": "1G"}}, f)
    with open("stage_local/env.json", "w") as f:
        json.dump({"resources": {"cpus": 1, "gpus": 0, "mem": "1G"}}, f)
        
    # 1. Custom sbatch load warnings (invalid JSON in env.json)
    with open("stage_sbatch/env.json", "w") as f:
        f.write("invalid json")
    
    # Verify warning is caught and printed
    details = spoints.get_submission_details("stage_sbatch", {"sbatch_details": sbatch_details})
    captured = capsys.readouterr()
    assert "Warning: Failed to load" in captured.out
    
    # 2. Custom sbatch successful parsing
    with open("stage_sbatch/env.json", "w") as f:
        json.dump({"resources": {"cpus": 1, "gpus": 0, "mem": "1G"}, "sbatch": {"partition": "custom_part", "n": "4"}}, f)
    details2 = spoints.get_submission_details("stage_sbatch", {"sbatch_details": sbatch_details})
    assert details2["sbatch_flags"]["--partition"] == "custom_part"
    assert details2["sbatch_flags"]["-n"] == "4"
    
    # 3. submit_spoints with no_sbatch=True (forces execute_spoint path)
    # Create the spoints for all swept combinations
    spoints.create_spoint("stage_local", {"x": 5}, clear=True)
    spoints.create_spoint("stage_local", {"x": 6}, clear=True)
    spoints.create_spoint("stage_sbatch", {"x": 5}, clear=True)
    spoints.create_spoint("stage_sbatch", {"x": 6}, clear=True)
    
    with patch("subprocess.run") as mock_run:
        # Success path (returncode = 0)
        mock_run.return_value.returncode = 0
        spoints.submit_spoints(sweep_names="sweep1", stage_names="stage_local", no_sbatch=True)
        assert status.load_status(spoints.get_spoint_path("stage_local", {"x": 5})) == "complete"
        assert status.load_status(spoints.get_spoint_path("stage_local", {"x": 6})) == "complete"
        
        # Failure path (returncode = 1)
        status.write_status("initialized", spoints.get_spoint_path("stage_local", {"x": 5}))
        status.write_status("initialized", spoints.get_spoint_path("stage_local", {"x": 6}))
        mock_run.return_value.returncode = 1
        spoints.submit_spoints(sweep_names="sweep1", stage_names="stage_local", no_sbatch=True)
        assert status.load_status(spoints.get_spoint_path("stage_local", {"x": 5})) == "error"
        assert status.load_status(spoints.get_spoint_path("stage_local", {"x": 6})) == "error"

    # 4. submit_spoints parameters loading exception warning (lines 157-164)
    # Status is initialized, but if params.set_params raises exception:
    status.write_status("initialized", spoints.get_spoint_path("stage_sbatch", {"x": 5}))
    status.write_status("initialized", spoints.get_spoint_path("stage_sbatch", {"x": 6}))
    with patch("snap_workflow.core.params.set_params", side_effect=ValueError("Test Param Error")):
        spoints.submit_spoints(sweep_names="sweep1", stage_names="stage_sbatch")
        captured = capsys.readouterr()
        assert "Cannot submit spoints for stage stage_sbatch" in captured.out

    # 5. submit_spoints sbatch queue submissions (success and failure returncodes)
    status.write_status("initialized", spoints.get_spoint_path("stage_sbatch", {"x": 5}))
    status.write_status("initialized", spoints.get_spoint_path("stage_sbatch", {"x": 6}))
    with patch("subprocess.run") as mock_run:
        # Failure returncode = 1
        mock_run.return_value.returncode = 1
        spoints.submit_spoints(sweep_names="sweep1", stage_names="stage_sbatch", num_submits=lambda: 2)
        assert status.load_status(spoints.get_spoint_path("stage_sbatch", {"x": 5})) == "initialized"
        
        # Success returncode = 0
        mock_run.return_value.returncode = 0
        spoints.submit_spoints(sweep_names="sweep1", stage_names="stage_sbatch", num_submits=2)
        assert status.load_status(spoints.get_spoint_path("stage_sbatch", {"x": 5})) == "submitted"

    # 6. Default parameters submit_spoints() call
    with patch("subprocess.run"):
        spoints.submit_spoints()
        
    # 7. test_submit=True and no num_submits (pops array option)
    status.write_status("initialized", spoints.get_spoint_path("stage_sbatch", {"x": 5}))
    # Ensure --array is in sbatch_flags to test pop array path (lines 295-296)
    details2["sbatch_flags"]["--array"] = "1-2"
    with patch("subprocess.run"):
        spoints.submit_spoints(sweep_names="sweep1", stage_names="stage_sbatch", test_submit=True, num_submits=None)

def test_check_submittable_dependency_checks(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage_parent", sbatch_details=None, stage_variables=["x", "y"], stage_dependencies=[])
    # child depends on parent, has same variables (no conv_vars)
    add_stage("stage_child_no_conv", sbatch_details=None, stage_variables=["x", "y"], stage_dependencies=["stage_parent"])
    # child depends on parent, has fewer variables (conv_vars present)
    add_stage("stage_child_conv", sbatch_details=None, stage_variables=["x"], stage_dependencies=["stage_parent"])
    
    add_variable("x", ["int"], add_to_stages=["stage_parent", "stage_child_no_conv", "stage_child_conv"], default_val=5)
    add_variable("y", ["int"], add_to_stages=["stage_parent", "stage_child_no_conv"], default_val=10)
    add_sweep("sweep1", include_stages=["stage_parent", "stage_child_no_conv", "stage_child_conv"], variable_values={"x": [5], "y": [10]})
    
    # Write configured resources to avoid validation errors
    with open("stage_parent/env.json", "w") as f:
        json.dump({"resources": {"cpus": 1, "gpus": 0, "mem": "1G"}}, f)
    with open("stage_child_no_conv/env.json", "w") as f:
        json.dump({"resources": {"cpus": 1, "gpus": 0, "mem": "1G"}}, f)
    with open("stage_child_conv/env.json", "w") as f:
        json.dump({"resources": {"cpus": 1, "gpus": 0, "mem": "1G"}}, f)
        
    spoints.create_spoint("stage_parent", {"x": 5, "y": 10}, clear=True)
    spoints.create_spoint("stage_child_no_conv", {"x": 5, "y": 10}, clear=True)
    spoints.create_spoint("stage_child_conv", {"x": 5}, clear=True)
    
    # Link dependencies to establish folders/symlinks
    dep_info_no_conv = spoints.get_dependent_spoint_info("stage_child_no_conv", "sweep1", {"x": 5, "y": 10})
    spoints.link_dependent_combo("stage_child_no_conv", {"x": 5, "y": 10}, dep_info_no_conv)
    
    dep_info_conv = spoints.get_dependent_spoint_info("stage_child_conv", "sweep1", {"x": 5})
    spoints.link_dependent_combo("stage_child_conv", {"x": 5}, dep_info_conv)

    # Verify submittable of child is False because parent is initialized, not complete
    status.write_status("initialized", spoints.get_spoint_path("stage_parent", {"x": 5, "y": 10}))
    
    assert spoints.check_submittable("sweep1", "stage_child_no_conv", {"x": 5, "y": 10}) is False
    assert spoints.check_submittable("sweep1", "stage_child_conv", {"x": 5}) is False
    
    # Mark parent complete, verify submittable becomes True
    status.write_status("complete", spoints.get_spoint_path("stage_parent", {"x": 5, "y": 10}))
    assert spoints.check_submittable("sweep1", "stage_child_no_conv", {"x": 5, "y": 10}) is True
    assert spoints.check_submittable("sweep1", "stage_child_conv", {"x": 5}) is True
