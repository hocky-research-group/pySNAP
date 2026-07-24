import snap_analyze as analyze
import gsd.hoomd
import numpy as np
import matplotlib.pyplot as plt

#with gsd.hoomd.open("gaurav.gsd") as traj:
    #snap = traj[100]
#
    #bond_groups = snap.bonds.group
    #bond_typeIDs = snap.bonds.typeid
    #dyn_bond_types = [3]
    #stat_bonds, dyn_bonds = analyze.split_static_dyn_bonds(bond_groups,
                                            #bond_typeIDs,dyn_bond_types)
#
    #num_particles = snap.particles.N
    #particle_typeIDs = snap.particles.typeid
    #atom_molIDs,(mol_typeIDs,mol_types) = analyze.get_complexes(num_particles,particle_typeIDs,stat_bonds,True)
    #bonds_molID = analyze.convert_id_to_complex_id(dyn_bonds,atom_molIDs)
    #toRemove = [1]
    #colloidBonds_molID, removed_bonds = analyze.remove_bond_intermediates(bonds_molID,mol_typeIDs,toRemove,True)

from snap_analyze import RDF
with gsd.hoomd.open("gaurav.gsd") as traj:
    snap0 = traj[0]
    rdf = RDF(snap0.configuration.box[:3],np.arange(0,40,0.5))
    #for snap in traj[1:30]:
    for snap in traj[1000::100]:
        types = snap.particles.typeid
        pos = snap.particles.position
        pos = pos[types == 0]
        rdf.append_sample(pos)
    bin_mids,rdf = rdf.compute()
    plt.plot(bin_mids,rdf)
    plt.show()
