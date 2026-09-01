import os
import pickle
import warnings
import numpy as np
import multiprocessing as mp


def _sampler_worker_loop(sampler_factory, init_kwargs, input_queue, result_queue, worker_name="FSKT_Worker"):
    """Generic background process worker loop for any BaseSampler subclass."""
    try:
        import setproctitle
        setproctitle.setproctitle(worker_name)
    except Exception:
        pass

    try:
        import ctypes
        # Set Linux process name (PR_SET_NAME = 15) for /proc/PID/comm
        ctypes.CDLL("libc.so.6").prctl(15, worker_name[:15].encode("utf-8"), 0, 0, 0)
    except Exception:
        pass

    try:
        sampler_inst = sampler_factory(**init_kwargs)
    except Exception as e:
        result_queue.put(("ERROR", e))
        return

    while True:
        try:
            cmd, args = input_queue.get()
            if cmd == "SAMPLE":
                timestep, payload = args
                sampler_inst._internal_sample(timestep, payload)
            elif cmd == "COMPUTE":
                tail_window, threshold = args if args is not None else (10, 0.01)
                res = sampler_inst._internal_compute(tail_window=tail_window, threshold=threshold)
                result_queue.put(res)
            elif cmd == "SAVE":
                file_name = args
                sampler_inst._internal_save_state(file_name)
            elif cmd == "LOAD":
                file_name = args
                res = sampler_inst._internal_load_state(file_name)
                result_queue.put(res)
            elif cmd == "SAVE_DATA":
                file_name = args
                res = sampler_inst.save_data(file_name)
                result_queue.put(res)
            elif cmd == "TERMINATE":
                break
        except Exception as e:
            result_queue.put(("ERROR", e))


