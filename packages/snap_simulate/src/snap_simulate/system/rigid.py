import numpy as np


def build_rigid(mol, particle_masses, particle_diameters):
    dim = 3
    num_particles = len(mol["particle_typeid"])
    angmom = [[0, 0, 0, 0]] * num_particles
    body = (-np.ones(num_particles)).tolist()
    moment_inertia = [[0, 0, 0]] * num_particles
    orientation = [[1, 0, 0, 0]] * num_particles

    if "rigid" in mol and mol["rigid"] is True:
        positions = np.array(mol["particle_positions"])
        if not np.all(positions[0] == 0):
            raise Exception("The first particle is taken to be the central particle "
                            "of the rigid body and must be at the center of the molecule")
        I = calculate_moment_inertia(mol, particle_masses, particle_diameters)
        moment_inertia[0] = I.tolist()
        body = [0] * num_particles
    return angmom, body, moment_inertia, orientation


def diagonalize_moment_inertia(mol, I):
    I_diagonal, E_vec = np.linalg.eig(I)
    positions = np.array(mol["particle_positions"])
    R = E_vec.T
    diagonalized_positions = np.dot(R, positions.T).T
    mol["particle_positions"] = diagonalized_positions
    return I_diagonal


def calculate_moment_inertia(mol, particle_masses, particle_diameters):
    dim = 3
    num_particles = len(mol["particle_positions"])
    particle_typeids = mol["particle_typeid"]
    masses = np.array(particle_masses)[particle_typeids]
    radii = np.array(particle_diameters)[particle_typeids] / 2
    positions = np.array(mol["particle_positions"])

    masses[0] = masses[0] - np.sum(masses[1:])
    if masses[0] < 0:
        raise Exception("First particle is assumed to be the central particle and should "
                        "have the total mass of the rigid body")

    I = np.zeros([dim, dim])
    ident = np.identity(dim)
    diag = ident.astype(bool)

    for i in range(num_particles):
        r = positions[i]
        mass = masses[i]
        R = radii[i]

        Iref = 2 / 5 * mass * R**2 * ident
        I += Iref + mass * (np.dot(r, r) * ident - np.outer(r, r))

    if np.any(I[~diag] != 0):
        I = diagonalize_moment_inertia(mol, I)
    else:
        I = I[diag]
    return I


def check_rigid(mols):
    for name, mol in mols.items():
        if "rigid" in mol and mol["rigid"] is True:
            return True
    return False
