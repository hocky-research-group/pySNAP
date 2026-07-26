import itertools
import numpy as np


class Container:
    def __init__(self, box_length, dim):
        self.maxSite = box_length
        self.sites = dict()
        self.dim = dim
        self.count = 0

    def __getitem__(self, index):
        if index.shape[1] != self.dim:
            raise ValueError(f"Indices must match box dimension ({self.dim})")
        if np.any(index > self.maxSite):
            raise ValueError("Cannot have index larger than boxsize")
        for i, ind in enumerate(index):
            flag = self.sites.get(tuple(ind), False)
            if flag:
                return flag
        return False

    def set(self, index):
        if index.shape[1] != self.dim:
            raise ValueError(f"Indices must match box dimension ({self.dim})")
        if np.any(index > self.maxSite):
            raise ValueError("Cannot have index larger than boxsize")
        for i, ind in enumerate(index):
            self.sites[tuple(ind)] = True
        self.count += i + 1
        return

    def vol_frac(self):
        return self.count / np.prod(self.maxSite)


class OverlapChecker:
    def __init__(self, box_length, cell_size, dim=None):
        self.nlist = dict()
        self.diameters = []
        box_length = np.copy(box_length)
        cell_size = np.copy(cell_size)
        if np.isscalar(box_length) and dim is None:
            raise Exception("If box_length is a scalar, dim must be specified")
        elif np.isscalar(box_length):
            self.dim = dim
            box_length = np.ones(dim) * box_length
        else:
            self.dim = len(box_length)
            box_length = np.asarray(box_length)

        if np.any(box_length == 0):
            flag = box_length == 0
            box_length[flag] = cell_size

        self.num_boxes = (box_length / cell_size).astype(int)
        self.cell_size = box_length / self.num_boxes
        self.box_length = box_length
        self.half_box = box_length / 2
        self.count_checks = 0
        self.count_adds = 0

    def has_overlap(self, mol_pos, mol_d):
        if np.any(mol_pos < 0):
            mol_pos = mol_pos + self.half_box
        if np.any(mol_pos < 0) or np.any(mol_pos > self.box_length):
            raise Exception("Cannot check particles that are out of the box")
        if np.any(mol_d != 1):
            is_colloid = True
        else:
            is_colloid = False
        idxs = (mol_pos / self.cell_size).astype(int)
        offset = np.array([np.arange(-1, 2) for i in range(self.dim)])
        L = self.box_length
        for idx, pos1, d1 in zip(idxs, mol_pos, mol_d):
            offsets = (idx[:, None] + offset) % self.num_boxes
            for off in itertools.product(*offsets):
                index = tuple(off)
                if index not in self.nlist:
                    continue
                for pos2, d2 in self.nlist[index]:
                    delta = pos1 - pos2
                    p = False
                    delta -= np.round(delta / L) * L
                    dist = np.sqrt(delta[0]**2 + delta[1]**2 + delta[2]**2)
                    dc = (d1 + d2) / 2  # contact distance
                    if dist < dc:
                        return True
        self.count_checks += 1
        return False

    def add(self, mol_pos, mol_d):
        if np.any(mol_pos < 0):
            mol_pos = mol_pos + self.half_box
        if np.any(mol_pos < 0) or np.any(mol_pos > self.box_length):
            raise Exception("Cannot add particles that are out of the box")
        idxs = (mol_pos / self.cell_size).astype(int)
        for idx, pos, d in zip(idxs, mol_pos, mol_d):
            index = tuple(idx)
            if index not in self.nlist:
                self.nlist[index] = []
            self.nlist[tuple(idx)].append([pos, d])
        self.count_adds += 1
        return True
