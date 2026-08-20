import os
import json
import pytest
import time
from unittest.mock import patch, MagicMock
from snap_workflow.core.workflow import initialize
from snap_workflow.core.domain.stages import add_stage
from snap_workflow.core.domain.variables import add_variable
from snap_workflow.core.domain.sweeps import add_sweep
from snap_workflow.core.domain import spoints
from snap_workflow.core.domain import status

def test_spoint_still_defined(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    
    spoint_dict = {"x": 5}
    assert spoint_still_defined_wrapper("sweep2", "stage1", spoint_dict) is True
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

        with pytest.raises(KeyboardInterrupt):
            with spoints.SPoint_Manager(stop_func=my_stop) as sm:
                raise KeyboardInterrupt
                
        assert status.load_status() == "incomplete"
        assert stop_called
        
        stop_called = False
        with pytest.raises(ValueError):
            with spoints.SPoint_Manager(stop_func=my_stop) as sm:
                raise ValueError("Dummy")
                
        assert status.load_status() == "error"
        assert stop_called
        
        with pytest.raises(ValueError):
            with spoints.SPoint_Manager(stop_func=None) as sm:
                raise ValueError("Dummy")
        
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
        
        with spoints.SPoint_Manager() as sm:
            assert sm.check_progress("step2") is False
            sm.set_save_func(my_stop)
            assert sm.save_func == my_stop
            assert sm.stop_func == my_stop
            
            sm.set_stop_func(my_stop)
            assert sm.stop_func == my_stop
            assert sm.save_func == my_stop
            
            with patch("snap_workflow.core.domain.spoints.params.load_params", return_value={"param": 1}):
                assert sm.load_params() == {"param": 1}
            with pytest.raises(NotImplementedError):
                sm._track_nvidia()
    finally:
        os.chdir(orig_cwd)

def test_spoint_manager_notify_server(sandbox, env_dir):
    initialize(env_dir)
    spoint_path = os.path.join("stage1", "spoints", "x_5")
    os.makedirs(os.path.join(spoint_path, ".spoint_info"), exist_ok=True)

    orig_cwd = os.getcwd()
    os.chdir(spoint_path)
    try:
        with patch("urllib.request.urlopen") as mock_urlopen, \
             patch.dict(os.environ, {"SERVER_TOKEN": "secret_token"}):
            with spoints.SPoint_Manager(report_to="http://localhost:8080"):
                pass
            assert mock_urlopen.called

        with patch("urllib.request.urlopen", side_effect=Exception("network error")), \
             patch("builtins.print") as mock_print:
            with spoints.SPoint_Manager(report_to="http://localhost:8080"):
                pass
            assert mock_print.called
    finally:
        os.chdir(orig_cwd)

def test_spoint_status_manager_set_status_exception_handling(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})

    mgr = spoints.SPointStatusManager()
    with patch("snap_workflow.core.params.params.set_spoint_params", side_effect=Exception("Params error")):
        mgr.set_status("sweep1", "stage1", {"x": 5}, "complete")
        assert status.load_status(spoints.get_spoint_path("stage1", {"x": 5})) == "complete"

def test_spoint_string_and_dict_helpers():
    assert spoints.get_spoint_string({}) == "."
    assert spoints.parse_spoint_string(".") == {}
    assert spoints.parse_spoint_string("var1_val1_var2_val2") == {"var1": "val1", "var2": "val2"}
    assert spoints.create_spoint_dict(["var1"], None) == {}

def test_load_spoint(sandbox, env_dir):
    initialize(env_dir)
    os.makedirs(".spoint_info", exist_ok=True)
    with open(".spoint_info/var.dat", "w") as f:
        f.write(".")
    assert spoints.load_spoint(".") == {}

