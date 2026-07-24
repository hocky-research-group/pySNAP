import sys
import numpy as np
import itertools
def split_static_dyn_bonds(bond_groups, bond_typeIDs, dyn_bond_types):# {{{
    ustr = "Usage:splitStatDynBond(bond_groups(list len num_bonds),"\
                                 +"bond_typeIDs(list len num_bonds),"\
                                 +"dyn_bond_types(list len num_dynbond_types))"

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
        raise Exception("bond_typeIDs and dynamic_bond_types should be convertible to their couterpart types")

    dyn_bonds = np.any(bond_typeIDs[:,None] == dyn_bond_types[None,:],axis = 1)
    stat_bonds = ~dyn_bonds

    dyn_bonds = bond_groups[dyn_bonds]
    stat_bonds = bond_groups[stat_bonds]

    return stat_bonds, dyn_bonds# }}}
def get_complexes(num_particles,particle_typeIDs,bond_groups,return_type_info = False):# {{{
    import networkx as nx
    graph = nx.Graph()
    graph.add_nodes_from(range(num_particles))
    graph.add_edges_from(bond_groups)
    complexes = list(nx.connected_components(graph))
    num_complexes = len(complexes)

    comp_IDs = np.zeros(num_particles).astype(int)
    for i,comp in enumerate(complexes):
        comp = sorted(comp)
        complexes[i] = comp
        comp_IDs[comp] = i

    if return_type_info:
        comp_typeIDs = np.zeros(num_complexes).astype(int)
        comp_types = set()
        ordered_comp_types = list()
        for i,comp in enumerate(complexes):
            comp_type = tuple(particle_typeIDs[comp])
            if comp_type in comp_types:
                comp_typeID = len(comp_types)-1
            else:
                comp_typeID = len(comp_types)
                comp_types.add(comp_type)
                ordered_comp_types.append(comp_type)
            comp_typeIDs[i] = comp_typeID
        return comp_IDs, (comp_typeIDs, ordered_comp_types)

    return comp_IDs# }}}
def convert_id_to_complex_id(particle_ids,complex_IDs):# {{{
    return complex_IDs[particle_ids]# }}}
def convert_id_to_type(particle_ids,particle_types):# {{{
    return particle_types[particle_ids]# }}}
def remove_bond_intermediates(bond_groups,particle_typeIDs,to_remove,return_removed_bonds = False):# {{{

    removed_bonds_dict = None
    if np.iterable(to_remove):
        if len(to_remove) > 1:
            recursive_results = remove_bond_intermediates(bond_groups,particle_typeIDs,to_remove[1:],return_removed_bonds = return_removed_bonds)
            if return_removed_bonds:
                bonded_groups,removed_bonds_dict = recursive_results
            else:
                bonded_groups = recursive_results

        to_remove = to_remove[0]

    bond_groupTypes = convert_id_to_type(bond_groups,particle_typeIDs)
    to_remove_flags = bond_groupTypes[:,:] == to_remove
    to_remove_IDs, counts = np.unique(bond_groups[to_remove_flags],return_counts=True)
    final_num_bonds = int(np.sum(counts*(counts-1)/2))

    count = 0
    ret_bonds = np.zeros([final_num_bonds,2])
    if return_removed_bonds:
        removed_bonds = dict()
    
    for rid in to_remove_IDs:
        has_rid_flag = np.any(bond_groups == rid,axis = -1)
        bond_group_with_rid = bond_groups[has_rid_flag]
        bonded_to = bond_group_with_rid[bond_group_with_rid != rid]
        if return_removed_bonds:
            removed_bonds[rid] = bonded_to
        remaining_ids,counts = np.unique(bonded_to,return_counts=True)

        new_bonds = itertools.combinations(remaining_ids,2)
        for new_bond in new_bonds:
            ret_bonds[count] = new_bond
            count += 1

        multi_flags = counts > 1
        for id,c in zip(remaining_ids[multi_flags],counts[multi_flags]):
            for i in range(c-1):
                ret_bonds[count] = id,id
                count += 1
    if return_removed_bonds:
        if removed_bonds_dict is None:
            removed_bonds_dict = {to_remove:removed_bonds}
        else:
            removed_bonds_dict[to_remove] = removed_bonds

        return ret_bonds, removed_bonds_dict
    return ret_bonds# }}}

