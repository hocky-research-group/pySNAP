##
# Author: Tanner A. Wilcoxson
# Date Created: May 18, 2023
# Generates an initial configuration from System_Params

import numpy as np
import itertools
import sys
from ..tools import dict_defines

class container:# {{{
    def __init__(self,box_length,dim):
        self.maxSite = box_length
        self.sites = dict()
        self.dim = dim
        self.count = 0
    def __getitem__(self,index):
        if index.shape[1] != self.dim:
            sys.tracebacklimit = 0
            raise ValueError(f"Indices must match box dimension ({self.dim})")
        if np.any(index > self.maxSite):
            sys.tracebacklimit = 0
            raise ValueError("Cannot have index larger than boxsize")
        for i,ind in enumerate(index):
            flag = self.sites.get(tuple(ind),False)
            if flag:
                return flag
        return False

    def set(self,index):
        if index.shape[1] != self.dim:
            sys.tracebacklimit = 0
            raise ValueError(f"Indices must match box dimension ({self.dim})")
        if np.any(index > self.maxSite):
            sys.tracebacklimit = 0
            raise ValueError("Cannot have index larger than boxsize")
        for i,ind in enumerate(index):
            self.sites[tuple(ind)] = True
        self.count += i+1
        return 

    def vol_frac(self):
        return self.count/np.prod(self.maxSite)
    # }}}
class overlap_checker:# {{{
    def __init__(self,box_length,cell_size,dim = None):
        self.nlist = dict()
        self.diameters = []
        box_length = np.copy(box_length)
        cell_size = np.copy(cell_size)
        if np.isscalar(box_length) and dim is None:
            sys.tracebacklimit = 0
            raise Exception("If box_length is a scalar, dim must be specified")
        elif np.isscalar(box_length):
            self.dim = dim
            box_length = np.ones(dim)*box_length
        else:
            self.dim = len(box_length)
            box_length = np.asarray(box_length)


        if np.any(box_length == 0):
            flag = box_length == 0
            box_length[flag] = cell_size

        self.num_boxes = (box_length/cell_size).astype(int)
        self.cell_size = box_length/self.num_boxes 
        self.box_length = box_length
        self.half_box = box_length/2
        self.count_checks = 0
        self.count_adds = 0

    def has_overlap(self,mol_pos,mol_d):
        if np.any(mol_pos < 0):
            mol_pos = mol_pos + self.half_box
        if np.any(mol_pos < 0) or np.any(mol_pos > self.box_length):
            sys.tracebacklimit = 0
            raise Exception("Cannot check particles that are out of the box")
        if np.any(mol_d != 1):
            is_colloid = True
        else:
            is_colloid = False
        idxs = (mol_pos/self.cell_size).astype(int)
        offset = np.array([np.arange(-1,2) for i in range(self.dim)])
        L = self.box_length
        for idx,pos1,d1 in zip(idxs,mol_pos,mol_d):
            offsets = (idx[:,None]+offset)%self.num_boxes
            for off in itertools.product(*offsets):
                index = tuple(off)
                if index not in self.nlist:
                    continue
                for pos2,d2 in self.nlist[index]:
                    delta = pos1 - pos2
                    p = False
                    delta -= np.round(delta/L)*L
                    dist = np.sqrt(delta[0]**2 + delta[1]**2 + delta[2]**2)
                    dc = (d1+d2)/2 #contact distance
                    if dist < dc:
                        return True
        self.count_checks += 1
        return False
        

    def add(self,mol_pos,mol_d):
        if np.any(mol_pos < 0):
            mol_pos = mol_pos + self.half_box
        if np.any(mol_pos < 0) or np.any(mol_pos > self.box_length):
            sys.tracebacklimit = 0
            raise Exception("Cannot add particles that are out of the box")
        idxs = (mol_pos/self.cell_size).astype(int)
        for idx,pos,d in zip(idxs,mol_pos,mol_d):
            index = tuple(idx)
            if index not in self.nlist:
                self.nlist[index] = []
            self.nlist[tuple(idx)].append([pos,d])
        self.count_adds += 1
        return True# }}}