class BaseSampler:
    """Base class for autocorrelation samplers supporting logarithmic scheduling and background multiprocessing."""

    def __init__(
        self,
        file_name="sampler_state.pkl",
        sampling_mode="linear",
        min_interval=10,
        max_interval=None,
        Nmag=10,
        Navg=1,
        use_multiprocessing=False,
        auto_load=True,
    ):
        self.file_name = file_name
        self.sampling_mode = sampling_mode
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.Nmag = Nmag
        self.Navg = Navg
        self.use_multiprocessing = use_multiprocessing
        self.auto_load = auto_load

        self.timesteps = []
        self.samples = []
        self.sample_count = 0
        self.initial_timestep = None
        self.latest_auto_result = (False, None)
        self._extended_sample_times = None

        self._worker_process = None
        self._input_queue = None
        self._result_queue = None

    @property
    def steps_ran(self):
        """Total simulation timesteps executed under this sampler."""
        if not self.timesteps or self.initial_timestep is None:
            return 0
        return self.timesteps[-1] - self.initial_timestep

    def _init_multiprocessing(self, sampler_factory, init_kwargs, worker_name="FSKT_Worker"):
        if self.use_multiprocessing and self._worker_process is None:
            try:
                ctx = mp.get_context("fork")
            except (ValueError, AttributeError):
                ctx = mp.get_context("spawn")
            self._input_queue = ctx.Queue()
            self._result_queue = ctx.Queue()
            self._worker_process = ctx.Process(
                target=_sampler_worker_loop,
                args=(sampler_factory, init_kwargs, self._input_queue, self._result_queue, worker_name),
                name=worker_name,
                daemon=True,
            )
            self._worker_process.start()

    def _get_extended_sample_times(self, num_log_points=500):
        log_times = []
        max_int = np.inf if self.max_interval is None else self.max_interval
        for k in range(num_log_points):
            tau = int(round(self.min_interval * (10.0 ** (k / self.Nmag))))
            log_times.append(tau)
            if self.max_interval is not None and tau >= self.max_interval:
                break

        sample_times = [int(dt * i) for i in range(1, self.Navg + 1) for dt in log_times]
        if self.max_interval is not None:
            sample_times = [st for st in sample_times if st <= self.max_interval]
        return sorted(list(set(sample_times)))

    def get_next_sample_interval(self):
        """Calculates the next simulation step interval based on sampling_mode, Nmag, and Navg."""
        if self.sampling_mode == "linear":
            return self.min_interval
        elif self.sampling_mode == "logarithmic":
            if self._extended_sample_times is None:
                self._extended_sample_times = self._get_extended_sample_times()
            extended_times = self._extended_sample_times
            k = self.sample_count
            if k == 0:
                return extended_times[0]
            elif k < len(extended_times):
                return max(1, extended_times[k] - extended_times[k - 1])
            else:
                step_after = extended_times[-1] - extended_times[-2] if len(extended_times) > 1 else self.min_interval
                return max(self.min_interval, step_after)
        else:
            raise ValueError(f"Unknown sampling_mode: {self.sampling_mode}")

    def sample(self, timestep, frame):
        """Sample data at a given timestep."""
        if self.initial_timestep is None:
            interval = self.get_next_sample_interval()
            self.initial_timestep = max(0, timestep - interval)

        self.sample_count += 1
        self.timesteps.append(timestep)

        if self.use_multiprocessing and self._worker_process is not None:
            payload = self._extract_frame_payload(frame)
            self._input_queue.put(("SAMPLE", (timestep, payload)))
            self.samples.append(None)
            return None
        else:
            sample_val = self._internal_sample(timestep, frame)
            self.samples.append(sample_val)
            return sample_val

    def check(self, tail_window=10, threshold=0.01):
        """Check autocorrelation condition. Returns (minimized: bool, auto_value)."""
        if self.use_multiprocessing and self._worker_process is not None:
            self._input_queue.put(("COMPUTE", (tail_window, threshold)))
            res = self._result_queue.get()
            if isinstance(res, tuple) and len(res) == 2 and res[0] == "ERROR":
                raise res[1]
            self.latest_auto_result = res
            return self.latest_auto_result
        else:
            self.latest_auto_result = self._internal_compute(tail_window=tail_window, threshold=threshold)
            return self.latest_auto_result

    def save_state(self, file_name=None):
        """Save sampler state to a pickle file."""
        file_name = file_name or self.file_name
        base_state = {
            "timesteps": self.timesteps,
            "samples": self.samples,
            "sample_count": self.sample_count,
            "initial_timestep": self.initial_timestep,
            "sampling_mode": self.sampling_mode,
            "min_interval": self.min_interval,
            "max_interval": self.max_interval,
            "Nmag": self.Nmag,
            "Navg": self.Navg,
        }
        with open(file_name, "wb") as f:
            pickle.dump(base_state, f)

        if self.use_multiprocessing and self._worker_process is not None:
            self._input_queue.put(("SAVE", file_name))
        else:
            self._internal_save_state(file_name)

    def load_state(self, file_name=None):
        """Load sampler state from a pickle file if it exists."""
        file_name = file_name or self.file_name
        if os.path.exists(file_name):
            with open(file_name, "rb") as f:
                base_state = pickle.load(f)
                self.timesteps = base_state.get("timesteps", [])
                self.samples = base_state.get("samples", [])
                self.sample_count = base_state.get("sample_count", len(self.timesteps))
                self.initial_timestep = base_state.get("initial_timestep", None)
                # Only fallback to state file for scheduling properties if not already set on self
                if not hasattr(self, "sampling_mode") or self.sampling_mode is None:
                    self.sampling_mode = base_state.get("sampling_mode", "linear")
                if not hasattr(self, "min_interval") or self.min_interval is None:
                    self.min_interval = base_state.get("min_interval", 10)
                if not hasattr(self, "max_interval") or self.max_interval is None:
                    self.max_interval = base_state.get("max_interval", None)
                if not hasattr(self, "Nmag") or self.Nmag is None:
                    self.Nmag = base_state.get("Nmag", 10)
                if not hasattr(self, "Navg") or self.Navg is None:
                    self.Navg = base_state.get("Navg", 1)
                self._extended_sample_times = None

            if self.use_multiprocessing and self._worker_process is not None:
                self._input_queue.put(("LOAD", file_name))
                res = self._result_queue.get()
                return res
            else:
                return self._internal_load_state(file_name)
        return False

    def save_data(self, file_name="sampled_data.txt"):
        """Save sampled data as a function of time/timestep."""
        if self.use_multiprocessing and self._worker_process is not None:
            self._input_queue.put(("SAVE_DATA", file_name))
            res = self._result_queue.get()
            return res
        else:
            return self._internal_save_data(file_name)

    def _extract_frame_payload(self, frame):
        """Extract payload from frame for background process. Override in subclass."""
        return frame

    def _internal_sample(self, timestep, frame_or_payload):
        raise NotImplementedError

    def _internal_compute(self, tail_window=10, threshold=0.01):
        raise NotImplementedError

    def _internal_save_state(self, file_name):
        pass

    def _internal_load_state(self, file_name):
        return True

    def _internal_save_data(self, file_name):
        data = np.column_stack((self.timesteps, self.samples))
        if file_name.endswith(".npy"):
            np.save(file_name, data)
        else:
            np.savetxt(file_name, data, header="timestep sample")

    def close(self):
        """Clean up background worker process."""
        if self._worker_process is not None and self._worker_process.is_alive():
            self._input_queue.put(("TERMINATE", None))
            self._worker_process.join(timeout=2.0)
            if self._worker_process.is_alive():
                self._worker_process.terminate()
            self._worker_process = None

    def __del__(self):
        self.close()