def test_spoint_still_defined_mismatches(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    add_sweep("sweep2", include_stages=[], variable_values={"x": [6]})
    add_sweep("sweep3", include_stages=["stage1"], variable_values={"x": [7]})
    
    assert spoints.spoint_still_defined("sweep2", "stage1", {"x": 5}) is True
    assert spoints.spoint_still_defined("sweep1", "stage1", {"x": 9}) is False

def test_iter_spoints_mismatches(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    add_sweep("sweep2", include_stages=[], variable_values={"x": [5]})
    
    results = list(spoints.iter_spoints(sweep_names="all", stage_names="stage1"))
    assert len(results) == 1
    assert results[0][0] == "sweep1"

def test_link_dependent_spoint(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage_parent", sbatch_details=None, stage_variables=["x", "y"], stage_dependencies=[])
    add_stage("stage_child", sbatch_details=None, stage_variables=["x"], stage_dependencies=["stage_parent"])
    add_stage("stage_child_no_conv", sbatch_details=None, stage_variables=["x", "y"], stage_dependencies=["stage_parent"])
    
    add_variable("x", ["int"], add_to_stages=["stage_parent", "stage_child", "stage_child_no_conv"], default_val=5)
    add_variable("y", ["int"], add_to_stages=["stage_parent", "stage_child_no_conv"], default_val=10)
    add_sweep("sweep1", include_stages=["stage_parent", "stage_child", "stage_child_no_conv"], variable_values={"x": [5], "y": [10]})
    
    spoint_path_no_conv = spoints.get_spoint_path("stage_child_no_conv", {"x": 5, "y": 10})
    os.makedirs(spoint_path_no_conv, exist_ok=True)
    dep_info_no_conv = spoints.get_dependent_spoint_info("stage_child_no_conv", "sweep1", {"x": 5, "y": 10})
    spoints.link_dependent_spoint("stage_child_no_conv", {"x": 5, "y": 10}, dep_info_no_conv)
    
    spoint_path_conv = spoints.get_spoint_path("stage_child", {"x": 5})
    os.makedirs(spoint_path_conv, exist_ok=True)
    os.makedirs(os.path.join(spoint_path_conv, "stage_parent"), exist_ok=True)
    
    dep_info_conv = spoints.get_dependent_spoint_info("stage_child", "sweep1", {"x": 5})
    spoints.link_dependent_spoint("stage_child", {"x": 5}, dep_info_conv)
    assert os.path.isdir(os.path.join(spoint_path_conv, "stage_parent"))

def test_get_spoint_parent_variable_filtering(sandbox, env_dir):
    initialize(env_dir)
    add_stage("shrink", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_stage("bonding", sbatch_details=None, stage_variables=["x", "ncheck"], stage_dependencies=["shrink"])
    
    add_variable("x", ["int"], add_to_stages=["shrink", "bonding"], default_val=5)
    add_variable("ncheck", ["int"], add_to_stages=["bonding"], default_val=10)
    add_sweep("sweep1", include_stages=["shrink", "bonding"], variable_values={"x": [5], "ncheck": [10, 100]})
    
    spoints.create_spoint("shrink", {"x": 5}, clear=True)
    status.write_status("complete", spoints.get_spoint_path("shrink", {"x": 5}))
    
    manager = spoints.SPointStatusManager()
    res = manager.get_spoint("sweep1", "shrink", {"x": 5, "ncheck": 10})
    assert res is not None
    assert res["status"] == "complete"
    assert res["variables"] == {"x": 5}

def test_submit_spoints_logic(sandbox, env_dir, capsys):
    initialize(env_dir)
    sbatch_details = {
        "num_jobs": 1,
        "multi_submission": True,
        "partition": "test_part",
        "--array": "1-2"
    }
    add_stage("stage_sbatch", sbatch_details=sbatch_details, stage_variables=["x"], stage_dependencies=[])
    add_stage("stage_local", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    
    add_variable("x", ["int"], add_to_stages=["stage_sbatch", "stage_local"], default_val=5)
    add_sweep("sweep1", include_stages=["stage_sbatch", "stage_local"], variable_values={"x": [5, 6]})
    
    os.makedirs("stage_sbatch", exist_ok=True)
    os.makedirs("stage_local", exist_ok=True)
    with open("stage_sbatch/env.json", "w") as f:
        json.dump({"resources": {"cpus": 1, "gpus": 0, "mem": "1G"}}, f)
    with open("stage_local/env.json", "w") as f:
        json.dump({"resources": {"cpus": 1, "gpus": 0, "mem": "1G"}}, f)
        
    with open("stage_sbatch/env.json", "w") as f:
        f.write("invalid json")
    
    details = spoints.get_submission_details("stage_sbatch", {"sbatch_details": sbatch_details})
    captured = capsys.readouterr()
    assert "Warning: Failed to load" in captured.out
    
    with open("stage_sbatch/env.json", "w") as f:
        json.dump({"resources": {"cpus": 1, "gpus": 0, "mem": "1G"}, "sbatch": {"partition": "custom_part", "n": "4"}}, f)
    details2 = spoints.get_submission_details("stage_sbatch", {"sbatch_details": sbatch_details})
    assert details2["sbatch_flags"]["--partition"] == "custom_part"
    assert details2["sbatch_flags"]["-n"] == "4"
    
    spoints.create_spoint("stage_local", {"x": 5}, clear=True)
    spoints.create_spoint("stage_local", {"x": 6}, clear=True)
    spoints.create_spoint("stage_sbatch", {"x": 5}, clear=True)
    spoints.create_spoint("stage_sbatch", {"x": 6}, clear=True)
    
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        spoints.submit_spoints(sweep_names="sweep1", stage_names="stage_local", no_sbatch=True)
        assert status.load_status(spoints.get_spoint_path("stage_local", {"x": 5})) == "complete"
        assert status.load_status(spoints.get_spoint_path("stage_local", {"x": 6})) == "complete"
        
        status.write_status("initialized", spoints.get_spoint_path("stage_local", {"x": 5}))
        status.write_status("initialized", spoints.get_spoint_path("stage_local", {"x": 6}))
        mock_run.return_value.returncode = 1
        spoints.submit_spoints(sweep_names="sweep1", stage_names="stage_local", no_sbatch=True)
        assert status.load_status(spoints.get_spoint_path("stage_local", {"x": 5})) == "error"
        assert status.load_status(spoints.get_spoint_path("stage_local", {"x": 6})) == "error"

    status.write_status("initialized", spoints.get_spoint_path("stage_sbatch", {"x": 5}))
    status.write_status("initialized", spoints.get_spoint_path("stage_sbatch", {"x": 6}))
    with patch("snap_workflow.core.domain.spoints.params.set_params", side_effect=ValueError("Test Param Error")), \
         patch("subprocess.run"):
        spoints.submit_spoints(sweep_names="sweep1", stage_names="stage_sbatch")
        captured = capsys.readouterr()
        assert "Cannot submit spoints for stage stage_sbatch" in captured.out

    status.write_status("initialized", spoints.get_spoint_path("stage_sbatch", {"x": 5}))
    status.write_status("initialized", spoints.get_spoint_path("stage_sbatch", {"x": 6}))
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        spoints.submit_spoints(sweep_names="sweep1", stage_names="stage_sbatch", num_submits=lambda: 2)
        assert status.load_status(spoints.get_spoint_path("stage_sbatch", {"x": 5})) == "initialized"
        
        mock_run.return_value.returncode = 0
        spoints.submit_spoints(sweep_names="sweep1", stage_names="stage_sbatch", num_submits=2)
        assert status.load_status(spoints.get_spoint_path("stage_sbatch", {"x": 5})) == "submitted"

    with patch("subprocess.run"):
        spoints.submit_spoints()
        
    status.write_status("initialized", spoints.get_spoint_path("stage_sbatch", {"x": 5}))
    details2["sbatch_flags"]["--array"] = "1-2"
    with patch("subprocess.run"):
        spoints.submit_spoints(sweep_names="sweep1", stage_names="stage_sbatch", test_submit=True, num_submits=None)

def test_check_submittable_dependency_checks(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage_parent", sbatch_details=None, stage_variables=["x", "y"], stage_dependencies=[])
    add_stage("stage_child_no_conv", sbatch_details=None, stage_variables=["x", "y"], stage_dependencies=["stage_parent"])
    add_stage("stage_child_conv", sbatch_details=None, stage_variables=["x"], stage_dependencies=["stage_parent"])
    
    add_variable("x", ["int"], add_to_stages=["stage_parent", "stage_child_no_conv", "stage_child_conv"], default_val=5)
    add_variable("y", ["int"], add_to_stages=["stage_parent", "stage_child_no_conv"], default_val=10)
    add_sweep("sweep1", include_stages=["stage_parent", "stage_child_no_conv", "stage_child_conv"], variable_values={"x": [5], "y": [10]})
    
    with open("stage_parent/env.json", "w") as f:
        json.dump({"resources": {"cpus": 1, "gpus": 0, "mem": "1G"}}, f)
    with open("stage_child_no_conv/env.json", "w") as f:
        json.dump({"resources": {"cpus": 1, "gpus": 0, "mem": "1G"}}, f)
    with open("stage_child_conv/env.json", "w") as f:
        json.dump({"resources": {"cpus": 1, "gpus": 0, "mem": "1G"}}, f)
        
    spoints.create_spoint("stage_parent", {"x": 5, "y": 10}, clear=True)
    spoints.create_spoint("stage_child_no_conv", {"x": 5, "y": 10}, clear=True)
    spoints.create_spoint("stage_child_conv", {"x": 5}, clear=True)
    
    dep_info_no_conv = spoints.get_dependent_spoint_info("stage_child_no_conv", "sweep1", {"x": 5, "y": 10})
    spoints.link_dependent_spoint("stage_child_no_conv", {"x": 5, "y": 10}, dep_info_no_conv)
    
    dep_info_conv = spoints.get_dependent_spoint_info("stage_child_conv", "sweep1", {"x": 5})
    spoints.link_dependent_spoint("stage_child_conv", {"x": 5}, dep_info_conv)

    status.write_status("initialized", spoints.get_spoint_path("stage_parent", {"x": 5, "y": 10}))
    
    assert spoints.check_submittable("sweep1", "stage_child_no_conv", {"x": 5, "y": 10}) is False
    assert spoints.check_submittable("sweep1", "stage_child_conv", {"x": 5}) is False
    
    status.write_status("complete", spoints.get_spoint_path("stage_parent", {"x": 5, "y": 10}))
    assert spoints.check_submittable("sweep1", "stage_child_no_conv", {"x": 5, "y": 10}) is True
    assert spoints.check_submittable("sweep1", "stage_child_conv", {"x": 5}) is True
