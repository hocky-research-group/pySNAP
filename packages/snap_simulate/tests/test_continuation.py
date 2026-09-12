"""A stage that is interrupted continues where it stopped when it is submitted again.

Production runs here are long enough to outlast a queue's walltime, so a stage has to
resume: from its own trajectory, appending rather than truncating, and running only the
steps it has left.
"""

import os

import gsd.hoomd
import numpy as np
import pytest

from snap_simulate.hoomd.simulation import (STAGE_START_FILE, remaining_steps,
                                            resolve_continuation,
                                            stage_trajectory_files)


def params_with_trajectory(filename="trajdump.gsd", **simulation):
    """Return a parameter tree whose stage writes one GSD trajectory.

    filename: the trajectory the stage writes.
    simulation: entries for the "simulation" section, e.g. continue_file.
    """
    return {
        "simulation": dict(simulation),
        "writers": {
            "trajectory": {"class": "GSD", "options": {"filename": filename,
                                                       "mode": "wb"}},
            "performance": {"class": "Table", "options": {}},
        },
    }


def write_trajectory(path, steps):
    """Write a GSD holding one frame per entry of `steps`, at those timesteps."""
    with gsd.hoomd.open(str(path), "w") as traj:
        for step in steps:
            frame = gsd.hoomd.Frame()
            frame.configuration.step = step
            frame.particles.N = 1
            frame.particles.position = [[0.0, 0.0, 0.0]]
            frame.particles.types = ["A"]
            traj.append(frame)


class FakeSimulation:
    """Stands in for a HOOMD simulation, which only needs to report its timestep."""

    def __init__(self, timestep):
        self.timestep = timestep


class TestStageTrajectories:
    def test_gsd_writers_are_found(self):
        assert stage_trajectory_files(params_with_trajectory()) == ["trajdump.gsd"]

    def test_other_writers_are_ignored(self):
        params = params_with_trajectory()
        del params["writers"]["trajectory"]
        assert stage_trajectory_files(params) == []

    def test_a_stage_that_writes_nothing_is_no_trouble(self):
        assert stage_trajectory_files({"simulation": {}}) == []


class TestResolveContinuation:
    def test_a_fresh_stage_starts_from_nothing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert resolve_continuation(params_with_trajectory()) is None

    def test_a_stage_resumes_from_its_own_trajectory(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        write_trajectory(tmp_path / "trajdump.gsd", [0, 5000])
        assert resolve_continuation(params_with_trajectory()) == "trajdump.gsd"

    def test_an_empty_trajectory_is_not_resumed_from(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        write_trajectory(tmp_path / "trajdump.gsd", [])
        assert resolve_continuation(params_with_trajectory()) is None

    def test_a_named_continue_file_wins(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        write_trajectory(tmp_path / "trajdump.gsd", [0])
        write_trajectory(tmp_path / "earlier.gsd", [0])
        params = params_with_trajectory(continue_file="earlier.gsd")
        assert resolve_continuation(params) == "earlier.gsd"

    def test_a_named_file_that_is_not_there_starts_fresh(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        params = params_with_trajectory(continue_file="missing.gsd")
        assert resolve_continuation(params) is None


class TestRemainingSteps:
    def test_a_fresh_stage_runs_its_whole_length(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / STAGE_START_FILE).write_text("20000")
        assert remaining_steps(FakeSimulation(20000), 500000) == 500000

    def test_a_resumed_stage_runs_what_is_left(self, tmp_path, monkeypatch):
        """The stage began at 20000 and has reached 150000, so 370000 remain."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / STAGE_START_FILE).write_text("20000")
        assert remaining_steps(FakeSimulation(150000), 500000) == 370000

    def test_a_finished_stage_runs_nothing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / STAGE_START_FILE).write_text("20000")
        assert remaining_steps(FakeSimulation(520000), 500000) == 0

    def test_overshooting_does_not_go_negative(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / STAGE_START_FILE).write_text("20000")
        assert remaining_steps(FakeSimulation(999999), 500000) == 0

    def test_without_the_marker_the_trajectory_says_where_it_began(self, tmp_path,
                                                                   monkeypatch):
        """Runs started before the marker existed still resume, to within one period."""
        monkeypatch.chdir(tmp_path)
        write_trajectory(tmp_path / "trajdump.gsd", [20000, 60000, 100000])
        assert remaining_steps(FakeSimulation(100000), 500000,
                               continue_path="trajdump.gsd") == 420000
