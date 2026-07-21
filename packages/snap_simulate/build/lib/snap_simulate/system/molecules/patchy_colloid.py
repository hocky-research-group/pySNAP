def make_patchy_colloid(mol_specs, particle_specs):
    import numpy as np

    mol_type = mol_specs.pop("molecule_type")
    if mol_type != "patchy_colloid":
        raise Exception(f"Cannot turn molecule of type {mol_type} into a patchy colloid")

    colloid_type = mol_specs["colloid_type"]
    patch_type = mol_specs["patch_type"]
    num_patches = mol_specs["num_patches"]
    bond_type = mol_specs["bond_type"]
    patch_geometry = mol_specs.get("patch_geometry", "fibonacci").lower()

    diameters = particle_specs["diameters"]
    d_colloid = diameters[colloid_type]
    r_colloid = d_colloid / 2.0
    d_patch = diameters[patch_type]
    r_patch = d_patch / 2.0

    # Default patch distance is r_colloid + r_patch (touching colloid surface)
    patch_distance = mol_specs.get("patch_distance", r_colloid + r_patch)

    # Generate patch direction vectors
    directions = []

    if patch_geometry == "tetrahedral":
        if num_patches != 4:
            raise Exception("tetrahedral geometry requires exactly 4 patches")
        directions = [
            np.array([0.0, 0.0, 1.0]),
            np.array([2.0 * np.sqrt(2.0) / 3.0, 0.0, -1.0 / 3.0]),
            np.array([-np.sqrt(2.0) / 3.0, np.sqrt(6.0) / 3.0, -1.0 / 3.0]),
            np.array([-np.sqrt(2.0) / 3.0, -np.sqrt(6.0) / 3.0, -1.0 / 3.0])
        ]
    elif patch_geometry == "octahedral":
        if num_patches != 6:
            raise Exception("octahedral geometry requires exactly 6 patches")
        directions = [
            np.array([1.0, 0.0, 0.0]),
            np.array([-1.0, 0.0, 0.0]),
            np.array([0.0, 1.0, 0.0]),
            np.array([0.0, -1.0, 0.0]),
            np.array([0.0, 0.0, 1.0]),
            np.array([0.0, 0.0, -1.0])
        ]
    elif patch_geometry == "icosahedral":
        if num_patches != 12:
            raise Exception("icosahedral geometry requires exactly 12 patches")
        phi = (1.0 + np.sqrt(5.0)) / 2.0
        raw_dirs = [
            (0.0, 1.0, phi), (0.0, -1.0, phi), (0.0, 1.0, -phi), (0.0, -1.0, -phi),
            (1.0, phi, 0.0), (-1.0, phi, 0.0), (1.0, -phi, 0.0), (-1.0, -phi, 0.0),
            (phi, 0.0, 1.0), (-phi, 0.0, 1.0), (phi, 0.0, -1.0), (-phi, 0.0, -1.0)
        ]
        directions = [np.array(v) / np.linalg.norm(v) for v in raw_dirs]
    elif patch_geometry == "fibonacci":
        # Generate spherical Fibonacci spiral coordinates
        golden_ratio = (1.0 + np.sqrt(5.0)) / 2.0
        points = np.arange(0, num_patches, dtype=int)
        theta = 2.0 * np.pi * points / golden_ratio
        z_coords = 1.0 - 2.0 * (points + 0.5) / num_patches
        radius_xy = np.sqrt(1.0 - z_coords * z_coords)
        for i in range(num_patches):
            directions.append(np.array([
                radius_xy[i] * np.cos(theta[i]),
                radius_xy[i] * np.sin(theta[i]),
                z_coords[i]
            ]))
    else:
        raise Exception(f"Unknown patch_geometry: {patch_geometry}")

    Ntot = 1 + num_patches
    nbonds = num_patches

    particle_positions = np.zeros((Ntot, 3), dtype=float)
    particle_typeid = np.zeros(Ntot, dtype=int)
    particle_typeid[0] = colloid_type

    bond_groups = np.zeros((nbonds, 2), dtype=int)
    bond_typeid = np.zeros(nbonds, dtype=int) + bond_type

    for i in range(num_patches):
        idx = 1 + i
        particle_typeid[idx] = patch_type
        particle_positions[idx] = directions[i] * patch_distance
        bond_groups[i] = [0, idx]

    angle_groups = []
    angle_typeid = []
    if "angle_type" in mol_specs and mol_specs["angle_type"] is not None:
        angle_type = mol_specs["angle_type"]
        for i in range(num_patches):
            d_i = directions[i]
            dots = []
            for j in range(num_patches):
                if i != j:
                    dots.append((np.dot(d_i, directions[j]), j))
            if not dots:
                continue
            max_dot = max(d[0] for d in dots)
            # Define neighbors as those with dot product close to the maximum
            # (which means closest angular distance)
            neighbors = [d[1] for d in dots if d[0] >= max_dot - 0.05]
            for nbr in neighbors:
                if i < nbr:
                    angle_groups.append([1 + i, 0, 1 + nbr])
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
