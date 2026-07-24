import os
import tempfile
import numpy as np
import pytest
from unittest.mock import MagicMock
from snap_simulate.hoomd.auto_correlation import (
    BaseSampler,
    PESampler,
    FSKTSampler,
    minimize_autocorrelation,
    min_auto_PE,
    min_auto_FSKT,
)


class DummySampler(BaseSampler):
    def __init__(self, file_name="dummy_sampler.pkl", **kwargs):
        super().__init__(file_name=file_name, **kwargs)

    def _internal_sample(self, timestep, frame):
        val = len(self.samples) + 1.0
        return val

    def _internal_compute(self, tail_window=10, threshold=0.01):
        if len(self.samples) >= 3:
            return True, np.array(self.samples)
        return False, np.array(self.samples)


def test_base_sampler_save_load_and_data():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = os.path.join(tmpdir, "state.pkl")
        data_file = os.path.join(tmpdir, "data.txt")

        sampler = DummySampler(file_name=state_file)
        sampler.sample(10, None)
        sampler.sample(20, None)

        assert sampler.save_state() is None
        assert os.path.exists(state_file)

        # Create new sampler instance and restore state
        restored_sampler = DummySampler(file_name=state_file)
        assert restored_sampler.load_state() is True
        assert restored_sampler.timesteps == [10, 20]
        assert restored_sampler.samples == [1.0, 2.0]

        # Test save_data
        sampler.save_data(data_file)
        assert os.path.exists(data_file)
        data = np.loadtxt(data_file)
        assert data.shape == (2, 2)
        assert np.allclose(data[:, 0], [10, 20])
        assert np.allclose(data[:, 1], [1.0, 2.0])


def test_pe_sampler():
    mock_logger = MagicMock()
    mock_logger.log.return_value = {
        'md': {
            'compute': {
                'ThermodynamicQuantities': {
                    'potential_energy': [ -12.5 ]
                }
            }
        }
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = os.path.join(tmpdir, "pe_state.pkl")
        pe_sampler = PESampler(logger=mock_logger, file_name=state_file)

        pe_val = pe_sampler.sample(100, None)
        assert pe_val == -12.5
        assert pe_sampler.timesteps == [100]
        assert pe_sampler.samples == [-12.5]

        # Test check function
        minimized, auto = pe_sampler.check(tail_window=2, threshold=0.1)
        assert minimized is False

        pe_sampler.save_state()
        assert os.path.exists(state_file)


def test_minimize_autocorrelation_with_sampler():
    mock_sim = MagicMock()
    mock_sim.timestep = 0

    def mock_run(steps):
        mock_sim.timestep += steps

    mock_sim.run.side_effect = mock_run

    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = os.path.join(tmpdir, "dummy_state.pkl")
        sampler = DummySampler(file_name=state_file)

        res = minimize_autocorrelation(
            mock_sim,
            sampler,
            max_steps=1000
        )

        assert res["minimized"] is True
        assert res["steps_ran"] == 30
        assert len(sampler.timesteps) == 3
        assert sampler.samples == [1.0, 2.0, 3.0]
        assert "sampler" in res


def test_backwards_compatibility():
    mock_logger = MagicMock()
    mock_logger.log.return_value = {
        'md': {
            'compute': {
                'ThermodynamicQuantities': {
                    'potential_energy': [ -5.0 ]
                }
            }
        }
    }
    sample_fn, check_fn = min_auto_PE(mock_logger)
    val = sample_fn(10, None)
    assert val == -5.0


def test_fskt_sampler():
    mock_sim = MagicMock()
    mock_sim.operations.integrator.dt = 0.005
    mock_sim.state.box.L = [10.0, 10.0, 10.0]

    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = os.path.join(tmpdir, "fskt_state.pkl")
        data_file = os.path.join(tmpdir, "fskt_data.txt")
        sampler = FSKTSampler(sim=mock_sim, ptype=0, file_name=state_file)

        # Mock frame snapshot
        mock_frame = MagicMock()
        mock_frame.particles.position = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]])
        mock_frame.particles.image = np.array([[0, 0, 0], [0, 0, 0]])
        mock_frame.particles.typeid = np.array([0, 1])

        sampler.sample(10, mock_frame)
        sampler.sample(20, mock_frame)
        assert len(sampler.timesteps) == 2

        # Test save_state and auto_load
        sampler.save_state()
        assert os.path.exists(state_file)

        # FSKTSampler auto-loads when file exists (auto_load=True by default)
        restored_sampler = FSKTSampler(sim=mock_sim, ptype=0, file_name=state_file)
        assert len(restored_sampler.timesteps) == 2

        # Can disable auto_load with auto_load=False
        fresh_sampler = FSKTSampler(sim=mock_sim, ptype=0, file_name=state_file, auto_load=False)
        assert len(fresh_sampler.timesteps) == 0


def test_logarithmic_sampling_schedule():
    sampler = DummySampler(file_name="dummy_log.pkl")
    sampler.sampling_mode = "logarithmic"
    sampler.min_interval = 10
    sampler.max_interval = 5000
    sampler.Nmag = 5
    intervals = []
    current_time = 0
    for _ in range(10):
        dt = sampler.get_next_sample_interval()
        intervals.append(dt)
        current_time += dt
        sampler.sample(current_time, None)
    assert intervals[0] == 10
    assert intervals[-1] > intervals[0]


def test_navg_sample_times_extension():
    sampler1 = DummySampler(file_name="dummy_navg1.pkl", sampling_mode="logarithmic", min_interval=10, max_interval=1000, Nmag=5, Navg=1)
    extended1 = sampler1._get_extended_sample_times()

    sampler3 = DummySampler(file_name="dummy_navg3.pkl", sampling_mode="logarithmic", min_interval=10, max_interval=1000, Nmag=5, Navg=3)
    extended3 = sampler3._get_extended_sample_times()

    # Navg=3 should include extra time points (multiples of base log_times)
    assert len(extended3) > len(extended1)

    # Verify every element in extended3 is sorted and unique
    assert extended3 == sorted(list(set(extended3)))

    # Verify exact relationship: [dt * i for i in range(1, 4) for dt in log_times]
    log_times = [st for st in extended1 if st <= 1000]
    expected3 = sorted(list(set(st for i in range(1, 4) for dt in log_times for st in [dt * i] if st <= 1000)))
    assert extended3 == expected3


def test_fskt_multiprocessing_sampler():
    mock_sim = MagicMock()
    mock_sim.operations.integrator.dt = 0.005
    mock_sim.state.box.L = [10.0, 10.0, 10.0]

    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = os.path.join(tmpdir, "fskt_mp_state.pkl")
        sampler = FSKTSampler(sim=mock_sim, ptype=0, file_name=state_file, use_multiprocessing=True)

        try:
            mock_frame = MagicMock()
            mock_frame.particles.position = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]])
            mock_frame.particles.image = np.array([[0, 0, 0], [0, 0, 0]])
            mock_frame.particles.typeid = np.array([0, 1])

            sampler.sample(10, mock_frame)
            sampler.sample(20, mock_frame)
            assert len(sampler.timesteps) == 2

            sampler.save_state()
            assert os.path.exists(state_file)

            npy_data_file = os.path.join(tmpdir, "fskt.npy")
            sampler.save_data(npy_data_file)
            assert os.path.exists(npy_data_file)
            loaded_npy = np.load(npy_data_file)
            assert loaded_npy.ndim == 2
        finally:
            sampler.close()