def build_rigid(mol,particle_masses,particle_diameters):# {{{
    dim = 3
    num_particles = len(mol["particle_typeid"])
    angmom = [[0,0,0,0]]*num_particles
    body = (-np.ones(num_particles)).tolist()
    moment_inertia = [[0,0,0]]*num_particles
    orientation = [[1,0,0,0]]*num_particles

    if "rigid" in mol and mol["rigid"] is True:
        positions = np.array(mol["particle_positions"])
        if not np.all(positions[0] == 0):
            raise Exception("The first particle is taken to be the central particle"\
                            +"of the rigid body and must be at the center of the molecule")
        I = calculate_moment_inertia(mol,particle_masses,particle_diameters)
        moment_inertia[0] = I.tolist()
        body = [0]*num_particles
    return angmom,body,moment_inertia,orientation# }}}
def diagonalize_moment_inertia(mol,I):# {{{
    I_diagonal,E_vec = np.linalg.eig(I)
    positions = np.array(mol["particle_positions"])
    R = E_vec.T
    diagonalized_positions = np.dot(R,positions.T).T
    mol["particle_positions"] = diagonalized_positions
    return I_diagonal
# }}}
def calculate_moment_inertia(mol,particle_masses,particle_diameters):# {{{
    dim=3
    num_particles = len(mol["particle_positions"])
    particle_typeids = mol["particle_typeid"]
    masses = np.array(particle_masses)[particle_typeids]
    radii= np.array(particle_diameters)[particle_typeids]/2
    positions = np.array(mol["particle_positions"])

    masses[0] = masses[0] - np.sum(masses[1:])
    if masses[0] < 0:
        raise Exception("First particle is assumed to be the central particle and should"\
                +" have the total mass of the rigid body")

    I = np.zeros([dim,dim])
    ident = np.identity(dim)
    diag = ident.astype(bool)

    for i in range(num_particles):
        r = positions[i]
        mass = masses[i]
        R = radii[i]

        Iref = 2/5*mass*R**2*ident
        I += Iref + mass * (np.dot(r,r) * ident - np.outer(r,r))

    if np.any(I[~diag] != 0):
        I = diagonalize_moment_inertia(mol,I)
    else:
        I = I[diag]
    return I# }}}

