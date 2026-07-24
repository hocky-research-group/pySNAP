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
