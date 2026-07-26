import numpy as np
from snap_simulate.tools import dict_defines
from snap_simulate.system.molecules import MOLECULE_TEMPLATES


def resolve_molecule_details(Molecules, Particles):
    Molecules = compute_num_molecules(Molecules)
    Molecules = create_molecules_from_template(Molecules, Particles)
    return Molecules


def compute_num_molecules(mols):
    mols = compute_group_nums(mols)
    for name, mol in mols.items():
        if dict_defines(mol, "num_molecules"):
            continue
        elif dict_defines(mol, "molecule_ratio") and dict_defines(mol, "molecule_ratio_reference"):
            ref_name = mol["molecule_ratio_reference"]
            ref_mol = mols[ref_name]
            if not dict_defines(ref_mol, "num_molecules"):
                recurse_compute_num_molecules(mols, ref_name)
            mol["num_molecules"] = int(ref_mol["num_molecules"] * mol["molecule_ratio"])
        else:
            raise Exception(f"{name} does not have either 'num_molecules' or 'molecule_ratio' and 'molecule_ratio_reference' defined")
    return mols


def recurse_compute_num_molecules(mols, name, name_list=np.array([])):
    mol = mols[name]
    if dict_defines(mol, "molecule_ratio") and dict_defines(mol, "molecule_ratio_reference"):
        ref_name = mol["molecule_ratio_reference"]
        if ref_name in name_list:
            raise Exception(f"Circular molecule ratios detected: {name_list}")
        ref_mol = mols[ref_name]
        if not dict_defines(ref_mol, "num_molecules"):
            recurse_compute_num_molecules(mols, ref_name, np.append(name_list, name))
        mol["num_molecules"] = int(ref_mol["num_molecules"] * mol["molecule_ratio"])
    return


def create_molecules_from_template(Molecules, Particles):
    for name, mol in Molecules.items():
        if not dict_defines(mol, "molecule_type"):
            continue
        mol_type = mol["molecule_type"]
        if mol_type == "custom":
            continue
        if mol_type not in MOLECULE_TEMPLATES:
            raise Exception(f"Unsupported molecule_type: '{mol_type}'. Must be one of {list(MOLECULE_TEMPLATES.keys())} or 'custom'.")

        template_func = MOLECULE_TEMPLATES[mol_type]
        new_mol = template_func(mol, Particles)
        mol.update(new_mol)
    return Molecules


def compute_group_nums(mols):
    groups = dict()
    for name, mol in mols.items():
        if "group_name" in mol and mol["group_name"] is not None:
            if mol["group_name"] not in groups:
                groups[mol["group_name"]] = []
            groups[mol["group_name"]].append(mol)

    if len(groups) == 0:
        return mols

    for name, group in groups.items():
        balance_index = None
        num_mols = 0
        group_num = None
        for i, mol in enumerate(group):
            if group_num is None:
                group_num = mol["num_group"]
            if group_num != mol["num_group"]:
                raise Exception("All mols in a group must have the same num_group")
            if mol["group_frac"] == "balance":
                if balance_index is not None:
                    raise Exception("Cannot have more than one mol in a group be set to balance")
                balance_index = i
            else:
                mol["num_molecules"] = int(mol["num_group"] * mol["group_frac"])
                num_mols += mol["num_molecules"]

        mol = group[balance_index]

        if mol["num_group"] < num_mols:
            raise Exception(f"Group {name} has more molecules than intended")
        mol["num_molecules"] = mol["num_group"] - num_mols
    return mols
