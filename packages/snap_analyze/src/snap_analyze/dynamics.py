"""
Dynamic correlation functions module (Mean Squared Displacement, Intermediate Scattering Function Fs(k,t), and van Hove self-correlation).
"""

import numpy as np


class dynamics:
    """
    Computes time-dependent dynamic properties of particle trajectories.

    Supports Mean Squared Displacement (MSD), self-intermediate scattering function :math:`F_s(k, t)`,
    and van Hove self-correlation function :math:`G_s(r, t)`.

    Parameters
    ----------
    box : array_like
        Simulation box lengths (must be cubic).
    kmag : float
        Magnitude of wavevector :math:`k` for :math:`F_s(k, t)` evaluation.
    num_cells : int, optional
        Number of spatial bins for van Hove distribution computation. Default is 200.
    min_avg_count : int, optional
        Minimum number of frame pairs required to include a time delta :math:`\\Delta t` in averages. Default is 2.
    sampling_mode : str, optional
        Time interval sampling scheme, either ``"all"`` or ``"logarithmic"``. Default is ``"all"``.
    Nmag : int, optional
        Decade resolution for logarithmic sampling. Default is 10.
    """

    def __init__(self, box, kmag, num_cells=200, min_avg_count=2, sampling_mode="all", Nmag=10):
        self.box_length = box[:3]
        self.kmag = kmag
        self.num_cells = num_cells
        self.min_avg_count = min_avg_count
        self.sampling_mode = sampling_mode
        self.Nmag = Nmag
        self.unwrapped = []
        self.timesteps = []
        self.num_particles = None
        self.calculated = False

        if len(np.unique(self.box_length)) != 1:
            raise Exception("Box is not a cube")

        self.k3 = self._generate_k_vectors()
        self.pending_pairs = []
        self.dt_stats = {}
        self.dts = np.array([])
        self.Fskt = []
        self.MSDs = []
        self.vh_bins = None
        self.vh_prob = []
        return

    def _generate_k_vectors(self):
        kmag = self.kmag
        Nqs = 100

        np.random.seed(1)
        vecs = np.random.uniform(-1, 1, [Nqs, 3])
        mags = np.linalg.norm(vecs, axis=1)

        zero_flag = mags == 0
        mags = mags[~zero_flag]
        vecs = vecs[~zero_flag]

        norm_vecs = vecs[:, :] / mags[:, None]
        k3 = kmag * norm_vecs

        return k3

    def append_timestep(self, timestep, pos, img=None):
        """
        Append a frame's timestep and particle positions to the trajectory accumulator.

        Parameters
        ----------
        timestep : float
            Simulation time or step index.
        pos : ndarray
            Particle position array of shape (N, 3).
        img : ndarray, optional
            Periodic box image vector array of shape (N, 3) for unwrapping coordinates.
        """
        if self.num_particles is None:
            self.num_particles = len(pos)
        if self.num_particles != len(pos):
            raise Exception("Every timestep must have the same number of particles")

        self.timesteps.append(timestep)
        if img is not None:
            delta_u = img * self.box_length
            upos = pos + delta_u
            self.unwrapped.append(upos)
        else:
            self.unwrapped.append(pos)

        N = len(self.timesteps) - 1
        if N > 0:
            t_N = self.timesteps[N]
            min_dt = self.timesteps[1] - self.timesteps[0] if len(self.timesteps) > 1 else 1
            for j in range(N):
                dt = t_N - self.timesteps[j]
                if dt <= 0:
                    continue

                key_dt = dt
                if self.sampling_mode == "logarithmic":
                    if min_dt > 0 and dt >= min_dt:
                        k = round(np.log10(dt / min_dt) * self.Nmag)
                        target_dt = int(round(min_dt * (10.0 ** (k / self.Nmag))))
                        tolerance = max(1, int(round(0.05 * target_dt)))
                        if abs(dt - target_dt) > tolerance:
                            continue
                        key_dt = target_dt

                stat = self.dt_stats.setdefault(
                    key_dt,
                    {"count": 0, "Fskt_sum": 0.0, "MSD_sum": 0.0, "vh_sum": None, "last_end_frame": -1},
                )
                if j >= stat["last_end_frame"]:
                    self.pending_pairs.append((key_dt, N, j))
                    stat["last_end_frame"] = N

        self.calculated = False
        return

    def compute(self):
        """
        Process accumulated frames and compute MSD, Fs(k,t), and van Hove functions.
        """
        if self.calculated:
            return

        if not hasattr(self, "k3") or self.k3 is None:
            self.k3 = self._generate_k_vectors()
        if not hasattr(self, "pending_pairs"):
            self.pending_pairs = []
        if not hasattr(self, "dt_stats"):
            self.dt_stats = {}

        if not self.dt_stats and not self.pending_pairs and len(self.timesteps) > 1:
            all_dts = np.array(self.timesteps)[:, None] - np.array(self.timesteps)[None, :]
            dts = np.unique(all_dts)
            dts = dts[dts > 0]

            if self.sampling_mode == "logarithmic" and len(dts) > 0:
                min_dt = np.min(dts)
                max_dt = np.max(dts)
                if min_dt > 0 and max_dt > min_dt:
                    num_decades = np.log10(max_dt / min_dt)
                    num_points = int(round(num_decades * self.Nmag)) + 1
                    target_dts = np.unique(
                        np.round(np.logspace(np.log10(min_dt), np.log10(max_dt), num_points)).astype(int)
                    )

                    filtered_dts = []
                    for target in target_dts:
                        idx = np.argmin(np.abs(dts - target))
                        filtered_dts.append((dts[idx], target))
                    dts_mapping = dict(filtered_dts)
                else:
                    dts_mapping = {d: d for d in dts}
            else:
                dts_mapping = {d: d for d in dts}

            for raw_dt, target_dt in dts_mapping.items():
                frame_idx = np.argwhere(raw_dt == all_dts)
                to_remove = []
                for i in range(len(frame_idx)):
                    end_frame = frame_idx[i, 0]
                    if i in to_remove:
                        continue
                    for j_idx in range(i + 1, len(frame_idx)):
                        if frame_idx[j_idx, 1] < end_frame:
                            to_remove.append(j_idx)
                        else:
                            break
                frame_idx = np.delete(frame_idx, to_remove, axis=0)
                for end_f, start_f in frame_idx:
                    stat = self.dt_stats.setdefault(
                        target_dt,
                        {"count": 0, "Fskt_sum": 0.0, "MSD_sum": 0.0, "vh_sum": None, "last_end_frame": -1},
                    )
                    self.pending_pairs.append((target_dt, int(end_f), int(start_f)))
                    stat["last_end_frame"] = int(end_f)

        histMax = int(2 * self.box_length[0])
        bins = np.linspace(0, histMax, self.num_cells)
        self.vh_bins = (bins[:-1] + bins[1:]) / 2

        for dt, end_frame, start_frame in self.pending_pairs:
            upos_end = self.unwrapped[end_frame]
            upos_start = self.unwrapped[start_frame]
            delta = upos_end - upos_start
            dist = np.linalg.norm(delta, axis=-1)

            hist1D = np.histogram(dist, bins=bins)[0]

            dot = np.sum(delta[:, None, :] * self.k3[None, :, :], axis=-1)
            cdot = np.cos(dot, out=dot)
            fskt_p = float(np.mean(cdot))

            msd_p = float(np.mean(dist ** 2))

            stat = self.dt_stats[dt]
            stat["count"] += 1
            stat["Fskt_sum"] += fskt_p
            stat["MSD_sum"] += msd_p
            if stat["vh_sum"] is None:
                stat["vh_sum"] = hist1D.astype(float)
            else:
                stat["vh_sum"] += hist1D.astype(float)

        self.pending_pairs = []

        valid_dts = sorted([dt for dt, s in self.dt_stats.items() if s["count"] >= self.min_avg_count])
        self.dts = np.array(valid_dts)
        self.Fskt = [self.dt_stats[dt]["Fskt_sum"] / self.dt_stats[dt]["count"] for dt in valid_dts]
        self.MSDs = [self.dt_stats[dt]["MSD_sum"] / self.dt_stats[dt]["count"] for dt in valid_dts]

        vh_list = []
        for dt in valid_dts:
            hist_avg = self.dt_stats[dt]["vh_sum"] / self.dt_stats[dt]["count"]
            s = np.sum(hist_avg)
            if s > 0:
                hist_avg = hist_avg / s
            vh_list.append(hist_avg)
        self.vh_prob = vh_list

        self.calculated = True
        return

    def calc_MSD(self):
        """
        Get calculated Mean Squared Displacement :math:`\\langle \\Delta r^2(t) \\rangle`.

        Returns
        -------
        dts : ndarray
            Time intervals :math:`\\Delta t`.
        MSDs : list of float
            Mean squared displacement values for each :math:`\\Delta t`.
        """
        if not self.calculated:
            self.compute()
        return self.dts, self.MSDs

    def calc_vanHove(self):
        """
        Get calculated van Hove self-correlation function :math:`G_s(r, t)`.

        Returns
        -------
        dts : ndarray
            Time intervals :math:`\\Delta t`.
        vh_bins : ndarray
            Distance bin centers for :math:`r`.
        vh_prob : list of ndarray
            Normalized distance probability distribution arrays for each :math:`\\Delta t`.
        """
        if not self.calculated:
            self.compute()
        return self.dts, self.vh_bins, self.vh_prob

    def calc_Fskt(self):
        """
        Get calculated intermediate scattering function :math:`F_s(k, t)`.

        Returns
        -------
        dts : ndarray
            Time intervals :math:`\\Delta t`.
        Fskt : list of float
            Intermediate scattering function values for each :math:`\\Delta t`.
        """
        if not self.calculated:
            self.compute()
        return self.dts, self.Fskt


Fskt = dynamics


#Example from a gsd# {{{
if __name__ == "__main__":
    import sys
    import gsd.hoomd
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation

    file = "n500-dump_eta_0.25-trial_1.gsd"
    dt = 0.001
    def read():# {{{
        if gsd.version.version.split('.')[0] == '3':
            return 'r'
        else:
            return 'rb'# }}}

    dynamicType = 0
    with gsd.hoomd.open(file, mode=read()) as traj:
        frame = traj[0]
        box = frame.configuration.box

        dyn = dynamics(box, kmag = 1.1)

        for i in range(100,501,1):
            frame = traj[i]

            pos = frame.particles.position
            particle_types = frame.particles.typeid
            image = frame.particles.image

            flags = particle_types==dynamicType
            pos = pos[flags]
            image = image[flags]

            timestep = dt*frame.configuration.step
            dyn.append_timestep(timestep, pos, image)

    dyn.compute()

    dt,Fskt = dyn.calc_Fskt()
    plt.plot(dt,Fskt)
    plt.show()

    dt,Fskt = dyn.calc_MSD()
    plt.plot(dt,Fskt)
    plt.show()# }}}