def gen_mixture(params,outfile):# {{{
    import gsd.hoomd

    Particles = params["particles"]

    if "bonds" in params:
        bond_types = params["bonds"]["types"]
    else:
        bond_types = []
    if "angles" in params:
        angle_types = params["angles"]["types"]
    else:
        angle_types = []

    if "dihedrals" in params:
        dihedral_types = params["dihedrals"]["types"]
    else:
        dihedral_types = []

    Molecules = params["molecules"]
    Box = params["box"]
    Dim = Box["dimensions"]

    has_rigid = check_rigid(Molecules)
    #---- Snapshot Initialization ----{{{
    s = gsd.hoomd.Frame()
    
    s.particles.N = 0
    s.particles.types = Particles["types"]
    s.particles.typeid = [] 
    s.particles.diameter = []
    s.particles.mass = []
    s.particles.position = []
    thermalize = []
    
    s.bonds.N = 0
    s.bonds.types = bond_types
    s.bonds.typeid = []
    s.bonds.group = []
    
    s.angles.N = 0
    s.angles.types = angle_types
    s.angles.typeid = []
    s.angles.group = []

    s.dihedrals.N = 0
    s.dihedrals.types = angle_types
    s.dihedrals.typeid = []
    s.dihedrals.group = []

    if has_rigid:
        s.particles.angmom = []
        s.particles.body = []
        s.particles.moment_inertia = []
        s.particles.orientation = []
        body_count = 0
        is_constituent = []
    # }}}
    #---- Generate Molecule Metadata ----{{{
    Molecules = resolve_molecule_details(Molecules,Particles)
    for name,mol in Molecules.items():
        N = mol["num_molecules"]
        N0 = s.particles.N
        # ----Particles----{{{
        typeids = mol["particle_typeid"]
        num_particles = len(typeids)

        masses    = np.array(Particles["mass"])[typeids].tolist()
        mol["masses"] = np.array(masses)
        diameters = np.array(Particles["diameters"])[typeids].tolist()
        mol["diameters"] = np.array(diameters)

        s.particles.N += N*num_particles
        s.particles.typeid += N*typeids
        s.particles.diameter += N*diameters
        s.particles.mass += N*masses
        # }}}
        # ----Rigid----{{{
        if has_rigid:
            rigid_info = build_rigid(mol,Particles["mass"],Particles["diameters"])
            angmom,body,moment_inertia,orientation = rigid_info
            s.particles.angmom += N*angmom
            new_bodies = body[0] == 0
            if new_bodies:
                full_body = []
                for i in range(N):
                    full_body += (np.array(body)+body_count).tolist()
                    body_count += 1
                is_constituent += N*([False] + (num_particles-1)*[True])
            else:
                full_body = N*body
                is_constituent += N*num_particles*[False]

            s.particles.body += full_body
            s.particles.moment_inertia += N*moment_inertia
            s.particles.orientation += N*orientation
        #}}}
        # ----Grid----{{{
        particle_positions = mol["particle_positions"]
        
        min_pos = np.min(particle_positions,axis = 0)
        max_pos = np.max(particle_positions,axis = 0)
        mol["vol"] = np.sum((min_pos-max_pos)**2)

        min_grid = (min_pos-0.5).astype(int)
        max_grid = (max_pos+0.5).astype(int)+1
        grid = np.array([min_grid,max_grid]).T

        mol_grid = np.array([[i,j,k] for i in range(*grid[0])\
                                     for j in range(*grid[1])\
                                     for k in range(*grid[2])])
        mol["grid"] = mol_grid
        #}}}
        # ----Bonds----{{{
        if "bond_groups" in mol:
            bonds = mol["bond_groups"]
            s.bonds.N += N*len(bonds)
            s.bonds.typeid += N*mol["bond_typeid"]
            groups = []
            for i in range(N):
                groups += list(np.array(bonds) + i*num_particles + N0)
            s.bonds.group += groups
        #}}}
        # ----Angles----{{{
        if "angle_groups" in mol:
            angles = mol["angle_groups"]
            s.angles.N += N*len(angles)
            s.angles.typeid += N*mol["angle_typeid"]
            groups = []
            for i in range(N):
                groups += list(np.array(angles) + i*num_particles + N0)
            s.angles.group += groups
        # }}}
        # ----Dihedrals----{{{
        if "dihedral_groups" in mol:
            dihedrals = mol["dihedral_groups"]
            s.dihedrals.N += N*len(dihedrals)
            s.dihedrals.typeid += N*mol["dihedral_typeid"]
            groups = []
            for i in range(N):
                groups += list(np.array(dihedrals) + i*num_particles + N0)
            s.dihedrals.group += groups
        #}}}
        # ----Thermalize---- {{{
        if "thermalize" in mol:
            thermalize += [mol["thermalize"] 
                            for i in range(N*num_particles)]
        else:
            thermalize += [False for i in range(N*num_particles)]
        #}}}
    #}}}
    #---- Set Box Size ---- {{{
    s.configuration.dimensions = Dim
    
    box_length = calc_box_length(Box,Molecules,Particles)
    box_length = np.array(box_length)

    Box['box_length'] = box_length
    Box['max'] = box_length/2
    Box['min'] = -box_length/2
    #}}}
    #---- Place Molecules ---- {{{{
    placement_style=Box["placement_style"]
    sites = container(box_length,Dim)
    sites = overlap_checker(box_length,max(Particles["diameters"]))
    if not isinstance(placement_style,dict):
        placement_style = {placement_style:Molecules}
    else:
        for style, names in placement_style.items():
            placement_style[style] = {name:Molecules[name] for name in names}

    pos = dict()
    if "simple_cubic" in placement_style:
        temp_p = place_simple_cubic(Box,sites,placement_style["simple_cubic"])
        pos.update(temp_p)
    if "random" in placement_style:
        temp_p = place_random(Box,sites,placement_style["random"])
        pos.update(temp_p)

    for name, mol in Molecules.items():
        s.particles.position += pos[name]
    #}}}
    #---- Adding to snapshot----{{{
    s.configuration.step = 0
    if "tilt" in Box:
        tilt = Box['tilt']
    else:
        tilt = np.zeros(Dim)
    box = np.concatenate([box_length,tilt])
    s.configuration.box = box
    
    s.bonds.group = np.array(s.bonds.group,dtype=int)
    s.angles.group = np.array(s.angles.group,dtype=int)
    s.dihedrals.group = np.array(s.dihedrals.group,dtype=int)

    s.particles.image = np.zeros((s.particles.N, Dim))
    s.particles.velocity = np.zeros((s.particles.N,Dim))
    if np.count_nonzero(thermalize) != 0:
        v = np.random.normal(0.0, 1.0, size=(np.count_nonzero(thermalize),Dim))
        v -= np.mean(v, axis=0)
        s.particles.velocity[thermalize] = v

    if has_rigid:
        sort_flags,old_to_new_idx = calc_reorder_idx(is_constituent)
        s.particles.typeid         = np.array(s.particles.typeid)[sort_flags]
        s.particles.diameter       = np.array(s.particles.diameter)[sort_flags]
        s.particles.mass           = np.array(s.particles.mass)[sort_flags]
        s.particles.position       = np.array(s.particles.position)[sort_flags]
        s.particles.angmom         = np.array(s.particles.angmom)[sort_flags]
        s.particles.body           = np.array(s.particles.body)[sort_flags]
        s.particles.moment_inertia = np.array(s.particles.moment_inertia)[sort_flags]
        s.particles.orientation    = np.array(s.particles.orientation)[sort_flags]
        s.particles.velocity = np.array(s.particles.velocity)[sort_flags]

        s.bonds.group = old_to_new_idx[s.bonds.group]
        s.angles.group = old_to_new_idx[s.angles.group]
        s.dihedrals.group = old_to_new_idx[s.dihedrals.group]
    #}}}
    with gsd.hoomd.open(name = outfile, mode="w") as f:
        f.append(s)# }}}

