"""
Particle clustering, cluster size distribution, center of mass, gyration tensor, and shape anisotropy analysis module.
"""

import numpy as np
import itertools
from .neighbor_list import NeighborList


class Clusters:
    """
    Identifies particle clusters based on a distance cutoff `r_max` and computes geometric properties.

    Parameters
    ----------
    r_max : float
        Maximum distance cutoff for considering two particles as part of the same cluster.
    box_length : array_like
        Length of the simulation box in each dimension.
    """

    def __init__(self, r_max, box_length):
        self.dim_flags = ~(box_length == 0)
        box_length = box_length[self.dim_flags]
        self.box_length = box_length
        self.half_box_length = box_length / 2
        self.dim = np.count_nonzero(self.dim_flags)
        self.nlist = NeighborList(r_max, box_length)
        self.r_max = r_max

        self.cluster_counts = []
        self.all_clusters = []
        self.time_frames = 0
        self.max_size = 0

    def _getWrappedDelta(self, pos1, pos2):
        delta = pos1 - pos2
        signs = np.sign(delta)
        delta = np.abs(delta)
        wrap_flag = np.argwhere(delta > self.half_box_length).T
        delta[*wrap_flag] = self.box_length[wrap_flag[-1]] - delta[*wrap_flag]
        signs[*wrap_flag] *= -1
        return delta * signs

    def append(self, pos):
        """
        Process a new frame of particle positions and update cluster identification.

        Parameters
        ----------
        pos : ndarray
            Particle position array of shape (N, d).
        """
        if len(pos.shape) == 2:
            num_particles = pos.shape[0]
            dims = pos.shape[1]
            pos = pos[:, self.dim_flags]
        else:
            raise Exception(
                "Positions should be passed to the RDF as an Nxd array where N is the number of particles and d is the dimension"
            )
        self.pos = pos

        P1, P2 = self.nlist(pos)
        delta = self._getWrappedDelta(pos[P1], pos[P2])
        dist = np.linalg.norm(delta, axis=-1)

        flag = dist <= self.r_max
        P1 = P1[flag]
        P2 = P2[flag]

        clusters = [[i] for i in range(num_particles)]
        cids = [i for i in range(num_particles)]

        for p1, p2 in zip(P1, P2):
            c1 = cids[p1]
            c2 = cids[p2]

            if c1 == c2:
                continue

            clusters[c1] += clusters[c2]
            removed_cluster = clusters[c2]
            for p3 in removed_cluster:
                cids[p3] = c1
            clusters[c2] = []

        clusters = [s for s in clusters if len(s) != 0]
        cluster_sizes = [len(cluster) for cluster in clusters]
        cluster_counts = np.bincount(cluster_sizes)[1:]

        self.clusters = clusters
        self.all_clusters.append(clusters)
        self.cluster_counts.append(cluster_counts)
        self.max_size = max(self.max_size, len(cluster_counts))
        self.time_frames += 1
        return

    def get_average_distribution(self):
        """
        Compute frame-averaged cluster size probability distribution.

        Returns
        -------
        dist : ndarray
            Averaged counts of clusters indexed by size (1-based index).
        """
        total = np.zeros(self.max_size)
        for count in self.cluster_counts:
            total[: len(count)] += count
        return total / self.time_frames

    def get_last_clusters(self):
        """
        Get identified cluster lists from the most recent frame.

        Returns
        -------
        clusters : list of list of int
            List of particle indices for each cluster in the last frame.
        """
        return self.all_clusters[-1]

    def get_all_clusters(self):
        """
        Get identified cluster lists for all appended frames.

        Returns
        -------
        all_clusters : list of list of list of int
            Cluster particle indices across all frames.
        """
        return self.all_clusters

    def get_all_distribution(self):
        """
        Get raw cluster size distribution counts for all frames.

        Returns
        -------
        cluster_counts : list of ndarray
            Size distribution counts per frame.
        """
        return self.cluster_counts

    def calc_center_mass(self, pos=None, clusters=None):
        """
        Compute center of mass for each cluster.

        Parameters
        ----------
        pos : ndarray, optional
            Particle positions array. If None, uses the last appended frame.
        clusters : list of list of int, optional
            Cluster definitions. If None, uses the last appended frame's clusters.

        Returns
        -------
        center_mass : ndarray
            Center of mass positions of shape `(N_clusters, d)`.
        """
        if pos is None and clusters is None:
            pos = self.pos
            clusters = self.clusters
        elif clusters is None or pos is None:
            raise Exception("'Clusters.calc_center_mass', must take both pos and clusters or neither")

        center_mass = []
        for s in clusters:
            cm = np.sum(pos[s, :], axis=0) / len(s)
            center_mass.append(cm)
        return np.array(center_mass)

    def calc_gyration_tensor(self, pos=None, clusters=None):
        """
        Compute radius of gyration tensor for each cluster.

        Parameters
        ----------
        pos : ndarray, optional
            Particle positions array.
        clusters : list of list of int, optional
            Cluster definitions.

        Returns
        -------
        all_S : list of ndarray
            List of 2D gyration tensor matrices for each cluster.
        """
        if pos is None and clusters is None:
            pos = self.pos
            clusters = self.clusters
        elif clusters is None or pos is None:
            raise Exception("'Clusters.calc_center_mass', must take both pos and clusters or neither")

        center_mass = self.calc_center_mass(pos, clusters)
        all_S = []
        for cm_s, s in zip(center_mass, clusters):
            pos_s = pos[s, :] - cm_s
            S = pos_s[:, :, None] * pos_s[:, None, :]
            S = np.sum(S, axis=0) / pos_s.shape[0]
            all_S.append(S)
        return all_S

    def calc_anisotropy(self, pos=None, clusters=None):
        """
        Compute relative shape anisotropy :math:`\\kappa^2` as a function of cluster size.

        Parameters
        ----------
        pos : ndarray, optional
            Particle positions.
        clusters : list of list of int, optional
            Cluster definitions.

        Returns
        -------
        ks : ndarray
            Average shape anisotropy values indexed by cluster size.
        """
        if pos is None and clusters is None:
            pos = self.pos
            clusters = self.clusters
        elif clusters is None or pos is None:
            raise Exception("'Clusters.calc_center_mass', must take both pos and clusters or neither")

        clusters = [s for s in clusters if len(s) > 2]
        cluster_size = [len(s) for s in clusters]
        S = self.calc_gyration_tensor(pos, clusters)
        ks = []
        for Si in S:
            val, vec = np.linalg.eig(Si)
            ksq = 1.5 * np.sum(val ** 2) / np.sum(val) ** 2 - 0.5
            ks.append(ksq)
        ks = np.bincount(cluster_size, weights=ks) / np.bincount(cluster_size)
        return ks

