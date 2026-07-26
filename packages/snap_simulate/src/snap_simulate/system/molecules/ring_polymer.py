import numpy as np


def make_ring_polymer(mol_specs, particle_specs):
    mol_type = mol_specs.pop("molecule_type")
    if mol_type != "ring_polymer":
        raise Exception(f"Cannot turn molecule of type {mol_type} into a ring polymer")

    beads = mol_specs["beads"]
    bead_type = mol_specs.get("bead_type")
    if bead_type is None:
        bead_type = mol_specs["bead_types"]  # fallback if they specify bead_types
    
    bond_type = mol_specs["bond_type"]

    # Convert bead_type to a list if a single int is provided
    if isinstance(bead_type, int):
        bead_type_list = [bead_type] * beads
    else:
        bead_type_list = list(bead_type)
        if len(bead_type_list) != beads:
            raise Exception("Length of bead_type list must match beads count")

    diameters = particle_specs["diameters"]
    particle_typeid = np.zeros(beads, dtype=int)
    for i in range(beads):
        particle_typeid[i] = bead_type_list[i]

    # Calculate average diameter
    d_avg = np.mean([diameters[t] for t in bead_type_list])

    # Calculate radius of the ring
    # Circumference = beads * d_avg = 2 * pi * R => R = beads * d_avg / (2 * pi)
    R = (beads * d_avg) / (2 * np.pi)

    particle_positions = np.zeros((beads, 3), dtype=float)
    for i in range(beads):
        theta = 2.0 * np.pi * i / beads
        particle_positions[i, 0] = R * np.cos(theta)
        particle_positions[i, 1] = R * np.sin(theta)
        particle_positions[i, 2] = 0.0

    # Generate bonds (closed loop)
    nbonds = beads
    bond_groups = np.zeros((nbonds, 2), dtype=int)
    bond_typeid = np.zeros(nbonds, dtype=int) + bond_type
    for i in range(beads - 1):
        bond_groups[i] = [i, i+1]
    bond_groups[beads - 1] = [beads - 1, 0]

    new_mol_specs = dict(
        bond_typeid=bond_typeid.tolist(),
        bond_groups=bond_groups.tolist(),
        angle_typeid=[],
        angle_groups=[],
        particle_typeid=particle_typeid.tolist(),
        particle_positions=particle_positions.tolist()
    )
    return new_mol_specs
