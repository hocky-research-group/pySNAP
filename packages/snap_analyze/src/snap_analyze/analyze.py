"""
Module for bond manipulation, topology splitting, and connected complex graph analysis.
"""

import sys
import numpy as np
import itertools

def split_static_dyn_bonds(bond_groups, bond_typeIDs, dyn_bond_types):
    """
    Split bond indices into static and dynamic bond subsets based on bond types.

    Parameters
    ----------
    bond_groups : array_like
        Array of shape (N_bonds, 2) containing particle index pairs defining each bond.
    bond_typeIDs : array_like
        Array of shape (N_bonds,) containing type integer IDs for each bond.
    dyn_bond_types : array_like or iterable
        Type integer IDs considered to be dynamic bonds.

    Returns
    -------
    stat_bonds : ndarray
        Bond particle pairs belonging to static bond types.
    dyn_bonds : ndarray
        Bond particle pairs belonging to dynamic bond types.
    """
    bond_groups = np.asarray(bond_groups)
    if not np.iterable(dyn_bond_types):
        dyn_bond_types = list(dyn_bond_types)
    dyn_bond_types = np.asarray(dyn_bond_types)
    if len(dyn_bond_types) == 0:
        return bond_groups, []

    try:
        dyn_bond_types.astype(bond_groups.dtype)
        bond_groups.astype(dyn_bond_types.dtype)
    except Exception:
        sys.tracebacklimit = 0
        raise Exception("bond_typeIDs and dynamic_bond_types should be convertible to their counterpart types")

    dyn_bonds = np.any(bond_typeIDs[:, None] == dyn_bond_types[None, :], axis=1)
    stat_bonds = ~dyn_bonds

    dyn_bonds = bond_groups[dyn_bonds]
    stat_bonds = bond_groups[stat_bonds]

    return stat_bonds, dyn_bonds


def get_complexes(num_particles, particle_typeIDs, bond_groups, return_type_info=False):
    """
    Identify connected clusters (complexes) of bonded particles using graph analysis.

    Parameters
    ----------
    num_particles : int
        Total number of particles in the system.
    particle_typeIDs : array_like
        Array of shape (num_particles,) containing particle type IDs.
    bond_groups : array_like
        Array of shape (N_bonds, 2) containing particle index pairs defining bonds.
    return_type_info : bool, optional
        If True, returns additional complex classification type IDs and ordered unique types. Default is False.

    Returns
    -------
    comp_IDs : ndarray
        Array of length `num_particles` mapping each particle index to its assigned complex ID.
    type_info : tuple of (ndarray, list), optional
        Only returned if `return_type_info` is True. Tuple containing:
        - `comp_typeIDs`: Array mapping each complex to its complex-type ID.
        - `ordered_comp_types`: List of unique particle-type tuples defining each complex type.
    """
    import networkx as nx
    graph = nx.Graph()
    graph.add_nodes_from(range(num_particles))
    graph.add_edges_from(bond_groups)
    complexes = list(nx.connected_components(graph))
    num_complexes = len(complexes)

    comp_IDs = np.zeros(num_particles, dtype=int)
    for i, comp in enumerate(complexes):
        comp = sorted(comp)
        complexes[i] = comp
        comp_IDs[comp] = i

    if return_type_info:
        comp_typeIDs = np.zeros(num_complexes, dtype=int)
        comp_types = set()
        ordered_comp_types = list()
        for i, comp in enumerate(complexes):
            comp_type = tuple(particle_typeIDs[comp])
            if comp_type in comp_types:
                comp_typeID = len(comp_types) - 1
            else:
                comp_typeID = len(comp_types)
                comp_types.add(comp_type)
                ordered_comp_types.append(comp_type)
            comp_typeIDs[i] = comp_typeID
        return comp_IDs, (comp_typeIDs, ordered_comp_types)

    return comp_IDs


def convert_id_to_complex_id(particle_ids, complex_IDs):
    """
    Map particle indices to their corresponding complex IDs.

    Parameters
    ----------
    particle_ids : array_like
        Particle indices to look up.
    complex_IDs : array_like
        Array mapping particle index -> complex ID.

    Returns
    -------
    complex_ids : ndarray
        Complex IDs corresponding to the given particle indices.
    """
    return complex_IDs[particle_ids]


def convert_id_to_type(particle_ids, particle_types):
    """
    Map particle indices to their corresponding particle types.

    Parameters
    ----------
    particle_ids : array_like
        Particle indices to look up.
    particle_types : array_like
        Array mapping particle index -> particle type.

    Returns
    -------
    types : ndarray
        Particle types corresponding to the given particle indices.
    """
    return particle_types[particle_ids]


def remove_bond_intermediates(bond_groups, particle_typeIDs, to_remove, return_removed_bonds=False):
    """
    Remove specified intermediate particle types from bond graphs, connecting remaining endpoints directly.

    Parameters
    ----------
    bond_groups : array_like
        Array of shape (N_bonds, 2) defining existing bonds.
    particle_typeIDs : array_like
        Array of shape (num_particles,) containing particle type IDs.
    to_remove : int or iterable of int
        Particle type ID(s) to remove from the bond network.
    return_removed_bonds : bool, optional
        If True, also returns a dictionary detailing removed intermediate bond connections. Default is False.

    Returns
    -------
    ret_bonds : ndarray
        Updated bond index pairs after removing intermediate particles.
    removed_bonds_dict : dict, optional
        Returned only if `return_removed_bonds` is True.
    """
    removed_bonds_dict = None
    if np.iterable(to_remove):
        if len(to_remove) > 1:
            recursive_results = remove_bond_intermediates(
                bond_groups, particle_typeIDs, to_remove[1:], return_removed_bonds=return_removed_bonds
            )
            if return_removed_bonds:
                bonded_groups, removed_bonds_dict = recursive_results
            else:
                bonded_groups = recursive_results

        to_remove = to_remove[0]

    bond_groupTypes = convert_id_to_type(bond_groups, particle_typeIDs)
    to_remove_flags = bond_groupTypes[:, :] == to_remove
    to_remove_IDs, counts = np.unique(bond_groups[to_remove_flags], return_counts=True)
    final_num_bonds = int(np.sum(counts * (counts - 1) / 2))

    count = 0
    ret_bonds = np.zeros([final_num_bonds, 2])
    if return_removed_bonds:
        removed_bonds = dict()

    for rid in to_remove_IDs:
        has_rid_flag = np.any(bond_groups == rid, axis=-1)
        bond_group_with_rid = bond_groups[has_rid_flag]
        bonded_to = bond_group_with_rid[bond_group_with_rid != rid]
        if return_removed_bonds:
            removed_bonds[rid] = bonded_to
        remaining_ids, counts = np.unique(bonded_to, return_counts=True)

        new_bonds = itertools.combinations(remaining_ids, 2)
        for new_bond in new_bonds:
            ret_bonds[count] = new_bond
            count += 1

        multi_flags = counts > 1
        for id, c in zip(remaining_ids[multi_flags], counts[multi_flags]):
            for i in range(c - 1):
                ret_bonds[count] = id, id
                count += 1
    if return_removed_bonds:
        if removed_bonds_dict is None:
            removed_bonds_dict = {to_remove: removed_bonds}
        else:
            removed_bonds_dict[to_remove] = removed_bonds

        return ret_bonds, removed_bonds_dict
    return ret_bonds


