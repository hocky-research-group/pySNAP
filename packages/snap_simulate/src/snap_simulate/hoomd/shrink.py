def shrink_box(sim,params,hoomd_objs = None):
    import numpy as np
    import hoomd
    import snap_simulate

    if "final_vol_frac" in params["box","shrink"]:
        params["box"]["vol_frac"] = params["box","shrink","final_vol_frac"]
    elif "final_area_frac" in params["box","shrink"]:
        params["box"]["area_frac"] = params["box","shrink","final_area_frac"]
    if "final_aspect_ratio" in params["box","shrink"]:
        params["box"]["aspect_ratio"] = params["box","shrink","final_aspect_ratio"]

    if "final_box_length" in params["box","shrink"]:
        new_box_length = params["box","shrink","final_box_length"]
    else:
        if "box_length" in params["box"]:
            params["box"].pop("box_length")
        new_box_length = snap_simulate.system.calc_box_length(params["box"],
                                                              params["molecules"],
                                                              params["particles"])
    if not np.iterable(new_box_length):
        dims = params["box","dimensions"]
        n_box_length = np.zeros(3)
        n_box_length[:dims] = new_box_length*np.ones(dims)
        new_box_length = n_box_length
    
    initial_box = sim.state.box
    final_box = hoomd.Box(*new_box_length)
    #final_box = hoomd.Box.from_box(initial_box)
    #final_box.volume = np.prod(new_box_length) 
                                               
    shrink_steps = int(params["box","shrink","total_steps"])
    ramp = hoomd.variant.Ramp(A=0,B=1,t_start=sim.timestep,t_ramp=shrink_steps)

    updater_period = int(params["box","shrink","updater_period"])
    if isinstance(updater_period,str):
        resize_trigger = hoomd_objs["triggers"][check_steps]
    else:
        resize_trigger = hoomd.trigger.Periodic(updater_period)

    try:
        variant = hoomd.variant.box.Interpolate(initial_box=initial_box,final_box=final_box,variant=ramp)
        box_resize = hoomd.update.BoxResize(trigger=resize_trigger,box=variant)
    except Exception:
        box_resize = hoomd.update.BoxResize(trigger=resize_trigger,
                                            box1=initial_box,
                                            box2=final_box,  
                                            variant=ramp)    
                                                       
    sim.operations.updaters.append(box_resize)
    sim.run(shrink_steps + 1)
    sim.operations.updaters.remove(box_resize)
    return