def calc_reorder_idx(is_constituent):# {{{
    N = len(is_constituent)
    new_idx = np.zeros(N,dtype=int)
    first_count = 0
    last_count = 0
    for i in range(N):
        if not is_constituent[i]:
            new_idx[i] = first_count
            first_count += 1
        else:
            new_idx[i] = last_count
            last_count += 1
    new_idx[is_constituent] += first_count
    sort_flags = np.argsort(new_idx)
    return sort_flags, new_idx
# }}}
def place_simple_cubic(box,sites,mols):#{{{
    #---- Pre placing calculations ----{{{
    num_mol = 0
    num_types = 0
    max_size = np.zeros(3)
    box_length = box["box_length"]
    if dict_defines(box,"placement_spacing"):
        spacing = np.array(box["placement_spacing"])
    else:
        spacing = np.array([None,None,None])
    needs_spacing = spacing == None
    min_N = np.inf

    dim = box["dimensions"]
    for name,mol in mols.items():
        min_N = np.min([min_N,mol["num_molecules"]])
        num_mol += mol["num_molecules"]
        num_types += 1
        grid = mol["grid"]
        size = np.max(grid,axis = 0) - np.min(grid,axis = 0)
        max_size[max_size<size] = size[max_size<size]

    min_N = int(min_N)
    num_lattice = np.zeros_like(spacing,dtype=int)-1
    num_lattice[~needs_spacing] = box_length[~needs_spacing]/spacing[~needs_spacing]
    num_lattice[num_lattice == 0] = 1
    N_set = np.prod(num_lattice[~needs_spacing])

    aspect_ratio = box_length[needs_spacing]/np.min(box_length[needs_spacing])

    N_not_set = num_mol/N_set
    n = (N_not_set*np.prod(aspect_ratio))**(1/len(aspect_ratio))
    num_lattice[needs_spacing] = np.ceil(n/aspect_ratio).astype(int)
    lattice_size = box_length/num_lattice
    if np.any(max_size > lattice_size):# Error Check mol > lattice {{{
        sys.tracebacklimit = 0
        raise Exception(f"Unable to place molecules in a simple cubic lattice. " +\
                         "Lattice size is not large enough for molecules")# }}}
    lattice_centers = [np.linspace(lattice_size[i]/2,
                                   box_length[i]-lattice_size[i]/2,
                                   num_lattice[i]) for i in range(dim)]
    lattice_sites = np.array(np.meshgrid(*lattice_centers)).T
    all_lattice = lattice_sites
    lattice_sites = all_lattice.reshape(np.prod(all_lattice.shape[:dim]),3)
    #}}}
    positions = dict()
    therms = dict()
    used_sites = []
    #---- Particle Placement ---- {{{
    position_index = np.arange(num_mol)

    if dict_defines(box,"placement_order"):
        if box['placement_order'] == "random":
            np.random.shuffle(position_index)
        elif box['placement_order'] == "alternating":
            N_not_set = dict()
            index_by_mol = dict()
            temp_index = np.arange(np.prod(all_lattice.shape[:-1])).reshape(all_lattice.shape[:-1])
            i = -1
            for name,mol in mols.items():
                i += 1
                checker_flags = ~((np.indices(all_lattice.shape[:-1]).sum(axis = 0)+i)%num_types).astype(bool)
                index_by_mol[name] = temp_index[checker_flags][:min_N]
                if min_N < mol["num_molecules"]:
                    N_not_set[name] = mol["num_molecules"] - min_N
            N_set = min_N*len(mols)
            for name,N_to_set in N_not_set.items():
                N_new = N_set + N_to_set
                index_by_mol[name] = np.concatenate([index_by_mol[name],np.arange(N_set,N_new)])
                N_set = N_new
            position_index = np.concatenate(list(index_by_mol.values()))

    N_total = 0
    for name,mol in mols.items():
        name_plural = name + ('s' if name[-1] != 's' else '')
        N = mol["num_molecules"]

        print(f"Placing {N} {name_plural} in a simple cubic lattice")
        num_particles = len(mol["particle_typeid"])

        mol_sites = lattice_sites[position_index[N_total:N_total+N]]
        positions[name] = []
        for site in mol_sites:
            part_pos = site + mol["particle_positions"]
            if sites.has_overlap(part_pos,mol["diameters"]):
                sys.tracebacklimit = 0
                raise Exception(f"Unable to place {name} in the Simple Cubic lattice. " +\
                                 "Atleast one particle has been placed in a lattice site")
            sites.add(part_pos,mol["diameters"])
            positions[name] += (part_pos-box_length/2).tolist()
        N_total += N
    #}}}
    return positions #}}}
