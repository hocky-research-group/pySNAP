import numpy as np


def make_star_polymer(mol_specs, particle_specs):
    mol_type = mol_specs.pop("molecule_type")
    if mol_type != "star_polymer":
        raise Exception(f"Cannot turn molecule of type {mol_type} into a star polymer")

    M = mol_specs["beads_per_arm"] #beads per arm
    N = mol_specs["num_arms"] #arms per molecule
    center_type = mol_specs["center_type"]
    end_type = mol_specs["end_type"]
    arm_type = mol_specs["arm_type"]
    bond_type = mol_specs["bond_type"]

    d_center = particle_specs["diameters"][center_type]
    r_center = d_center/2
    d_arm = particle_specs["diameters"][arm_type]
    r_arm = d_arm/2
    d_end = particle_specs["diameters"][end_type]
    r_end = d_end/2
    
    nbonds = M*N
    Ntot  = M*N+1
    
    ct = 0
    bct = 0
    mct = 0
    
    particle_positions = np.zeros((Ntot,3), dtype=float)
    particle_typeid = np.zeros(Ntot,dtype = int)
    particle_typeid[0] = center_type
    
    bond_groups = np.zeros((int(nbonds), 2), dtype=int)
    bond_typeid = np.zeros(nbonds,dtype=int) + bond_type

    angle_typeid = []
    angle_groups = []
    
    #generate fibonacci tessalation of points on unit circle centered at origin
    goldenRatio = (1 + np.sqrt(5))/2
    points = np.arange(0, N, dtype=int)
    theta = 2 * np.pi *points/goldenRatio
    phi = np.arccos(1-2*(points+0.5)/N)
    
    #record x, y, z coordinates of all tessellated points
    for i in range(1,Ntot):
        arm = int((i-1)/M)
        bead = (i-1)%M
        bead_type = end_type if bead == M-1 else arm_type

        particle_typeid[i] = bead_type
        bond_groups[i-1] = [0,i] if bead == 0 else [i-1,i]

        r_self = r_end if bead == M-1 else r_arm
        r = r_center + bead*(d_arm) + r_self

        particle_positions[i] = (r*np.cos(theta[arm])*np.sin(phi[arm]), 
                  r*np.sin(theta[arm])*np.sin(phi[arm]), 
                  r*np.cos(phi[arm]))
    
    new_mol_specs = dict(bond_typeid = bond_typeid.tolist(),
                         bond_groups = bond_groups.tolist(),
                         angle_typeid = angle_typeid,
                         angle_groups = angle_groups,
                         particle_typeid = particle_typeid.tolist(),
                         particle_positions = particle_positions.tolist())
    return new_mol_specs

#mol = {"mol_type":"star_polymer","beads_per_arm":3,"num_arms":4,
        #"center_type":0,"arm_type":1,"end_type":2,
        #"bond_type":0,
        #"num_molecules":100}
#part = {"diameters":[1,1,1]}
#print(make_star_polymer(mol,part))
