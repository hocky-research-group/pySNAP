import json
import logging
import os
import sys
import numpy as np
from snap_simulate.tools import decode, dict_defines, get_options, recursive_print

logger = logging.getLogger("snap_simulate.hoomd.simulation")


def get_class(info, default, class_name=None):
    import hoomd
    if class_name is None:
        if "class" not in info:
            raise Exception("Class_name not supplied")
        class_name = info["class"]

    if "module" in info:
        mod_path = info["module"]
    else:
        mod_path = default

    mod = hoomd
    for path in mod_path:
        mod = getattr(mod, path)

    return getattr(mod, class_name)


def _build_bonded_potentials(info_dict, default_mod_path, name_title):
    print(f"{name_title}:")
    potentials = dict()
    types = info_dict["types"]
    specs = info_dict["specs"]

    for pot_class, pot_data in specs.items():
        pot_cls = get_class(pot_data, default_mod_path, pot_class)

        if pot_class == "Table":
            table = np.load(pot_data["table_file"])
            width = table.shape[2]
            pot = pot_cls(width)
            if default_mod_path[-1] == "bond":
                pot_data.setdefault("default_params", {})
                pot_data["default_params"]["U"] = np.zeros(width)
                pot_data["default_params"]["F"] = np.zeros(width)
                for i, params in enumerate(pot_data["params"].values()):
                    params["U"] = table[i, 0]
                    params["F"] = table[i, 1]
            else:
                pot_data["default_params"] = {"U": np.zeros(width), "tau": np.zeros(width)}
                for i, params in enumerate(pot_data["params"].values()):
                    params["U"] = table[i, 0]
                    params["tau"] = table[i, 1]
        else:
            pot = pot_cls()

        print("    ", pot_class, ":")
        print("    " * 2, "Default parameters:")
        print("    " * 3, pot_data["default_params"])
        for t in types:
            pot.params[t] = pot_data["default_params"]

        print("    " * 2, "Specified parameters:")
        for t, params in pot_data["params"].items():
            pot.params[t] = params
            print("    " * 3, t, " ", params)
        potentials[pot_class] = pot
        print()
    return potentials


def build_angles(Angles):
    return _build_bonded_potentials(Angles, ["md", "angle"], "Angles")


def build_bonds(Bonds):
    return _build_bonded_potentials(Bonds, ["md", "bond"], "Bonds")


def build_computes(Computes, hoomd_objs):
    import hoomd
    print("Computes:")
    computes = dict()
    for comp_name, comp_info in Computes.items():
        comp_class = get_class(comp_info, ["md", "compute"])
        options = get_options(comp_info)

        comp_filter = hoomd_objs["filters"][comp_info['filter']]
        comp = comp_class(comp_filter, **options)
        computes[comp_name] = comp
        print("    ", comp_name, comp_info["class"])
        print("    " * 2, "Filter:", comp_info["filter"])
        print("    " * 2, "Options:", options)
        print()

    return computes


def build_dihedrals(Dihedrals):
    return _build_bonded_potentials(Dihedrals, ["md", "dihedral"], "Dihedrals")

