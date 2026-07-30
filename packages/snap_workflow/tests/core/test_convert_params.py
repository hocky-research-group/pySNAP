import os
import json
import pytest
import warnings
from snap_workflow.core.workflow import initialize
from snap_workflow.core.domain import stages, sweeps, variables, spoints, params, status
from snap_workflow.cli import main_reset, main_convert


def test_params_hashing_and_drift_warning(sandbox):
    os.chdir(sandbox)
    initialize()

    # Create dummy params config
    with open("params/solver.json", "w") as f:
        json.dump({"tolerance": 1e-5}, f)

    stages.add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    variables.add_variable("x", ["int"], add_to_stages=["stage1"], default_val=10)
    sweeps.add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [10, 20]})

    sp_path = spoints.get_spoint_path("stage1", {"x": 10})
    params_obj = params.load_params(sp_path)

    assert hasattr(params_obj, "source_hash")
    assert params_obj.source_hash is not None

    # Modify params/ file to introduce drift
    with open("params/solver.json", "w") as f:
        json.dump({"tolerance": 1e-9}, f)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        params.load_params(sp_path)
        assert any("source hash mismatch" in str(item.message) for item in w)


def test_export_and_convert_params(sandbox):
    os.chdir(sandbox)
    initialize()

    with open("params/config.json", "w") as f:
        json.dump({"steps": 100}, f)

    stages.add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    variables.add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    sweeps.add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})

    sp_path = spoints.get_spoint_path("stage1", {"x": 5})

    # Test export_readable to JSON and YAML
    params_obj = params.load_params(sp_path)
    json_path = params_obj.export_readable(os.path.join(sp_path, "params.json"), format="json")
    yaml_path = params_obj.export_readable(os.path.join(sp_path, "params.yaml"), format="yaml")

    assert os.path.isfile(json_path)
    assert os.path.isfile(yaml_path)

    with open(json_path, "r") as f:
        data = json.load(f)
        assert data["params"]["config"]["steps"] == 100
        assert data["variables"]["x"] == 5

    # Test convert_params function
    res = params.convert_params(sweep_name="sweep1", stage_name="stage1", format="json")
    assert len(res) == 1
    assert os.path.isfile(res[0])


def test_reset_spoint_cwd(sandbox):
    os.chdir(sandbox)
    initialize()

    stages.add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    variables.add_variable("x", ["int"], add_to_stages=["stage1"], default_val=10)
    sweeps.add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [10]})

    sp_path = spoints.get_spoint_path("stage1", {"x": 10})

    # Test error when run outside an SPoint directory
    with pytest.raises(ValueError, match="is not an SPoint directory"):
        spoints.reset_spoint(sandbox)

    # Change into SPoint CWD
    os.chdir(sp_path)

    # Create dummy output file and set status
    with open("output.txt", "w") as f:
        f.write("simulation result")
    status.write_status("complete", ".")

    # Standard reset in CWD
    spoints.reset_spoint(".", hard=False)
    assert status.load_status(".") == "initialized"
    assert os.path.isfile("output.txt")  # Output preserved on non-hard reset

    # Hard reset in CWD
    spoints.reset_spoint(".", hard=True)
    assert status.load_status(".") == "initialized"
    assert not os.path.exists("output.txt")  # Output wiped on hard reset
    assert os.path.exists(".spoint_info/var.dat")


def test_reset_spoint_cli(sandbox):
    os.chdir(sandbox)
    initialize()

    stages.add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    variables.add_variable("x", ["int"], add_to_stages=["stage1"], default_val=15)
    sweeps.add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [15]})

    sp_path = spoints.get_spoint_path("stage1", {"x": 15})

    # CLI reset outside SPoint should exit with status 1
    with pytest.raises(SystemExit) as exc_info:
        main_reset("workflow reset", ["spoint"])
    assert exc_info.value.code == 1

    # Change to SPoint CWD
    os.chdir(sp_path)
    with open("result.dat", "w") as f:
        f.write("12345")

    main_reset("workflow reset", ["spoint"])
    assert status.load_status(".") == "initialized"
    assert os.path.isfile("result.dat")

    main_reset("workflow reset", ["spoint", "--hard", "--force"])
    assert status.load_status(".") == "initialized"
    assert not os.path.exists("result.dat")


def test_reset_spoint_relinks_dependencies(sandbox):
    os.chdir(sandbox)
    initialize()

    stages.add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    stages.add_stage("stage2", sbatch_details=None, stage_variables=["x"], stage_dependencies=["stage1"])
    variables.add_variable("x", ["int"], add_to_stages=["stage1", "stage2"], default_val=10)
    sweeps.add_sweep("sweep1", include_stages=["stage1", "stage2"], variable_values={"x": [10]})

    sp2_path = spoints.get_spoint_path("stage2", {"x": 10})
    os.chdir(sp2_path)

    dep_link = os.path.join(".", "stage1")
    assert os.path.exists(dep_link) or os.path.islink(dep_link)

    # Perform hard reset in CWD
    spoints.reset_spoint(".", hard=True)

    # Verify that status is initialized AND dependency link was restored
    assert status.load_status(".") == "initialized"
    assert os.path.islink(dep_link) or os.path.exists(dep_link)

    # CLI convert params in SPoint CWD
    main_convert("workflow convert", ["params", "--format", "json"])
    assert os.path.isfile("params.json")
