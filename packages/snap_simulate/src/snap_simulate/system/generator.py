import gsd.hoomd
import numpy as np
from snap_simulate.tools import dict_defines
from snap_simulate.system.spatial import Container, OverlapChecker
from snap_simulate.system.placement import place_simple_cubic, place_random
from snap_simulate.system.rigid import build_rigid, check_rigid
from snap_simulate.system.molecules import MOLECULE_TEMPLATES
from snap_simulate.system.box import calc_box_length
from snap_simulate.system.molecules.resolver import (
    resolve_molecule_details,
    compute_num_molecules,
    recurse_compute_num_molecules,
    create_molecules_from_template,
    compute_group_nums,
)


def gen_mixture(params, outfile=None):
    Particles = params["particles"]

    if "bonds" in params:
        bond_types = params["bonds"]["types"]
    else:
        bond_types = []
    if "angles" in params:
        angle_types = params["angles"]["types"]
    else:
        angle_types = []

    if "dihedrals" in params:
        dihedral_types = params["dihedrals"]["types"]
    else:
        dihedral_types = []

    Molecules = params["molecules"]
    Box = params["box"]
    Dim = Box["dimensions"]

    has_rigid = check_rigid(Molecules)

    s = gsd.hoomd.Frame()

    s.particles.N = 0
    s.particles.types = Particles["types"]
    s.particles.typeid = []
    s.particles.diameter = []
    s.particles.mass = []
    s.particles.position = []
    thermalize = []

    s.bonds.N = 0
    s.bonds.types = bond_types
    s.bonds.typeid = []
    s.bonds.group = []

    s.angles.N = 0
    s.angles.types = angle_types
    s.angles.typeid = []
    s.angles.group = []

    s.dihedrals.N = 0
    s.dihedrals.types = angle_types
    s.dihedrals.typeid = []
    s.dihedrals.group = []

    if has_rigid:
        s.particles.angmom = []
        s.particles.body = []
        s.particles.moment_inertia = []
        s.particles.orientation = []
        body_count = 0
        is_constituent = []

    Molecules = resolve_molecule_details(Molecules, Particles)
    for name, mol in Molecules.items():
        N = mol["num_molecules"]
        N0 = s.particles.N

        typeids = mol["particle_typeid"]
        num_particles = len(typeids)

        masses = np.array(Particles["mass"])[typeids].tolist()
        mol["masses"] = np.array(masses)
        diameters = np.array(Particles["diameters"])[typeids].tolist()
        mol["diameters"] = np.array(diameters)

        s.particles.N += N * num_particles
        s.particles.typeid += N * typeids
        s.particles.diameter += N * diameters
        s.particles.mass += N * masses

        if has_rigid:
            rigid_info = build_rigid(mol, Particles["mass"], Particles["diameters"])
            angmom, body, moment_inertia, orientation = rigid_info
            s.particles.angmom += N * angmom
            new_bodies = body[0] == 0
            if new_bodies:
                full_body = []
                for i in range(N):
                    full_body += (np.array(body) + body_count).tolist()
                    body_count += 1
                is_constituent += N * ([False] + (num_particles - 1) * [True])
            else:
                full_body = N * body
                is_constituent += N * num_particles * [False]

            s.particles.body += full_body
            s.particles.moment_inertia += N * moment_inertia
            s.particles.orientation += N * orientation

        particle_positions = mol["particle_positions"]

        min_pos = np.min(particle_positions, axis=0)
        max_pos = np.max(particle_positions, axis=0)
        mol["vol"] = np.sum((min_pos - max_pos)**2)

        min_grid = (min_pos - 0.5).astype(int)
        max_grid = (max_pos + 0.5).astype(int) + 1
        grid = np.array([min_grid, max_grid]).T

        mol_grid = np.array([[i, j, k] for i in range(*grid[0])
                                     for j in range(*grid[1])
                                     for k in range(*grid[2])])
        mol["grid"] = mol_grid

        if "bond_groups" in mol:
            bonds = mol["bond_groups"]
            s.bonds.N += N * len(bonds)
            s.bonds.typeid += N * mol["bond_typeid"]
            groups = []
            for i in range(N):
                groups += list(np.array(bonds) + i * num_particles + N0)
            s.bonds.group += groups

        if "angle_groups" in mol:
            angles = mol["angle_groups"]
            s.angles.N += N * len(angles)
            s.angles.typeid += N * mol["angle_typeid"]
            groups = []
            for i in range(N):
                groups += list(np.array(angles) + i * num_particles + N0)
            s.angles.group += groups

        if "dihedral_groups" in mol:
            dihedrals = mol["dihedral_groups"]
            s.dihedrals.N += N * len(dihedrals)
            s.dihedrals.typeid += N * mol["dihedral_typeid"]
            groups = []
            for i in range(N):
                groups += list(np.array(dihedrals) + i * num_particles + N0)
            s.dihedrals.group += groups

        if "thermalize" in mol:
            thermalize += [mol["thermalize"] for _ in range(N * num_particles)]
        else:
            thermalize += [False for _ in range(N * num_particles)]

    s.configuration.dimensions = Dim

    box_length = calc_box_length(Box, Molecules, Particles)
    box_length = np.array(box_length)

    Box['box_length'] = box_length
    Box['max'] = box_length / 2
    Box['min'] = -box_length / 2

    placement_style = Box["placement_style"]
    sites = Container(box_length, Dim)
    sites = OverlapChecker(box_length, max(Particles["diameters"]))
    if not isinstance(placement_style, dict):
        placement_style = {placement_style: Molecules}
    else:
        for style, names in placement_style.items():
            placement_style[style] = {name: Molecules[name] for name in names}

    pos = dict()
    if "simple_cubic" in placement_style:
        temp_p = place_simple_cubic(Box, sites, placement_style["simple_cubic"])
        pos.update(temp_p)
    if "random" in placement_style:
        temp_p = place_random(Box, sites, placement_style["random"])
        pos.update(temp_p)

    for name, mol in Molecules.items():
        s.particles.position += pos[name]

    s.configuration.step = 0
    if "tilt" in Box:
        tilt = Box['tilt']
    else:
        tilt = np.zeros(Dim)
    box = np.concatenate([box_length, tilt])
    s.configuration.box = box

    s.bonds.group = np.array(s.bonds.group, dtype=int)
    s.angles.group = np.array(s.angles.group, dtype=int)
    s.dihedrals.group = np.array(s.dihedrals.group, dtype=int)

    s.particles.image = np.zeros((s.particles.N, Dim))
    s.particles.velocity = np.zeros((s.particles.N, Dim))
    if np.count_nonzero(thermalize) != 0:
        v = np.random.normal(0.0, 1.0, size=(np.count_nonzero(thermalize), Dim))
        v -= np.mean(v, axis=0)
        s.particles.velocity[thermalize] = v

    if has_rigid:
        sort_flags, old_to_new_idx = calc_reorder_idx(is_constituent)
        s.particles.typeid = np.array(s.particles.typeid)[sort_flags]
        s.particles.diameter = np.array(s.particles.diameter)[sort_flags]
        s.particles.mass = np.array(s.particles.mass)[sort_flags]
        s.particles.position = np.array(s.particles.position)[sort_flags]
        s.particles.angmom = np.array(s.particles.angmom)[sort_flags]
        s.particles.body = np.array(s.particles.body)[sort_flags]
        s.particles.moment_inertia = np.array(s.particles.moment_inertia)[sort_flags]
        s.particles.orientation = np.array(s.particles.orientation)[sort_flags]
        s.particles.velocity = np.array(s.particles.velocity)[sort_flags]

        s.bonds.group = old_to_new_idx[s.bonds.group]
        s.angles.group = old_to_new_idx[s.angles.group]
        s.dihedrals.group = old_to_new_idx[s.dihedrals.group]

    if outfile is not None:
        with gsd.hoomd.open(name=outfile, mode="w") as f:
            f.append(s)
    return s


def calc_reorder_idx(is_constituent):
    N = len(is_constituent)
    new_idx = np.zeros(N, dtype=int)
    first_count = 0
    last_count = 0
    for i in range(N):
        if not is_constituent[i]:
            new_idx[i] = first_count
            first_count += 1
        else:
            new_idx[i] = last_count
            last_count += 1
    new_idx[is_constituent] += first_count
    sort_flags = np.argsort(new_idx)
    return sort_flags, new_idx