def _resolve_dybond_rates(spec_name, spec_info, dt_check):
    import math

    has_kon = "kon" in spec_info and spec_info["kon"] is not None
    has_koff = "koff" in spec_info and spec_info["koff"] is not None

    eps_key = None
    for k in ("epsilon", "eps", "E"):
        if k in spec_info and spec_info[k] is not None:
            eps_key = k
            break

    pon_key = None
    for k in ("Pon", "pon", "P_on"):
        if k in spec_info and spec_info[k] is not None:
            pon_key = k
            break

    has_eps = eps_key is not None
    has_pon = pon_key is not None

    kon_val = float(spec_info["kon"]) if has_kon else None
    koff_val = float(spec_info["koff"]) if has_koff else None
    eps_val = float(spec_info[eps_key]) if has_eps else None
    pon_val = float(spec_info[pon_key]) if has_pon else None

    # Step 1: Resolve kon from Pon if specified, and validate if kon was also specified
    kon = None
    if has_pon:
        expected_kon = pon_val / dt_check
        if has_kon:
            if not math.isclose(kon_val, expected_kon, rel_tol=1e-4, abs_tol=1e-8):
                raise ValueError(
                    f"Inconsistent dybond spec '{spec_name}': specified kon ({kon_val}) does not match "
                    f"Pon ({pon_val}) given dt_check={dt_check} (expected kon={expected_kon})."
                )
            kon = kon_val
        else:
            kon = expected_kon
    elif has_kon:
        kon = kon_val

    # Step 2: Resolve koff and epsilon relationship
    koff = None
    if has_eps:
        expected_ratio = math.exp(eps_val)
        if has_koff and kon is not None:
            if koff_val <= 0:
                raise ValueError(f"Inconsistent dybond spec '{spec_name}': koff must be > 0 when epsilon is specified, got {koff_val}.")
            actual_ratio = kon / koff_val
            actual_eps = math.log(actual_ratio)
            if not math.isclose(actual_eps, eps_val, rel_tol=1e-4, abs_tol=1e-8):
                raise ValueError(
                    f"Inconsistent dybond spec '{spec_name}': specified epsilon ({eps_val}) does not match "
                    f"kon={kon} and koff={koff_val} (implied epsilon={actual_eps})."
                )
            koff = koff_val
        elif has_koff:
            koff = koff_val
            kon = koff * expected_ratio
        elif kon is not None:
            koff = kon * math.exp(-eps_val)
        else:
            raise ValueError(
                f"Incomplete dybond spec '{spec_name}': epsilon ({eps_val}) was specified without 'kon', 'Pon', or 'koff'. "
                f"At least one transition rate or probability must be specified."
            )
    else:
        if kon is None or koff_val is None:
            raise KeyError(
                f"Missing required rate parameter for dybond spec '{spec_name}': both 'kon' (or 'Pon') and 'koff' "
                f"(or an 'epsilon' relationship) must be specified."
            )
        koff = koff_val

    return kon, koff


