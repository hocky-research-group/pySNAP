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


def test_spoint_scheduler_ttl_leases_and_heartbeats(sandbox, env_dir):
    import time
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=[], stage_dependencies=[])
    env_file = os.path.join("stage1", "env.json")
    with open(env_file, "r") as f:
        env_data = json.load(f)
    env_data["resources"] = {"cpus": 1, "gpus": 0, "mem": "1G"}
    with open(env_file, "w") as f:
        json.dump(env_data, f)

    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=10)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [10]})

    scheduler = SPointScheduler(default_lease_ttl=0.2)

    # 1. Acquire lease with short TTL (0.2s)
    cand = scheduler.acquire_next_available(cpus_avail=1, worker_id="worker_1")
    assert cand is not None
    sweep_name, stage_name, spoint_dict, sp_path = cand
    assert sp_path in scheduler.active_leases
    assert scheduler.active_leases[sp_path]["worker_id"] == "worker_1"

    # 2. Record start
    scheduler.record_start(sp_path, worker_id="worker_1", pid=12345, ttl=0.3)
    assert scheduler.active_leases[sp_path]["pid"] == 12345
    assert status.load_status(sp_path) == "running"

    # 3. Extend heartbeat
    extended = scheduler.extend_heartbeat([sp_path], worker_id="worker_1", ttl=0.4)
    assert extended == 1

    # 4. Wait for lease to expire (> 0.5s)
    time.sleep(0.5)

    # 5. Calling acquire or get_spoints should reclaim expired lease back to initialized
    reclaimed = scheduler.reclaim_expired_leases()
    assert reclaimed == 1
    assert sp_path not in scheduler.active_leases
    assert status.load_status(sp_path) == "initialized"

    # 6. Can be re-acquired by another worker
    cand2 = scheduler.acquire_next_available(cpus_avail=1, worker_id="worker_2")
    assert cand2 is not None
    assert scheduler.active_leases[sp_path]["worker_id"] == "worker_2"


def test_spoint_scheduler_worker_shutdown(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=[], stage_dependencies=[])
    env_file = os.path.join("stage1", "env.json")
    with open(env_file, "r") as f:
        env_data = json.load(f)
    env_data["resources"] = {"cpus": 1, "gpus": 0, "mem": "1G"}
    with open(env_file, "w") as f:
        json.dump(env_data, f)

    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=10)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [10, 20]})

    scheduler = SPointScheduler()

    # Worker 1 acquires and starts task 1
    cand1 = scheduler.acquire_next_available(cpus_avail=1, worker_id="worker_ls6", host="Lonestar")
    assert cand1 is not None
    sp_path1 = cand1[3]
    scheduler.record_start(sp_path1, worker_id="worker_ls6", host="Lonestar")
    assert status.load_status(sp_path1) == "running"

    # Worker 1 notifies shutdown with active task
    affected = scheduler.handle_worker_shutdown(worker_id="worker_ls6", host="Lonestar", active_tasks=[sp_path1])
    assert sp_path1 in affected
    assert status.load_status(sp_path1) == "incomplete"
    assert sp_path1 not in scheduler.active_leases