def place_random(box,sites,mols,try_limit=1000):#{{{
    positions = dict()
    therms = dict()
    box_length = box['box_length']
    dim = box["dimensions"]


    mol_order = list(mols.items())
    mol_order = sorted(mol_order,key = lambda x:x[1]["vol"], reverse = True)
    for name,mol in mol_order:
        N = mol["num_molecules"]
        name_plural = name + ('s' if name[-1] != 's' else '')
        num_particles = len(mol["particle_typeid"])
        particle_positions = mol["particle_positions"]
        mol_dia = mol["diameters"]
        positions[name] = []

        if N == 0:
            print(f"Not placing {name_plural}- zero requested")
            continue
        print(f"Placing {N} {name_plural} randomly:")
        for i in range(N):
            tries = 0
            print_freq = max(int(N/10),1)
            if i%print_freq == 0:
                print(f"    {(i+1)/N*100:.0f}% of {name_plural} placed")
            placed = False
            while tries < try_limit:
                tries += 1

                rand_pos = np.random.rand(dim)*box_length
                pos = particle_positions + rand_pos
                pos -= np.floor(pos/box_length)*box_length
    
                if sites.has_overlap(pos,mol_dia):
                    continue

                placed = True
                sites.add(pos,mol_dia)
                part_pos = pos - box_length/2
                positions[name] += part_pos.tolist()
                break
            if not placed:
                sys.tracebacklimit = 0
                raise Exception(f"Unable to place {name} {i} out of {N} after {try_limit} attempts")
    return positions
        #}}}