def build_dybond(Dybond,snap,dt,seed,hoomd_objs):# {{{
    import hoomd
    from hoomd.dybond import DyBondUpdater

    print("Dybond:")
    
    # 1. Parse shared updater parameters
    if "nlist" not in Dybond:
        raise KeyError("Missing required parameter 'nlist' in dybond configuration.")
    nlist_name = Dybond["nlist"]
    nlist = hoomd_objs["nlists"][nlist_name]
    
    if "thermo" not in Dybond:
        raise KeyError("Missing required parameter 'thermo' in dybond configuration.")
    thermo_name = Dybond["thermo"]
    thermo = hoomd_objs["computes"][thermo_name]
    
    if "trigger" not in Dybond:
        raise KeyError("Missing required parameter 'trigger' in dybond configuration.")
    trigger_spec = Dybond["trigger"]
    if isinstance(trigger_spec, str):
        trigger = hoomd_objs["triggers"][trigger_spec]
        period = getattr(trigger, "period", 100)
    elif isinstance(trigger_spec, hoomd.trigger.Trigger):
        trigger = trigger_spec
        period = getattr(trigger, "period", 100)
    else:
        period = int(trigger_spec)
        trigger = hoomd.trigger.Periodic(period)
        
    dt_check = float(period) * float(dt)
    nearest_neighbor = Dybond.get("nearestNeighbor", True)
    
    print("    ", "nlist:", nlist_name)
    print("    ", "thermo:", thermo_name)
    print("    ", "trigger:", trigger_spec)
    print("    ", "nearestNeighbor:", nearest_neighbor)
    print()

    # 2. Construct DyBondUpdater
    updater = DyBondUpdater(
        trigger=trigger,
        nlist=nlist,
        thermo=thermo,
        nearestNeighbor=nearest_neighbor
    )
    
    # 3. Add specifications to the updater
    specs = Dybond.get("specs", {})
    for spec_name, spec_info in specs.items():
        pair = spec_info["pair"]
        bond_name = spec_info["bond"]
        bond = hoomd_objs["bonds"][bond_name]
        
        kon, koff = _resolve_dybond_rates(spec_name, spec_info, dt_check)

        if "rmin" not in spec_info:
            raise KeyError(f"Missing required parameter 'rmin' for dybond spec '{spec_name}'.")
        if "rmax" not in spec_info:
            raise KeyError(f"Missing required parameter 'rmax' for dybond spec '{spec_name}'.")
        if "selfAvoidFlag" not in spec_info:
            raise KeyError(f"Missing required parameter 'selfAvoidFlag' for dybond spec '{spec_name}'.")

        # Build options dictionary for DyBond updater __setitem__
        val_dict = {
            "bond": bond,
            "kon": kon,
            "koff": koff,
            "rmin": float(spec_info["rmin"]),
            "rmax": float(spec_info["rmax"]),
            "metropolisFlag": spec_info.get("metropolisFlag", True),
            "selfAvoidFlag": bool(spec_info["selfAvoidFlag"])
        }
        
        has_typename = "bond_typename" in spec_info
        has_typeid = "bond_typeid" in spec_info
        if has_typename and has_typeid:
            raise ValueError(f"Only one of 'bond_typename' or 'bond_typeid' can be specified in dybond spec '{spec_name}', not both.")
        if has_typename:
            val_dict["bond_typename"] = spec_info["bond_typename"]
        elif has_typeid:
            val_dict["bond_typeid"] = spec_info["bond_typeid"]
        else:
            raise KeyError(f"Each dybond spec requires either 'bond_typename' or 'bond_typeid', none specified in '{spec_name}'.")
        
        if "force_a" in spec_info:
            val_dict["force_a"] = spec_info["force_a"]
            
        if "Tmelt" in spec_info:
            val_dict["Tmelt"] = spec_info["Tmelt"]
            if "alpha" in spec_info:
                val_dict["alpha"] = spec_info["alpha"]
            if "kon_melt" in spec_info:
                val_dict["kon_melt"] = spec_info["kon_melt"]
            if "koff_melt" in spec_info:
                val_dict["koff_melt"] = spec_info["koff_melt"]
                
        # Register the key-value pair on the updater
        key = (pair[0], pair[1])
        updater[key] = val_dict
        
        print("    ", spec_name, ":")
        print("    " * 2, "Pair:", pair)
        print("    " * 2, "Bond:", bond_name)
        print("    " * 2, "Parameters:")
        print("    " * 3, f"kon: {kon}")
        print("    " * 3, f"koff: {koff}")
        for k, v in spec_info.items():
            if k not in ("pair", "bond", "kon", "koff"):
                print("    " * 3, f"{k}: {v}")
        print()
        
    return updater# }}}
def build_filters(Filter):# {{{
    import hoomd
    filters = {}
    print("Filters:")
    for filt_name, filt_info in Filter.items():
        filt_class = get_class(filt_info,["filter"])
        print("    ",filt_name,filt_info['class'])

        options = get_options(filt_info)
        # A parameter file has no tuples, and some filters insist on one:
        # hoomd.filter.Rigid takes its flags as a tuple and refuses a list.
        options = {key: tuple(value) if isinstance(value, list) else value
                   for key, value in options.items()}
        if filt_info["composite"]:
            filt_comps = [filters[name] for name in options]
            print("    "*2,"Components: ", options)
            filter = filt_class(*filt_comps)
        else:
            print("    "*2,"Options: ", options)
            filter = filt_class(**options)

        filters[filt_name] = filter
        print()

    return filters# }}}
