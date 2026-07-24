import pytest
import numpy as np
from snap_analyze import Fskt, dynamics

def test_incremental_dynamics():
    box = [10.0, 10.0, 10.0]
    dyn = dynamics(box, kmag=1.1, min_avg_count=1, sampling_mode="logarithmic", Nmag=5)

    np.random.seed(42)
    N_particles = 20
    base_pos = np.random.uniform(-4, 4, (N_particles, 3))

    timesteps = [0, 10, 20, 30, 40, 50, 80, 100, 160, 200, 320, 400]
    for step in timesteps:
        disp = np.random.normal(0, 0.1 * np.sqrt(step + 1), (N_particles, 3))
        pos = base_pos + disp
        dyn.append_timestep(step, pos)

    dts, Fskt_vals = dyn.calc_Fskt()
    assert len(dts) > 0
    assert len(Fskt_vals) == len(dts)
    assert Fskt_vals[0] <= 1.0

    # Test MSD and vanHove
    dts_msd, msds = dyn.calc_MSD()
    assert len(dts_msd) == len(dts)
    assert msds[0] >= 0

    dts_vh, bins, probs = dyn.calc_vanHove()
    assert len(dts_vh) == len(dts)
    assert len(probs) == len(dts)