def resolve_molecule_details(Molecules,Particles):# {{{
    Molecules = compute_num_molecules(Molecules)
    Molecules = create_molecules_from_template(Molecules,Particles)
    return Molecules# }}}
def compute_num_molecules(mols):# {{{
    mols = compute_group_nums(mols)
    for name,mol in mols.items():
        if dict_defines(mol,"num_molecules"):
            continue
        elif dict_defines(mol,"molecule_ratio") and dict_defines(mol,"molecule_ratio_reference"):
            ref_name = mol["molecule_ratio_reference"]
            ref_mol = mols[ref_name]
            if not dict_defines(ref_mol,"num_molecules"):
                recurse_compute_num_molecules(mols,ref_name)
            mol["num_molecules"] = int(ref_mol["num_molecules"] * mol["molecule_ratio"])
        else:
            sys.tracebacklimit = 0
            raise Exception(f"{name} does not have either 'num_molecules' or 'molecule_ratio' and 'molecule_ratio_reference' defined")
    return mols

def recurse_compute_num_molecules(mols,name,name_list = np.array([])):
    mol = mols[name]
    if dict_defines(mol,"molecule_ratio") and dict_defines(mol,"molecule_ratio_reference"):
        ref_name = mol["molecule_ratio_reference"]
        if ref_name in name_list:
            sys.tracebacklimit = 0
            raise Exception(f"Circular molecule ratios detected: {name_list}")
        ref_mol = mols[ref_name]
        if not dict_defines(ref_mol,"num_molecules"):
            recurse_compute_num_molecules(mols,ref_name,np.append(name_list,name))
        mol["num_molecules"] = int(ref_mol["num_molecules"] * mol["molecule_ratio"])
    return#}}}
def create_molecules_from_template(Molecules,Particles):# {{{
    for name,mol in Molecules.items():
        if not dict_defines(mol,"molecule_type"): 
            continue
        mol_type = mol["molecule_type"]
        if mol_type == "custom":
            continue
        if mol_type == "star_polymer":
            from .molecules import make_star_polymer
            new_mol = make_star_polymer(mol,Particles)
            mol.update(new_mol)
    return Molecules# }}}
def compute_group_nums(mols):# {{{
    groups = dict()
    for name,mol in mols.items():
        if "group_name" in mol and mol["group_name"] is not None:
            if mol["group_name"] not in groups:
                groups[mol["group_name"]] = []
            groups[mol["group_name"]].append(mol)

    if len(groups) == 0:
        return mols

    for name,group in groups.items():
        balance_index = None
        num_mols = 0
        group_num = None
        for i,mol in enumerate(group):
            if group_num is None:
                group_num = mol["num_group"]
            if group_num != mol["num_group"]:
                raise Exception("All mols in a group must have the same num_group")
            if mol["group_frac"] == "balance":
                if balance_index is not None:
                    raise Exception("Cannot have more than one mol in a group be set to balance")
                balance_index = i
            else:
                mol["num_molecules"] = int(mol["num_group"]*mol["group_frac"])
                num_mols += mol["num_molecules"]

        mol = group[balance_index]

        if mol["num_group"] < num_mols:
            raise Exception(f"Group {name} has more molecules than intended")
        mol["num_molecules"] = mol["num_group"] - num_mols
    return mols# }}}