def build_integrator(int_info, hoomd_objs):# {{{
    import hoomd
    print("Integrator:")
    options = get_options(int_info)
    if dict_defines(int_info,"dt") and not dict_defines(options,"dt"):
        options["dt"] = int_info["dt"]
    print("    ", "Options: ", options)
    integrator = hoomd.md.Integrator(**options)

    method_info = int_info["method"]
    method_class = get_class(method_info,["md","methods"])
    raw_method_options = get_options(method_info)
    method_options = dict(raw_method_options)

    filter = hoomd_objs["filters"][method_info["filter"]]
    method_options["filter"] = filter

    print("    ","Method: ", method_info['class'])
    print("    "*2,"Filter: ", method_info['filter'])

    if "thermostat" in method_info and method_info["thermostat"] is not None:
        thermostat_info = method_info["thermostat"]
        thermostat_class = get_class(thermostat_info,["md","methods","thermostats"])
        thermostat_options = get_options(thermostat_info)
        thermostat = thermostat_class(**thermostat_options)
        method_options["thermostat"] = thermostat
        print("    "*2,"Thermostat: ", thermostat_info['class'])
        print("    "*3,"Options: ", thermostat_options)

    print("    "*2,"Options: ", raw_method_options)

    method = method_class(**method_options)

    if "gamma" in method_info:
        print("    "*2,"Gamma:")
        for particle,gamma in method_info['gamma'].items():
            print("    "*3, particle, ": ", gamma)
            method.gamma[particle] = gamma

    integrator.methods.append(method)
    print()

    return integrator
# }}}
def build_json(file_name):# {{{
    import hoomd
    json_string = ''
    with open(file_name,'r') as file:
        while line := file.readline():
            index = line.find("#")
            if index != -1:
                line = line[:index] + '\n'
            json_string += line
    return json.loads(json_string)# }}}
def build_loggers(Loggers, obj_dict):# {{{
    import hoomd
    loggers = dict()
    print("Loggers:")
    for log_name, log_info in Loggers.items():
        print("    ",log_name)
        options = get_options(log_info)
        print("    "*2,"Categories:",log_info["categories"])
        print("    "*2,"Options:",options)
        logger = hoomd.logging.Logger(categories = log_info["categories"], **options)
        print("    "*2,"Quantities:")
        for (obj_path, log_quants) in log_info["loggables"]:
            obj = obj_dict
            for next_path in obj_path:
                obj = obj[next_path]
            print("    "*3,"Object: ",obj_path)
            print("    "*3,"Quantities: ", log_quants)
            print("    "*3)
            logger.add(obj,log_quants)
        loggers[log_name] = logger
        print()
    return loggers# }}}
def build_nlist(Nlist):# {{{
    import hoomd
    nlists = dict()
    print("Neighbor Lists:")
    for nlist_name, nlist_info in Nlist.items():
        print("    ",nlist_name,nlist_info["class"])
        nlist_class = get_class(nlist_info,["md","nlist"])
        options = get_options(nlist_info)
        print("    "*2,"Options: ", options)
        nlists[nlist_name] = nlist_class(**options)
        print()
    return nlists# }}}
