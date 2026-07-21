def make_linear_polymer(mol_specs, particle_specs):
    import numpy as np

    mol_type = mol_specs.pop("molecule_type")
    if mol_type != "linear_polymer":
        raise Exception(f"Cannot turn molecule of type {mol_type} into a linear polymer")

    beads = mol_specs["beads"]
    bead_types = mol_specs["bead_types"]
    bond_type = mol_specs["bond_type"]

    # Convert bead_types to a list if a single int is provided
    if isinstance(bead_types, int):
        bead_types = [bead_types] * beads
    elif len(bead_types) != beads:
        if len(bead_types) < beads:
            raise Exception("Length of bead_types must match beads count")

    diameters = particle_specs["diameters"]
    particle_positions = np.zeros((beads, 3), dtype=float)
    particle_typeid = np.zeros(beads, dtype=int)

    # Set bead types
    for i in range(beads):
        particle_typeid[i] = bead_types[i]

    # Calculate x coordinates based on consecutive bead radii
    x = 0.0
    particle_positions[0, 0] = x
    for i in range(1, beads):
        r_prev = diameters[bead_types[i-1]] / 2.0
        r_curr = diameters[bead_types[i]] / 2.0
        x += (r_prev + r_curr)
        particle_positions[i, 0] = x

    # Generate sequential bonds
    nbonds = beads - 1
    bond_groups = np.zeros((nbonds, 2), dtype=int)
    bond_typeid = np.zeros(nbonds, dtype=int) + bond_type
    for i in range(nbonds):
        bond_groups[i] = [i, i+1]

    angle_groups = []
    angle_typeid = []
    if "angle_type" in mol_specs and mol_specs["angle_type"] is not None:
        angle_type = mol_specs["angle_type"]
        for i in range(beads - 2):
            angle_groups.append([i, i+1, i+2])
            angle_typeid.append(angle_type)

    new_mol_specs = dict(
        bond_typeid=bond_typeid.tolist(),
        bond_groups=bond_groups.tolist(),
        angle_typeid=angle_typeid,
        angle_groups=angle_groups,
        particle_typeid=particle_typeid.tolist(),
        particle_positions=particle_positions.tolist()
    )
    return new_mol_specs
