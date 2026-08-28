import os
import json
import pytest
from snap_workflow.core.workflow import initialize
from snap_workflow.core.domain.stages import add_stage
from snap_workflow.core.domain.variables import add_variable
from snap_workflow.core.domain.sweeps import add_sweep
from snap_workflow.core.domain import status, spoints
from snap_workflow.server.scheduler import SPointScheduler


def test_spoint_scheduler_lifecycle(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=[], stage_dependencies=[])
    env_file = os.path.join("stage1", "env.json")
    with open(env_file, "r") as f:
        env_data = json.load(f)
    env_data["resources"] = {"cpus": 2, "gpus": 0, "mem": "1G"}
    with open(env_file, "w") as f:
        json.dump(env_data, f)

    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=10)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [10, 20]})

    scheduler = SPointScheduler()

    # Get spoints before running
    sps = scheduler.get_spoints("sweep1", "stage1")
    assert len(sps) == 2
    assert sps[0]["status"] == "initialized"

    # Acquire next available with insufficient CPUs
    cand_none = scheduler.acquire_next_available(cpus_avail=1)
    assert cand_none is None

    # Acquire next available with sufficient CPUs
    cand = scheduler.acquire_next_available(cpus_avail=2)
    assert cand is not None
    sweep_name, stage_name, spoint_dict, sp_path = cand
    assert sweep_name == "sweep1"
    assert stage_name == "stage1"
    assert spoint_dict in [{"x": 10}, {"x": 20}]
    assert status.load_status(sp_path) == "submitted"

    # Verify not all complete yet
    assert scheduler.are_all_complete() is False

    # Mark both complete
    status.write_status("complete", spoints.get_spoint_path("stage1", {"x": 10}))
    status.write_status("complete", spoints.get_spoint_path("stage1", {"x": 20}))

    assert scheduler.are_all_complete() is True