def build_pairs(Pairs,atom_types,nlists):# {{{
    import hoomd
    pair_dict = dict()
    print("Pair Potentials:")
    for pair_name, pair_info in Pairs.items():
        if "class" in pair_info:
            pair_class = pair_info["class"] 
        else:
            pair_class = pair_name

        print("    ",pair_class,":")
        pair= get_class(pair_info,["md","pair"],pair_class)
        options = get_options(pair_info)

        pair_defaults = pair_info["default_params"]

        # Support nlist (preferred default) or nlist_name
        n_key = pair_info.get("nlist", pair_info.get("nlist_name"))
        if n_key is None:
            raise KeyError(f"Neighbor list key 'nlist' or 'nlist_name' must be specified for pair potential '{pair_name}'")
        nlist = nlists[n_key]

        if pair_class == "Table":
            import numpy as np
            pair = pair(nlist, **options)
            pair_info["default_params"] = {"r_min":0,"U":np.zeros(1),"F":np.zeros(1)}
            for i,params in enumerate(pair_info["params"].values()):
                if "table_file" in params[-1]:
                    table = np.load(params[-1].pop("table_file"))
                    params[-1]["U"] = table[0]
                    params[-1]["F"] = table[1]
        else:
            pair = pair(nlist, **options)


        print("    "*2,"Options:")
        print("    "*3, options)
        print("    "*2,"Default parameters:")
        print("    "*3,pair_defaults)

        for i,atom1 in enumerate(atom_types):
            for j,atom2 in enumerate(atom_types[i:]):
                pair.params[atom1,atom2] = pair_defaults
            
        print("    "*2,"Specified parameters:")
        for atom1,atom2,pair_params in pair_info["params"].values():
            pair.params[atom1,atom2] = pair_params
            print("    "*3,atom1, atom2, pair_params)
    
        print("    "*2,"Specified rcuts:")
        for atom1,atom2,pair_cut in pair_info["rcuts"].values():
            pair.r_cut[atom1,atom2] = pair_cut
            print("    "*3, atom1, atom2, pair_cut)
    
        pair_dict[pair_name] = pair
        print()
    return pair_dict# }}}
def build_rigid(particles,molecules):# {{{
        from snap_simulate.system import build_rigid
        import hoomd
        rigid = hoomd.md.constrain.Rigid()
        from snap_simulate.system.rigid import rigid_constituents
        for mol_name,mol in molecules.items():
            if not dict_defines(mol,"rigid") or not mol["rigid"]:
                continue
            _,_,_,orientations = build_rigid(mol,particles["mass"],particles["diameters"])
            positions = mol["particle_positions"]
            type_id = mol["particle_typeid"]
            names = np.array(particles["types"])[type_id]
            # A molecule may be rigid only in its core, the rest of it staying free.
            last = rigid_constituents(mol, len(type_id)) + 1

            rigid.body[names[0]] = {
                                "constituent_types" : names[1:last],
                                "positions"   : positions[1:last],
                                "orientations" : orientations[1:last]}
        return rigid
    #}}}
#: Where a stage records the timestep it began at, so a resumed run knows how much of
#: its length it has already covered.
STAGE_START_FILE = "stage_start_timestep.txt"


def stage_trajectory_files(params):# {{{
    """Return the GSD trajectory filenames this stage writes.

    params: the parameter tree, whose "writers" section declares the output.
    """
    writers = params["writers"] if dict_defines(params, "writers") else {}
    paths = []
    for info in (writers or {}).values():
        if not isinstance(info, dict) or info.get("class") != "GSD":
            continue
        filename = (info.get("options") or {}).get("filename")
        if filename:
            paths.append(filename)
    return paths# }}}


def _has_frames(path):# {{{
    """Return True if `path` is a GSD file holding at least one frame."""
    import gsd.hoomd
    if not os.path.isfile(path):
        return False
    try:
        with gsd.hoomd.open(path) as traj:
            return len(traj) > 0
    except Exception:
        return False# }}}


def resolve_continuation(params):# {{{
    """Return the trajectory this stage should resume from, or None to start fresh.

    A `continue_file` named in the simulation parameters wins. Otherwise a stage
    resumes from its own trajectory, which is what makes a stage restartable by
    submitting it again: the run left off where that file ends.

    params: the parameter tree.
    """
    sim_info = params["simulation"]
    explicit = sim_info.get("continue_file") if hasattr(sim_info, "get") else None
    if explicit:
        return explicit if _has_frames(explicit) else None
    for path in stage_trajectory_files(params):
        if _has_frames(path):
            return path
    return None# }}}


