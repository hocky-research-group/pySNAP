import hoomd
import numpy as np
import pytest
from snap_workflow.core.params.system_params import System_Params
from snap_simulate.hoomd import shrink_box

def test_shrink_box(tmp_path):
    sim = hoomd.Simulation(hoomd.device.CPU())
    snapshot = hoomd.Snapshot()
    snapshot.configuration.box = [10.0, 10.0, 10.0, 0, 0, 0]
    snapshot.particles.N = 2
    snapshot.particles.types = ['A']
    snapshot.particles.position[:] = [[0, 0, 0], [1, 1, 1]]
    sim.create_state_from_snapshot(snapshot)

    param_dir = tmp_path / "params"
    param_dir.mkdir()
    (param_dir / "box.yml").write_text("""
dimensions: 3
box_length: [10.0, 10.0, 10.0]
shrink:
  final_box_length: [5.0, 5.0, 5.0]
  total_steps: 50
  updater_period: 5
""")

    sys_params = System_Params(str(param_dir))
    shrink_box(sim, sys_params)

    assert np.allclose(sim.state.box.L, [5.0, 5.0, 5.0])


def test_shrink_box_direct_kwargs():
    sim = hoomd.Simulation(hoomd.device.CPU())
    snapshot = hoomd.Snapshot()
    snapshot.configuration.box = [10.0, 10.0, 10.0, 0, 0, 0]
    snapshot.particles.N = 2
    snapshot.particles.types = ['A']
    snapshot.particles.position[:] = [[0, 0, 0], [1, 1, 1]]
    sim.create_state_from_snapshot(snapshot)

    shrink_box(sim, total_steps=20, updater_period=2, final_box_length=[4.0, 4.0, 4.0])

    assert np.allclose(sim.state.box.L, [4.0, 4.0, 4.0])


def test_shrink_box_top_level_dict():
    sim = hoomd.Simulation(hoomd.device.CPU())
    snapshot = hoomd.Snapshot()
    snapshot.configuration.box = [10.0, 10.0, 10.0, 0, 0, 0]
    snapshot.particles.N = 2
    snapshot.particles.types = ['A']
    snapshot.particles.position[:] = [[0, 0, 0], [1, 1, 1]]
    sim.create_state_from_snapshot(snapshot)

    top_level_params = {
        "box": {"dimensions": 3, "box_length": [10.0, 10.0, 10.0]},
        "shrink": {
            "final_box_length": [6.0, 6.0, 6.0],
            "total_steps": 30,
            "updater_period": 3,
        }
    }

    shrink_box(sim, top_level_params)

    assert np.allclose(sim.state.box.L, [6.0, 6.0, 6.0])

