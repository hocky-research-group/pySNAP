import os
import json
import pytest
import subprocess
from unittest.mock import patch, MagicMock

from snap_workflow.core.workflow import initialize
from snap_workflow.core.domain.stages import add_stage
from snap_workflow.dispatcher.slurm import SlurmDispatcher, slurm_dispatcher_loop


def test_slurm_dispatcher_capacity(sandbox, env_dir):
    initialize(env_dir)
    d = SlurmDispatcher(server_url="http://localhost:8000", token="token", max_queued_jobs=2)
    assert d.has_capacity() is True

    d.active_jobs["job1"] = {"job_id": "101"}
    assert d.has_capacity() is True

    d.active_jobs["job2"] = {"job_id": "102"}
    assert d.has_capacity() is False


def test_slurm_dispatcher_dispatch_and_script_generation(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])

    spoint_dir = os.path.join("stage1", "spoints", "x_5")
    os.makedirs(spoint_dir, exist_ok=True)

    d = SlurmDispatcher(server_url="http://localhost:8000", token="token", max_queued_jobs=10)

    task = {
        "sweep": "sweep1",
        "stage": "stage1",
        "spoint_dict": {"x": 5},
        "spoint_path": spoint_dir
    }

    mock_res = subprocess.CompletedProcess(args=["sbatch"], returncode=0, stdout="Submitted batch job 888123\n")

    with patch("subprocess.run", return_value=mock_res) as mock_run, \
         patch.object(d, "send_request", return_value={"status": "ok"}):
        d.dispatch_task(task)

        assert mock_run.called
        sbatch_call = mock_run.call_args[0][0]
        assert sbatch_call[0] == "sbatch"
        script_path = sbatch_call[-1]
        assert os.path.isfile(script_path)

        with open(script_path, "r") as f:
            script_content = f.read()

        assert "#SBATCH -J snap_stage1" in script_content
        assert "#SBATCH --signal=B:INT@60" in script_content
        assert "snap_workflow.dispatcher.runner" in script_content
        assert "--assigned-spoints" in script_content
        assert spoint_dir in d.active_jobs
        assert d.active_jobs[spoint_dir]["job_id"] == "888123"


def test_slurm_dispatcher_custom_profile_and_chained_submissions(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage_chained", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])

    env_file = os.path.join("stage_chained", "env.json")
    with open(env_file, "r") as f:
        env_data = json.load(f)
    env_data["setup_cmds"] = ["module load cuda/12.2", "export OMP_NUM_THREADS=1"]
    env_data["chained_submissions"] = 3
    env_data["slurm_flags"] = {"-p": "gpu-a100", "-N": 1, "-n": 1, "-t": "02:00:00"}
    with open(env_file, "w") as f:
        json.dump(env_data, f, indent=4)

    spoint_dir = os.path.join("stage_chained", "spoints", "x_10")
    os.makedirs(spoint_dir, exist_ok=True)

    d = SlurmDispatcher(server_url="http://localhost:8000", token="token", max_queued_jobs=10)

    task = {
        "sweep": "sweep1",
        "stage": "stage_chained",
        "spoint_dict": {"x": 10},
        "spoint_path": spoint_dir
    }

    call_count = 0
    job_ids = ["10001", "10002", "10003"]
    submitted_commands = []

    def mock_subprocess_run(cmd, *args, **kwargs):
        nonlocal call_count
        submitted_commands.append(cmd)
        jid = job_ids[call_count]
        call_count += 1
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=f"Submitted batch job {jid}\n")

    with patch("subprocess.run", side_effect=mock_subprocess_run), \
         patch.object(d, "send_request", return_value={"status": "ok"}):
        d.dispatch_task(task)

        assert call_count == 3
        # Check script content from initial submission
        script_file = os.path.join(spoint_dir, "run_spoint.sbatch")
        with open(script_file, "r") as f:
            content = f.read()

        assert "#SBATCH -p gpu-a100" in content
        assert "#SBATCH -N 1" in content
        assert "#SBATCH -n 1" in content
        assert "#SBATCH -t 02:00:00" in content
        assert "module load cuda/12.2" in content
        assert "export OMP_NUM_THREADS=1" in content

        # Check dependency chaining on subsequent submissions
        assert submitted_commands[0] == ["sbatch", script_file]
        assert submitted_commands[1] == ["sbatch", "--dependency=afterany:10001", script_file]
        assert submitted_commands[2] == ["sbatch", "--dependency=afterany:10002", script_file]
        assert d.active_jobs[spoint_dir]["job_id"] == "10001"


def test_slurm_dispatcher_reap_finished(sandbox, env_dir):
    initialize(env_dir)
    d = SlurmDispatcher(server_url="http://localhost:8000", token="token")
    d.active_jobs["p1"] = {"job_id": "1001", "stage": "stage1"}
    d.active_jobs["p2"] = {"job_id": "1002", "stage": "stage1"}

    # Simulate squeue returning only job 1001 (meaning 1002 has finished)
    mock_res = subprocess.CompletedProcess(
        args=["squeue"],
        returncode=0,
        stdout="1001 RUNNING\n"
    )

    with patch("subprocess.run", return_value=mock_res):
        d.reap_finished()

    assert "p1" in d.active_jobs
    assert "p2" not in d.active_jobs


def test_slurm_dispatcher_cleanup_scancel(sandbox, env_dir):
    initialize(env_dir)
    d = SlurmDispatcher(server_url="http://localhost:8000", token="token")
    d.active_jobs["p1"] = {"job_id": "1001"}
    d.active_jobs["p2"] = {"job_id": "1002"}

    with patch("subprocess.run") as mock_run:
        d.cleanup()
        assert mock_run.called
        args = mock_run.call_args[0][0]
        assert args == ["scancel", "1001", "1002"]


def test_slurm_dispatcher_remote_ssh(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])

    spoint_dir = os.path.join("stage1", "spoints", "x_5")
    os.makedirs(spoint_dir, exist_ok=True)

    d = SlurmDispatcher(
        server_url="http://localhost:8000",
        token="token",
        remote_host="lonestar",
        remote_path="~/remote_proj",
        remote_port=9090,
        max_queued_jobs=10
    )
    assert d.is_remote is True
    assert d.remote_host == "lonestar"

    task = {
        "sweep": "sweep1",
        "stage": "stage1",
        "spoint_dict": {"x": 5},
        "spoint_path": spoint_dir
    }

    # 1. Test remote dispatch over SSH
    mock_sbatch_res = subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="Submitted batch job 999111\n")
    with patch("subprocess.run", return_value=mock_sbatch_res) as mock_run, \
         patch.object(d, "send_request", return_value={"status": "ok"}):
        d.dispatch_task(task)
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "ssh"
        assert "lonestar" in call_args
        assert "cd ~/remote_proj && sbatch" in call_args[-1]
        assert mock_run.call_args[1].get("input") is not None
        assert spoint_dir in d.active_jobs
        assert d.active_jobs[spoint_dir]["job_id"] == "999111"

    # 2. Test remote reap over SSH
    mock_squeue_res = subprocess.CompletedProcess(args=["ssh"], returncode=0, stdout="999111 RUNNING\n")
    with patch("subprocess.run", return_value=mock_squeue_res) as mock_run:
        d.reap_finished()
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "ssh"
        assert "lonestar" in call_args
        assert "squeue -j 999111" in call_args[-1]
        assert spoint_dir in d.active_jobs

    # 3. Test remote cleanup/scancel over SSH
    with patch("subprocess.run") as mock_run:
        d.cleanup()
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "ssh"
        assert "lonestar" in call_args
        assert "scancel 999111" in call_args[-1]