def _append_to_continued_trajectories(params, continue_path):# {{{
    """Switch the GSD writer that owns `continue_path` to appending.

    A writer left in "wb" truncates on the next run, destroying the very trajectory the
    run resumed from.

    params: the parameter tree, modified in place.
    continue_path: the trajectory being resumed from.
    """
    writers = params["writers"] if dict_defines(params, "writers") else {}
    for info in (writers or {}).values():
        if not isinstance(info, dict) or info.get("class") != "GSD":
            continue
        options = info.setdefault("options", {})
        if options.get("filename") == continue_path:
            options["mode"] = "ab"# }}}


def _record_stage_start(timestep):# {{{
    """Write the timestep this stage began at, for a later resumption to read."""
    try:
        with open(STAGE_START_FILE, "w") as f:
            f.write(str(int(timestep)))
    except OSError as err:
        logger.warning("Could not record the stage start timestep: %s", err)# }}}


def stage_start_timestep(sim, continue_path=None):# {{{
    """Return the timestep at which this stage began.

    Read from the file the stage wrote when it first ran. Where that is missing — a run
    started before this was recorded — the first frame of the trajectory being resumed
    from is used instead, which is accurate to one output period.

    sim: the simulation, whose timestep gives the answer on a fresh start.
    continue_path: the trajectory being resumed from, if any.
    """
    if os.path.isfile(STAGE_START_FILE):
        try:
            with open(STAGE_START_FILE) as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            pass
    if continue_path and _has_frames(continue_path):
        import gsd.hoomd
        with gsd.hoomd.open(continue_path) as traj:
            return int(traj[0].configuration.step)
    return int(sim.timestep)# }}}


def remaining_steps(sim, total_steps, continue_path=None):# {{{
    """Return how many of this stage's steps are left to run.

    A stage that was interrupted and submitted again picks up the steps it has yet to
    run; one that already finished its length returns zero rather than running again.

    sim: the simulation, already restored to where the stage left off.
    total_steps: the stage's full length, from run_details.
    continue_path: the trajectory resumed from, if any.
    """
    start = stage_start_timestep(sim, continue_path)
    done = max(0, int(sim.timestep) - start)
    return max(0, int(total_steps) - done)# }}}


