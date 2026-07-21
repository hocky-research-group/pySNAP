def make_grafted_colloid(mol_specs, particle_specs):
    import numpy as np

    mol_type = mol_specs.pop("molecule_type")
    if mol_type != "grafted_colloid":
        raise Exception(f"Cannot turn molecule of type {mol_type} into a grafted colloid")

    colloid_type = mol_specs["colloid_type"]
    M = mol_specs["arm_beads"]
    N = mol_specs["num_arms"]
    arm_type = mol_specs["arm_type"]
    end_type = mol_specs["end_type"]
    bond_type = mol_specs["bond_type"]

    # Convert arm_type to a list if a single int is provided
    if isinstance(arm_type, int):
        arm_types = [arm_type] * M
    else:
        arm_types = list(arm_type)
        if len(arm_types) != M:
            raise Exception("Length of arm_type list must match arm_beads count")

    diameters = particle_specs["diameters"]
    d_colloid = diameters[colloid_type]
    r_colloid = d_colloid / 2.0

    # Pre-calculate arm bead types and distances from colloid center
    arm_bead_types = []
    arm_distances = []
    for bead in range(M):
        bead_type = end_type if bead == M - 1 else arm_types[bead]
        arm_bead_types.append(bead_type)
        
        r_curr = diameters[bead_type] / 2.0
        if bead == 0:
            dist = r_colloid + r_curr
        else:
            r_prev = diameters[arm_bead_types[bead - 1]] / 2.0
            dist = arm_distances[bead - 1] + r_prev + r_curr
        arm_distances.append(dist)

    Ntot = 1 + N * M
    nbonds = N * M

    particle_positions = np.zeros((Ntot, 3), dtype=float)
    particle_typeid = np.zeros(Ntot, dtype=int)
    particle_typeid[0] = colloid_type

    bond_groups = np.zeros((nbonds, 2), dtype=int)
    bond_typeid = np.zeros(nbonds, dtype=int) + bond_type

    # Generate Fibonacci sphere discretization of points on the unit sphere
    golden_ratio = (1.0 + np.sqrt(5.0)) / 2.0
    points = np.arange(0, N, dtype=int)
    theta = 2.0 * np.pi * points / golden_ratio
    phi = np.arccos(1.0 - 2.0 * (points + 0.5) / N)

    for arm in range(N):
        # Calculate arm direction vector
        sin_phi = np.sin(phi[arm])
        ux = np.cos(theta[arm]) * sin_phi
        uy = np.sin(theta[arm]) * sin_phi
        uz = np.cos(phi[arm])

        for bead in range(M):
            idx = 1 + arm * M + bead
            bead_type = arm_bead_types[bead]
            particle_typeid[idx] = bead_type

            # Position computation
            r = arm_distances[bead]
            particle_positions[idx] = (r * ux, r * uy, r * uz)

            # Bonds structure
            bond_idx = arm * M + bead
            if bead == 0:
                bond_groups[bond_idx] = [0, idx]
            else:
                bond_groups[bond_idx] = [idx - 1, idx]

    new_mol_specs = dict(
        bond_typeid=bond_typeid.tolist(),
        bond_groups=bond_groups.tolist(),
        angle_typeid=[],
        angle_groups=[],
        particle_typeid=particle_typeid.tolist(),
        particle_positions=particle_positions.tolist()
    )
    return new_mol_specs
