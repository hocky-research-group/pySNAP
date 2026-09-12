import numpy as np


def rigid_constituents(mol, num_particles):
    """Return how many particles after the first belong to the molecule's rigid body.

    A molecule may be rigid throughout, or rigid only in its core: droplets with mobile
    binders are built the second way, the binders having to diffuse over a core that
    does not deform. `"rigid": true` keeps its meaning of the whole molecule; a count
    names that many constituents, taken in order after the central particle.

    mol: the molecule definition.
    num_particles: how many particles it has.
    """
    spec = mol.get("rigid", False)
    if isinstance(spec, bool):
        return num_particles - 1 if spec else 0
    if isinstance(spec, int):
        if not 0 <= spec <= num_particles - 1:
            raise ValueError(
                f"a rigid body of {spec} constituents does not fit a molecule of "
                f"{num_particles} particles")
        return spec
    raise TypeError(f"'rigid' must be a boolean or a count, got {type(spec).__name__}")


def offset_bodies(body, index):
    """Return one molecule instance's body tags, shifted to its own body.

    Each instance of a rigid molecule is its own body, so the tags are offset by the
    instance's number. Free particles carry -1 and must keep it: offsetting the sentinel
    puts them in a body, and with two instances the second molecule's free particles
    would join the first's body.

    body: the molecule's body tags, 0 for the body and -1 for free particles.
    index: which instance this is.
    """
    tags = np.asarray(body)
    return np.where(tags >= 0, tags + index, -1).tolist()


def constituent_flags(mol, num_particles):
    """Return, per particle, whether it is a rigid constituent.

    HOOMD wants the constituents of a body after the free and central particles, which
    is what the generator reorders by. Only the body's own particles count: in a
    molecule that is rigid at the core, the rest are free.

    mol: the molecule definition.
    num_particles: how many particles it has.
    """
    constituents = rigid_constituents(mol, num_particles)
    return ([False]                                  # the central particle
            + [True] * constituents
            + [False] * (num_particles - 1 - constituents))


def renumber_bodies(body, is_constituent):
    """Return body tags naming each body by its central particle's index.

    HOOMD identifies a rigid body by its central particle: that particle's body tag must
    equal its own tag, and its constituents carry the same value. Bodies are numbered as
    they are created, which is the same thing only when every particle of a rigid
    molecule belongs to its body — the centres then occupy the first indices in order.
    A molecule that is rigid only in its core has free particles among them, and the
    numbering no longer lines up.

    Call this after the particles have been reordered.

    body: per-particle body tags, -1 for a free particle.
    is_constituent: per-particle, whether it is a constituent, in the same order.
    """
    body = np.asarray(body)
    central_index = {}
    for index, (tag, constituent) in enumerate(zip(body, is_constituent)):
        if tag >= 0 and not constituent:
            central_index[int(tag)] = index
    return np.array([central_index.get(int(tag), -1) if tag >= 0 else -1
                     for tag in body])


def build_rigid(mol, particle_masses, particle_diameters):
    dim = 3
    num_particles = len(mol["particle_typeid"])
    angmom = [[0, 0, 0, 0]] * num_particles
    body = (-np.ones(num_particles)).tolist()
    moment_inertia = [[0, 0, 0]] * num_particles
    orientation = [[1, 0, 0, 0]] * num_particles

    constituents = rigid_constituents(mol, num_particles)
    if constituents:
        positions = np.array(mol["particle_positions"])
        if not np.all(positions[0] == 0):
            raise Exception("The first particle is taken to be the central particle "
                            "of the rigid body and must be at the center of the molecule")
        I = calculate_moment_inertia(mol, particle_masses, particle_diameters,
                                     constituents)
        moment_inertia[0] = I.tolist()
        # Particles outside the body keep -1 and are integrated as free particles.
        body = [0] * (constituents + 1) + [-1] * (num_particles - constituents - 1)
    return angmom, body, moment_inertia, orientation


def diagonalize_moment_inertia(mol, I):
    I_diagonal, E_vec = np.linalg.eig(I)
    positions = np.array(mol["particle_positions"])
    R = E_vec.T
    diagonalized_positions = np.dot(R, positions.T).T
    mol["particle_positions"] = diagonalized_positions
    return I_diagonal


def calculate_moment_inertia(mol, particle_masses, particle_diameters,
                            constituents=None):
    """Return the moment of inertia of a molecule's rigid body.

    mol: the molecule definition.
    particle_masses: mass per particle type.
    particle_diameters: diameter per particle type.
    constituents: how many particles after the first belong to the body; None for all
        of them, which is what a fully rigid molecule means.
    """
    dim = 3
    if constituents is None:
        constituents = len(mol["particle_positions"]) - 1
    # Only the body's own particles carry its inertia and its mass; anything else in
    # the molecule is integrated separately and must not be counted here.
    num_particles = constituents + 1
    particle_typeids = mol["particle_typeid"][:num_particles]
    masses = np.array(particle_masses)[particle_typeids]
    radii = np.array(particle_diameters)[particle_typeids] / 2
    positions = np.array(mol["particle_positions"])[:num_particles]

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
        if rigid_constituents(mol, len(mol.get("particle_typeid", []))):
            return True
    return False
