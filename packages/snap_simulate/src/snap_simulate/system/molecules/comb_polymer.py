import numpy as np


def make_comb_polymer(mol_specs, particle_specs):
    mol_type = mol_specs.pop("molecule_type")
    if mol_type != "comb_polymer":
        raise Exception(f"Cannot turn molecule of type {mol_type} into a comb polymer")

    N_bb = mol_specs["backbone_beads"]
    backbone_type = mol_specs["backbone_type"]
    M_arm = mol_specs["arm_beads"]
    arm_type = mol_specs["arm_type"]
    S = mol_specs["graft_spacing"]
    bond_type = mol_specs["bond_type"]

    diameters = particle_specs["diameters"]
    d_bb = diameters[backbone_type]
    r_bb = d_bb / 2.0
    d_arm = diameters[arm_type]
    r_arm = d_arm / 2.0

    # Determine graft indices along the backbone
    graft_indices = [i for i in range(N_bb) if i % S == 0]
    num_arms = len(graft_indices)

    N_tot = N_bb + num_arms * M_arm
    particle_positions = np.zeros((N_tot, 3), dtype=float)
    particle_typeid = np.zeros(N_tot, dtype=int)

    # Place backbone beads along x-axis
    for i in range(N_bb):
        particle_typeid[i] = backbone_type
        particle_positions[i, 0] = i * d_bb
        particle_positions[i, 1] = 0.0
        particle_positions[i, 2] = 0.0

    # Bonds container
    # Sequential backbone bonds: N_bb - 1
    # Graft connection bonds: num_arms
    # Sequential arm bonds: num_arms * (M_arm - 1)
    nbonds = (N_bb - 1) + num_arms + num_arms * (M_arm - 1)
    bond_groups = np.zeros((nbonds, 2), dtype=int)
    bond_typeid = np.zeros(nbonds, dtype=int) + bond_type

    b_idx = 0
    # Add backbone bonds
    for i in range(N_bb - 1):
        bond_groups[b_idx] = [i, i+1]
        b_idx += 1

    # Place arms and add their bonds
    current_arm_start_idx = N_bb
    for k, i_bb in enumerate(graft_indices):
        # Angle of projection in the yz-plane (alternating directions to avoid overlaps)
        phi = 2.0 * np.pi * k / 3.0
        u_y = np.cos(phi)
        u_z = np.sin(phi)

        # Place beads for this arm
        for j in range(M_arm):
            idx = current_arm_start_idx + j
            particle_typeid[idx] = arm_type
            
            # Position offset from the graft backbone bead
            dist = r_bb + r_arm + j * d_arm
            particle_positions[idx, 0] = particle_positions[i_bb, 0]
            particle_positions[idx, 1] = dist * u_y
            particle_positions[idx, 2] = dist * u_z

        # Add connection bond from backbone graft bead to first arm bead
        bond_groups[b_idx] = [i_bb, current_arm_start_idx]
        b_idx += 1

        # Add sequential arm bonds
        for j in range(M_arm - 1):
            bond_groups[b_idx] = [current_arm_start_idx + j, current_arm_start_idx + j + 1]
            b_idx += 1

        current_arm_start_idx += M_arm

    new_mol_specs = dict(
        bond_typeid=bond_typeid.tolist(),
        bond_groups=bond_groups.tolist(),
        angle_typeid=[],
        angle_groups=[],
        particle_typeid=particle_typeid.tolist(),
        particle_positions=particle_positions.tolist()
    )
    return new_mol_specs
