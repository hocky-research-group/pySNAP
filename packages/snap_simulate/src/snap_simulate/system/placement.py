import numpy as np
from snap_simulate.tools import dict_defines


def place_simple_cubic(box, sites, mols):
    num_mol = 0
    num_types = 0
    max_size = np.zeros(3)
    box_length = box["box_length"]
    if dict_defines(box, "placement_spacing"):
        spacing = np.array(box["placement_spacing"])
    else:
        spacing = np.array([None, None, None])
    needs_spacing = spacing == None
    min_N = np.inf

    dim = box["dimensions"]
    for name, mol in mols.items():
        min_N = np.min([min_N, mol["num_molecules"]])
        num_mol += mol["num_molecules"]
        num_types += 1
        grid = mol["grid"]
        size = np.max(grid, axis=0) - np.min(grid, axis=0)
        max_size[max_size < size] = size[max_size < size]

    min_N = int(min_N)
    num_lattice = np.zeros_like(spacing, dtype=int) - 1
    num_lattice[~needs_spacing] = box_length[~needs_spacing] / spacing[~needs_spacing]
    num_lattice[num_lattice == 0] = 1
    N_set = np.prod(num_lattice[~needs_spacing])

    if np.any(needs_spacing):
        aspect_ratio = box_length[needs_spacing] / np.min(box_length[needs_spacing])
        N_not_set = num_mol / N_set
        n = (N_not_set * np.prod(aspect_ratio))**(1 / len(aspect_ratio))
        num_lattice[needs_spacing] = np.ceil(n / aspect_ratio).astype(int)
    lattice_size = box_length / num_lattice
    if np.any(max_size > lattice_size):
        raise Exception("Unable to place molecules in a simple cubic lattice. "
                        "Lattice size is not large enough for molecules")
    lattice_centers = [np.linspace(lattice_size[i] / 2,
                                   box_length[i] - lattice_size[i] / 2,
                                   num_lattice[i]) for i in range(dim)]
    lattice_sites = np.array(np.meshgrid(*lattice_centers)).T
    all_lattice = lattice_sites
    lattice_sites = all_lattice.reshape(np.prod(all_lattice.shape[:dim]), 3)

    positions = dict()
    position_index = np.arange(num_mol)

    if dict_defines(box, "placement_order"):
        if box['placement_order'] == "random":
            np.random.shuffle(position_index)
        elif box['placement_order'] == "alternating":
            N_not_set = dict()
            index_by_mol = dict()
            temp_index = np.arange(np.prod(all_lattice.shape[:-1])).reshape(all_lattice.shape[:-1])
            i = -1
            for name, mol in mols.items():
                i += 1
                checker_flags = ~((np.indices(all_lattice.shape[:-1]).sum(axis=0) + i) % num_types).astype(bool)
                index_by_mol[name] = temp_index[checker_flags][:min_N]
                if min_N < mol["num_molecules"]:
                    N_not_set[name] = mol["num_molecules"] - min_N
            N_set = min_N * len(mols)
            for name, N_to_set in N_not_set.items():
                N_new = N_set + N_to_set
                index_by_mol[name] = np.concatenate([index_by_mol[name], np.arange(N_set, N_new)])
                N_set = N_new
            position_index = np.concatenate(list(index_by_mol.values()))

    N_total = 0
    for name, mol in mols.items():
        name_plural = name + ('s' if name[-1] != 's' else '')
        N = mol["num_molecules"]

        print(f"Placing {N} {name_plural} in a simple cubic lattice")

        mol_sites = lattice_sites[position_index[N_total:N_total + N]]
        positions[name] = []
        for site in mol_sites:
            part_pos = site + mol["particle_positions"]
            part_pos -= np.floor(part_pos / box_length) * box_length
            if sites.has_overlap(part_pos, mol["diameters"]):
                raise Exception(f"Unable to place {name} in the Simple Cubic lattice. "
                                "Atleast one particle has been placed in a lattice site")
            sites.add(part_pos, mol["diameters"])
            positions[name] += (part_pos - box_length / 2).tolist()
        N_total += N

    return positions


def place_random(box, sites, mols, try_limit=1000):
    positions = dict()
    box_length = box['box_length']
    dim = box["dimensions"]

    mol_order = list(mols.items())
    mol_order = sorted(mol_order, key=lambda x: x[1]["vol"], reverse=True)
    for name, mol in mol_order:
        N = mol["num_molecules"]
        name_plural = name + ('s' if name[-1] != 's' else '')
        particle_positions = mol["particle_positions"]
        mol_dia = mol["diameters"]
        positions[name] = []

        if N == 0:
            print(f"Not placing {name_plural}- zero requested")
            continue
        print(f"Placing {N} {name_plural} randomly:")
        for i in range(N):
            tries = 0
            print_freq = max(int(N / 10), 1)
            if i % print_freq == 0:
                print(f"    {(i + 1) / N * 100:.0f}% of {name_plural} placed")
            placed = False
            while tries < try_limit:
                tries += 1

                rand_pos = np.random.rand(dim) * box_length
                pos = particle_positions + rand_pos
                pos -= np.floor(pos / box_length) * box_length

                if sites.has_overlap(pos, mol_dia):
                    continue

                placed = True
                sites.add(pos, mol_dia)
                part_pos = pos - box_length / 2
                positions[name] += part_pos.tolist()
                break
            if not placed:
                raise Exception(f"Unable to place {name} {i} out of {N} after {try_limit} attempts")
    return positions