class PESampler(BaseSampler):
    """Potential Energy autocorrelation sampler."""

    def __init__(
        self,
        logger,
        file_name="pe_sampler.pkl",
        sampling_mode="linear",
        min_interval=10,
        max_interval=None,
        Nmag=10,
        Navg=1,
        use_multiprocessing=False,
        auto_load=True,
    ):
        super().__init__(
            file_name=file_name,
            sampling_mode=sampling_mode,
            min_interval=min_interval,
            max_interval=max_interval,
            Nmag=Nmag,
            Navg=Navg,
            use_multiprocessing=use_multiprocessing,
            auto_load=auto_load,
        )
        self.logger = logger

        if self.auto_load and os.path.exists(self.file_name):
            self.load_state()

    def _internal_sample(self, timestep, frame):
        PE = self.logger.log()['md']['compute']["ThermodynamicQuantities"]["potential_energy"][0]
        return PE

    def _internal_compute(self, tail_window=10, threshold=0.01):
        if len(self.samples) < tail_window:
            return False, np.array(self.samples)

        samples_arr = np.array(self.samples)
        avg = samples_arr - np.mean(samples_arr)
        var = np.var(samples_arr)
        if var == 0:
            return True, np.zeros_like(samples_arr)

        ft_signal = np.fft.rfft(avg)
        convolution = ft_signal * np.conjugate(ft_signal)
        auto = np.fft.irfft(convolution) / (len(samples_arr) * var)
        last_auto = np.mean(auto[-tail_window:])

        if last_auto < threshold:
            return True, auto
        return False, auto

    def _internal_save_data(self, file_name):
        data = np.column_stack((self.timesteps, self.samples))
        if file_name.endswith(".npy"):
            np.save(file_name, data)
        else:
            np.savetxt(file_name, data, header="timestep potential_energy")


class _FSKTInternalWorker:
    def __init__(self, box, dt, ptype, file_name, kmag=1.1, sampling_mode="linear", Nmag=10, Navg=1):
        from snap_analyze import Fskt
        self.box = box
        self.dt = dt
        self.ptype = ptype
        self.file_name = file_name
        self.kmag = kmag
        self.dyn = Fskt(box, kmag=kmag, min_avg_count=1, sampling_mode=sampling_mode, Nmag=Nmag)

    def _internal_sample(self, timestep, payload):
        pos, image = payload
        self.dyn.append_timestep(timestep, pos, image)
        return None

    def _internal_compute(self, tail_window=10, threshold=0.01):
        self.dyn.compute()
        dt, Fskt_vals = self.dyn.calc_Fskt()
        if len(Fskt_vals) < tail_window:
            return False, Fskt_vals
        auto = np.mean(Fskt_vals[-tail_window:])
        return (auto < threshold), Fskt_vals

    def _internal_save_state(self, file_name):
        state_file = (file_name or self.file_name) + ".dyn"
        with open(state_file, "wb") as f:
            pickle.dump(self.dyn, f)

    def _internal_load_state(self, file_name):
        state_file = (file_name or self.file_name) + ".dyn"
        if os.path.exists(state_file):
            with open(state_file, "rb") as f:
                self.dyn = pickle.load(f)
            return True
        return False

    def save_data(self, file_name="fskt_data.txt"):
        self.dyn.compute()
        dt, Fskt_vals = self.dyn.calc_Fskt()
        data = np.column_stack((dt, Fskt_vals))
        if file_name.endswith(".npy"):
            np.save(file_name, data)
        else:
            np.savetxt(file_name, data, header="delta_t Fskt")