def check_rigid(mols):# {{{
    for name,mol in mols.items():
        if "rigid" in mol and mol["rigid"] is True:
            return True
    return False# }}}
def calc_box_length(Box,Molecules,Particles):# {{{
    Dim = Box["dimensions"]
    if ("vol_frac" in Box and Box['vol_frac'] is not None) and \
                ("box_length" in Box and Box['box_length'] is not None):
        sys.tracebacklimit = 0
        raise Exception("Both vol_frac and box_length specified in params")

    elif "vol_frac" in Box and Box['vol_frac'] is not None:
        vol_frac = Box["vol_frac"]
        vol_frac_mols = Box["vol_frac_mols"]
        vol = 0

        Molecules = resolve_molecule_details(Molecules,Particles)
        for name,mol in [[mol_name, Molecules[mol_name]] for mol_name in vol_frac_mols]:
            typeids = mol["particle_typeid"]
            diameters = np.array(Particles["diameters"])[typeids][np.array(Particles["excluded_volume"])[typeids]]
            vol += mol["num_molecules"]*np.pi/6*np.sum(diameters**3)

        box_vol = vol/vol_frac
        box_length = box_vol**(1/3)
        box_length = [box_length for i in range(3)]

    elif "area_frac" in Box and Box['area_frac'] is not None:
        area_frac = Box["area_frac"]
        area_frac_mols = Box["area_frac_mols"]
        area = 0

        Molecules = resolve_molecule_details(Molecules,Particles)
        for name,mol in [[mol_name, Molecules[mol_name]] for mol_name in area_frac_mols]:
            typeids = mol["particle_typeid"]
            diameters = np.array(Particles["diameters"])[typeids][np.array(Particles["excluded_volume"])[typeids]]
            area += mol["num_molecules"]*np.pi/4*np.sum(diameters**2)

        box_area = area/area_frac
        if dict_defines(Box,"aspect_ratio"):
            aspect_ratio = Box["aspect_ratio"]
            if len(aspect_ratio) != 2:
                raise Exception("Aspect ratio must be 2 numbers if working with area fractions")
        else:
            aspect_ratio = np.ones(2)
        L = (box_area/np.prod(aspect_ratio))**(1/2)
        box_length = L*np.array(aspect_ratio)
        box_length = np.append(box_length,0)


    elif "box_length" in Box and Box['box_length'] is not None:
        box_length = Box["box_length"]
        if not np.iterable(box_length):
            box_length = [box_length for i in range(Dim)]
    else:
        raise Exception("No volume_fraction, area_fraction, or box_length defined")

    return box_length# }}}

#----Partial Implementations----
#def place_packed(box,sites,mols):#{{{
#    box_length = box["box_length"]
#    box_sites = box_length.astype(int)
#    #---- Particle Placement ---- {{{
#    xsite = 0
#    ysite = 0
#    for name,mol in Molecules.items():
#        print("Placing ", name)
#        N = mol["num_molecules"]
#        num_particles = len(mol["particle_typeid"])
#        molecule_grid = mol["grid"]
#
#        positions[name] = []
#        for lattice_site in lattice_sites:
#            grid_sites = (lattice_site + molecule_grid).astype(int)
#            if sites[grid_sites]:
#                raise Exception(f"Unable to place {name} in the Simple Cubic lattice. " +\
#                                 "Atleast one particle has been placed in a lattice site")
#            sites.set(grid_sites)
#            part_pos = lattice_site - box_length/2 + mol["particle_positions"]
#            positions[name] += part_pos.tolist()
#
#        therms[name] = [mol["thermalize"] for i in range(N*num_particles)]
#    #}}}
#    return positions, therms #}}}
