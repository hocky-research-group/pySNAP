import numpy as np
from snap_simulate.tools import dict_defines
from snap_simulate.system.molecules.resolver import resolve_molecule_details


def calc_box_length(Box, Molecules, Particles):
    Dim = Box["dimensions"]
    if ("vol_frac" in Box and Box['vol_frac'] is not None) and \
            ("box_length" in Box and Box['box_length'] is not None):
        raise Exception("Both vol_frac and box_length specified in params")

    elif "vol_frac" in Box and Box['vol_frac'] is not None:
        vol_frac = Box["vol_frac"]
        vol_frac_mols = Box["vol_frac_mols"]
        vol = 0

        Molecules = resolve_molecule_details(Molecules, Particles)
        for name, mol in [[mol_name, Molecules[mol_name]] for mol_name in vol_frac_mols]:
            typeids = mol["particle_typeid"]
            diameters = np.array(Particles["diameters"])[typeids][np.array(Particles["excluded_volume"])[typeids]]
            vol += mol["num_molecules"] * np.pi / 6 * np.sum(diameters**3)

        box_vol = vol / vol_frac
        box_length = box_vol**(1 / 3)
        box_length = [box_length for i in range(3)]

    elif "area_frac" in Box and Box['area_frac'] is not None:
        area_frac = Box["area_frac"]
        area_frac_mols = Box["area_frac_mols"]
        area = 0

        Molecules = resolve_molecule_details(Molecules, Particles)
        for name, mol in [[mol_name, Molecules[mol_name]] for mol_name in area_frac_mols]:
            typeids = mol["particle_typeid"]
            diameters = np.array(Particles["diameters"])[typeids][np.array(Particles["excluded_volume"])[typeids]]
            area += mol["num_molecules"] * np.pi / 4 * np.sum(diameters**2)

        box_area = area / area_frac
        if dict_defines(Box, "aspect_ratio"):
            aspect_ratio = Box["aspect_ratio"]
            if len(aspect_ratio) != 2:
                raise Exception("Aspect ratio must be 2 numbers if working with area fractions")
        else:
            aspect_ratio = np.ones(2)
        L = (box_area / np.prod(aspect_ratio))**(1 / 2)
        box_length = L * np.array(aspect_ratio)
        box_length = np.append(box_length, 0)

    elif "box_length" in Box and Box['box_length'] is not None:
        box_length = Box["box_length"]
        if not np.iterable(box_length):
            box_length = [box_length for i in range(Dim)]
    else:
        raise Exception("No volume_fraction, area_fraction, or box_length defined")

    return box_length