class FSKTSampler(BaseSampler):
    """Intermediate scattering function Fs(k,t) autocorrelation sampler."""

    def __init__(
        self,
        sim,
        ptype,
        kmag=1.1,
        file_name="fskt_sampler.pkl",
        sampling_mode="linear",
        min_interval=10,
        max_interval=None,
        Nmag=10,
        Navg=1,
        use_multiprocessing=False,
        auto_load=True,
    ):
        super().__init__(
            file_name=file_name,
            sampling_mode=sampling_mode,
            min_interval=min_interval,
            max_interval=max_interval,
            Nmag=Nmag,
            Navg=Navg,
            use_multiprocessing=use_multiprocessing,
            auto_load=auto_load,
        )
        from snap_analyze import Fskt
        self.dt = sim.operations.integrator.dt
        self.box = sim.state.box.L
        self.ptype = ptype
        self.kmag = kmag

        if not self.use_multiprocessing:
            self.dyn = Fskt(self.box, kmag=kmag, min_avg_count=1, sampling_mode=sampling_mode, Nmag=Nmag)
        else:
            self.dyn = None
            init_kwargs = {
                "box": self.box,
                "dt": self.dt,
                "ptype": ptype,
                "file_name": file_name,
                "kmag": kmag,
                "sampling_mode": sampling_mode,
                "Nmag": Nmag,
                "Navg": Navg,
            }
            self._init_multiprocessing(_FSKTInternalWorker, init_kwargs, worker_name="FSKT_Worker")
        if self.auto_load and os.path.exists(self.file_name):
            self.load_state()

    def _extract_frame_payload(self, frame):
        pos = frame.particles.position
        image = frame.particles.image
        particle_types = frame.particles.typeid
        flags = particle_types == self.ptype
        return (pos[flags], image[flags])

    def _internal_sample(self, timestep, frame_or_payload):
        if isinstance(frame_or_payload, tuple):
            pos, image = frame_or_payload
        else:
            pos = frame_or_payload.particles.position
            image = frame_or_payload.particles.image
            flags = frame_or_payload.particles.typeid == self.ptype
            pos = pos[flags]
            image = image[flags]

        self.dyn.append_timestep(timestep, pos, image)
        return None

    def _internal_compute(self, tail_window=10, threshold=0.01):
        self.dyn.compute()
        dt, Fskt_vals = self.dyn.calc_Fskt()
        if len(Fskt_vals) < tail_window:
            return False, Fskt_vals
        auto = np.mean(Fskt_vals[-tail_window:])

        if auto < threshold:
            return True, Fskt_vals
        return False, Fskt_vals

    def _internal_save_state(self, file_name):
        dyn_file = (file_name or self.file_name) + ".dyn"
        with open(dyn_file, "wb") as f:
            pickle.dump(self.dyn, f)

    def _internal_load_state(self, file_name):
        dyn_file = (file_name or self.file_name) + ".dyn"
        if os.path.exists(dyn_file):
            with open(dyn_file, "rb") as f:
                self.dyn = pickle.load(f)
            return True
        return False

    def _internal_save_data(self, file_name):
        if self.dyn is not None:
            self.dyn.compute()
            dt, Fskt_vals = self.dyn.calc_Fskt()
            data = np.column_stack((dt, Fskt_vals))
            if file_name.endswith(".npy"):
                np.save(file_name, data)
            else:
                np.savetxt(file_name, data, header="delta_t Fskt")


def minimize_autocorrelation(
    sim,
    sampler,
    threshold=0.01,
    tail_window=10,
    max_steps=None,
):
    """Run simulation while checking autocorrelation after each sample until decorrelated or max_steps reached."""
    target_max_steps = np.inf if max_steps is None else max_steps

    minimized = False
    auto = None

    if len(sampler.timesteps) > 0:
        minimized, auto = sampler.check(tail_window=tail_window, threshold=threshold)

    while not minimized and sampler.steps_ran < target_max_steps:
        step_interval = sampler.get_next_sample_interval()
        sim.run(step_interval)

        snap = sim.state.get_snapshot()
        timestep = sim.timestep
        sampler.sample(timestep, snap)

        minimized, auto = sampler.check(tail_window=tail_window, threshold=threshold)

    steps_ran = sampler.steps_ran

    if not minimized:
        limit_str = "infinite" if max_steps is None else f"{max_steps}"
        warnings.warn(f"Unable to minimize autocorrelation within {limit_str} timesteps")
    else:
        print()
        print(f"Finished minimizing autocorrelation function in {steps_ran} timesteps")
        print()

    return {
        "minimized": minimized,
        "auto": auto,
        "steps_ran": steps_ran,
        "sampler": sampler,
    }


def min_auto_FSKT(sim, ptype, kmag=1.1):
    sampler = FSKTSampler(sim, ptype=ptype, kmag=kmag)
    return sampler.sample, sampler.check


def min_auto_PE(logger):
    sampler = PESampler(logger)
    return sampler.sample, sampler.check