def build_simulation(params, output_file = None, print_objs = False):# {{{
    import hoomd
    from datetime import datetime
    hoomd_objects = dict()
    #---- Output file controls ---- {{{
    if output_file is not None:
        if not isinstance(output_file,str):
            output_file = "build_sim.log"
        file = open(output_file,'a')

        stdout_default = sys.stdout
        sys.stdout = file
        time = datetime.today().strftime('%Y-%m-%d %H:%M:%S')
        print('\n\n\n',time)
    # }}}
    #---- Filters ---- {{{
    filters = dict()
    if "filters" in params:
        general_filters = build_filters(params["filters"])
        filters.update(general_filters)
    hoomd_objects["filters"] = filters
    #}}}
    #---- Triggers ---- {{{
    triggers = dict()
    if "triggers" in params:
        general_triggers = build_triggers(params["triggers"])
        triggers.update(general_triggers)
    hoomd_objects["triggers"] = triggers
    #}}}
    #---- General (Seed/Device/Initialization) ---- {{{
    if "simulation" in params:
        sim_info = params['simulation']
    else:
        raise Exception("Must have simulation data specified")

    if sim_info["device"] == "GPU":
        if "GPUID" in sim_info:
            proc = hoomd.device.GPU(gpu_ids=[sim_info["GPUID"]])
        else:
            proc = hoomd.device.GPU()
    elif sim_info["device"] == "CPU":
        proc = hoomd.device.CPU()
    else:
        raise ValueError(f"Device should be set to either CPU or GPU in simulation specs")

    if "random_seed" in sim_info and sim_info["random_seed"]:
        if os.path.isfile("seed.txt"):
            seed = np.loadtxt("seed.txt").astype(int).take(0)
        else:
            seed = int.from_bytes(os.urandom(2), "big")
            np.savetxt("seed.txt", [seed])
    elif "seed" in sim_info:
        seed = sim_info["seed"]
    else:
        raise Exception("'seed' or 'random seed' must be set")
    

    sim = hoomd.Simulation(device=proc, seed=seed)
    # A stage resumes from its own trajectory when one is there, so re-submitting an
    # interrupted stage continues it instead of starting over.
    continue_path = resolve_continuation(params)
    if continue_path:
        sim_info = dict(sim_info)
        sim_info["continue_file"] = continue_path
    continue_successful = _set_initial_configuration(sim, sim_info, "continue_file")
    if continue_successful:
        _append_to_continued_trajectories(params, continue_path)
    if not continue_successful:
        init_successful = _set_initial_configuration(sim, sim_info, "init_file")
        if not init_successful:
            raise Exception("No suitable initial configuration found: 'continue_file' and/or 'init_file' either not set or not pointing to valid configurations")
        if dict_defines(sim_info, "thermalize_initial"):
            therm_info = sim_info["thermalize_initial"]
            therm_options = get_options(therm_info)
            therm_options["filter"] = hoomd_objects["filters"][therm_info["filter"]]
            sim.state.thermalize_particle_momenta(**therm_options)

    if not continue_successful:
        _record_stage_start(sim.timestep)
    hoomd_objects["simulation"] = sim
    hoomd_objects["continue_file"] = continue_path if continue_successful else None

    # ---- Integrator ----
    if "integrator" in params:
        int_info = params["integrator"]
    else:
        raise Exception("Integrator information must be defined to build a simulation")
    integrator = build_integrator(int_info, hoomd_objects)

    if dict_defines(sim_info,"has_rigid_bodies") and sim_info["has_rigid_bodies"]:
        if not dict_defines(params,"molecules") or not dict_defines(params, "particles"):
            raise Exception("Molecule and particle data must be supplied if system "\
                             +"is to be built with rigid bodies")
        rigid = build_rigid(params["particles"],params["molecules"])
        integrator.rigid = rigid

    sim.operations.integrator = integrator
    hoomd_objects["integrator"] = integrator
    #}}}
    #---- NeighborList ---- {{{
    nlists = dict()
    if "nlist" in params:
        general_nlists = build_nlist(params["nlist"])
        nlists.update(general_nlists)
    hoomd_objects["nlists"] = nlists
    #}}}
    #---- Pair Potentials ----{{{
    atom_types = params["particles","types"]
    pairs = dict()

    if "pairs" in params:
        general_pairs = build_pairs(params['pairs'],atom_types,nlists)
        pairs.update(general_pairs)

    for pair in pairs.values():
        integrator.forces.append(pair)
    hoomd_objects["pairs"] = pairs
    #}}}
    #---- Bonds ---- {{{
    bonds = dict()

    if 'bonds' in params:
        general_bonds = build_bonds(params['bonds'])
        bonds.update(general_bonds)

    for bond in bonds.values():
        integrator.forces.append(bond)
    hoomd_objects["bonds"] = bonds
    #}}}
    #---- Angles ---- {{{
    angles = dict()

    if 'angles' in params:
        general_angles = build_angles(params['angles'])
        angles.update(general_angles)

    for angle in angles.values():
        integrator.forces.append(angle)
    hoomd_objects["angles"] = angles
    #}}}
    #---- Dihedrals ---- {{{
    dihedrals = dict()

    if 'dihedrals' in params:
        general_dihedrals = build_dihedrals(params['dihedrals'])
        dihedrals.update(general_dihedrals)

    for dihedral in dihedrals.values():
        integrator.forces.append(dihedral)
    hoomd_objects["dihedrals"] = dihedrals
    #}}}
    #---- Computes ---- {{{
    computes = dict()

    if 'computes' in params:
        general_computes = build_computes(params["computes"],hoomd_objects)
        computes.update(general_computes)

    for compute in computes.values():
        sim.operations.computes.append(compute)

    hoomd_objects["computes"] = computes
    #}}}
    #---- Dybond ---- {{{
    if 'dybond' in params:
        dybond =  build_dybond(params["dybond"],
                               sim.state.get_snapshot(),
                               sim.operations.integrator.dt,
                               sim.seed,
                               hoomd_objects)
        hoomd_objects["dybond"] = dybond
        sim.operations.updaters.append(dybond)
    #}}}
    #---- Loggers ---- {{{
    loggers = dict()
    if 'loggers' in params:
        general_loggers = build_loggers(params["loggers"],hoomd_objects)
        loggers.update(general_loggers)

    hoomd_objects["loggers"] = loggers
    #}}}
    #---- Writers ---- {{{
    writers = dict()
    if 'writers' in params:
        general_writers = build_writers(params["writers"],hoomd_objects)
        writers.update(general_writers)

    for writer in writers.values():
        sim.operations.writers.append(writer)
    hoomd_objects["writers"] = writers
    #}}}
    #---- Output file controls ---- {{{
    if output_file is not None:
        file.close()
        sys.stdout = stdout_default
    # }}}
    if print_objs:
        recursive_print(hoomd_objects)
    return sim, hoomd_objects
