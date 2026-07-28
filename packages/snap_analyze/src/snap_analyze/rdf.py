"""
Radial Distribution Function (RDF, g(r)) calculation module for 2D and 3D systems.
"""

import numpy as np
import itertools
from .neighbor_list import NeighborList


class RDF:
    """
    Computes the radial distribution function :math:`g(r)` for 2D or 3D particle positions.

    Parameters
    ----------
    box_length : array_like
        Dimensions of the simulation box.
    bin_edges : array_like
        1D array specifying distance histogram bin boundaries for :math:`g(r)`.
    """

    def __init__(self, box_length, bin_edges):
        self.dim_flags = ~(box_length == 0)
        box_length = box_length[self.dim_flags]
        self.dim = np.count_nonzero(self.dim_flags)

        self.nlist = NeighborList(np.max(bin_edges), box_length)
        self.box_length = box_length
        self.half_box_length = box_length / 2
        self.bin_edges = bin_edges
        self.bins = np.zeros(len(bin_edges) - 1)

        if self.dim == 2:
            self.bin_volume = np.pi * (self.bin_edges[1:] ** 2 - self.bin_edges[:-1] ** 2)
        elif self.dim == 3:
            self.bin_volume = 4 / 3 * np.pi * (self.bin_edges[1:] ** 3 - self.bin_edges[:-1] ** 3)
        self.num_frames = 0
        self.ideal_density = None
        self.num_particles = None

    def _getWrappedDelta(self, pos1, pos2):
        delta = pos1 - pos2
        signs = np.sign(delta)
        delta = np.abs(delta)
        wrap_flag = np.argwhere(delta > self.half_box_length).T
        delta[*wrap_flag] = self.box_length[wrap_flag[-1]] - delta[*wrap_flag]
        signs[*wrap_flag] *= -1
        return delta * signs

    def append_sample(self, pos):
        """
        Accumulate a frame of particle positions into the RDF distance histogram.

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

        if self.num_particles is None:
            self.num_particles = num_particles
        elif self.num_particles != num_particles:
            raise Exception(
                f"Number of particles should not change from timestep to timestep:\n"
                + f"\tOrignal number: {self.num_particles}\n\tNew number: {num_particles}"
            )
        ideal_density = num_particles / np.prod(self.box_length)
        if self.ideal_density is None:
            self.ideal_density = ideal_density
        elif self.ideal_density != ideal_density:
            raise Exception(
                f"Particle density should not change from timestep to timestep:\n"
                + f"\tOrignal density: {self.ideal_density}\n\tNew density: {ideal_density}"
            )
        P1, P2 = self.nlist(pos)
        self.num_frames += 1
        delta = self._getWrappedDelta(pos[P1], pos[P2])
        dist = np.linalg.norm(delta, axis=-1)
        hist, edges = np.histogram(dist, self.bin_edges)
        self.bins += 2 * hist

    def compute(self, return_bin_mids=True, norm_density=True, norm_volume=True):
        """
        Compute the averaged normalized radial distribution function :math:`g(r)`.

        Parameters
        ----------
        return_bin_mids : bool, optional
            If True (default), returns `(bin_mids, g_r)`. If False, returns only `g_r`.
        norm_density : bool, optional
            If True (default), normalizes by the ideal gas particle density.
        norm_volume : bool, optional
            If True (default), normalizes by spherical shell volume.

        Returns
        -------
        bin_mids : ndarray, optional
            Radial distance bin midpoints (if `return_bin_mids` is True).
        g_r : ndarray
            The calculated radial distribution function values.
        """
        rdf = self.bins / self.num_frames / self.num_particles
        if norm_density:
            rdf /= self.ideal_density
        if norm_volume:
            rdf /= self.bin_volume
        bin_mids = (self.bin_edges[:-1] + self.bin_edges[1:]) / 2
        if return_bin_mids:
            return bin_mids, rdf
        else:
            return rdf