# }}}
def build_triggers(trigger_dict):# {{{
    import hoomd
    triggers = {}
    print("Triggers:")
    for trig_name, trig_info in trigger_dict.items():
        print("    ",trig_name, trig_info['class'])
        trig_class = get_class(info = trig_info, default = ["trigger"])
        options = get_options(trig_info)

        if trig_info["composite"]:
            print("    "*2,"Components: ", options)
            logic_triggers = [triggers[name] for name in options]
            trigger = trig_class(logic_triggers)
        else:
            print("    "*2,"Options: ", options)
            if isinstance(options,list):
                trigger = trig_class(*options)
            if isinstance(options,dict):
                trigger = trig_class(**options)
        triggers[trig_name] = trigger
        print()

    return triggers# }}}
def build_writers(Writers, obj_dict):# {{{
    import hoomd
    writers = {}
    print("Writers:")
    for writer_name, writer_info in Writers.items():
        print("    ", writer_name, writer_info["class"])
        options = get_options(writer_info)
        print("    "*2, "Options: ", options)

        if "trigger" in writer_info:
            trigger_info = writer_info["trigger"]
            if isinstance(trigger_info, str):
                print("    " * 2, "trigger: ", trigger_info)
                trigger = obj_dict["triggers"][trigger_info]
            else:
                raise TypeError(f"Cannot build info of type {type(trigger_info)} into a trigger")
            options["trigger"] = trigger

        if "logger" in writer_info:
            logger_info = writer_info["logger"]

            if isinstance(logger_info, str):
                print("    " * 2, "logger: ", logger_info)
                logger_name = logger_info
                logger_obj = obj_dict["loggers"][logger_name]
            else:
                raise TypeError(f"Cannot build info of type {type(logger_info)} into a logger")

            options["logger"] = logger_obj

        if "filter" in writer_info:
            filter_info = writer_info["filter"]
            if isinstance(filter_info, str):
                print("    " * 2, "filter: ", filter_info)
                filter_obj = obj_dict["filters"][filter_info]
            else:
                raise TypeError(f"Cannot build info of type {type(filter_info)} into a filter")
            options["filter"] = filter_obj

        writer_class = get_class(writer_info,["write"])
        writer = writer_class(**options)
        writers[writer_name] = writer
        print()

    return writers# }}}
def _set_initial_configuration(sim,sim_info,path_name):# {{{
    import gsd.hoomd
    if path_name not in sim_info:
        return False

    init_path = sim_info[path_name]
    if not os.path.isfile(init_path):
        return False

    with gsd.hoomd.open(init_path) as traj:
        if len(traj) == 0:
            return False 

        frame = traj[-1]
        timestep = frame.configuration.step

        sim.timestep = timestep
        sim.create_state_from_snapshot(frame)
    return True # }}}
