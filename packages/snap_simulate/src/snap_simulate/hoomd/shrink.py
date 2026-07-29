import hoomd
import numpy as np
import snap_simulate


def shrink_box(
    sim,
    params=None,
    total_steps=None,
    updater_period=None,
    final_box_length=None,
    final_vol_frac=None,
    final_area_frac=None,
    final_aspect_ratio=None,
    molecules=None,
    particles=None,
    dimensions=None,
    hoomd_objs=None,
):
    """Shrink the HOOMD simulation box to a target box length, volume fraction, or area fraction.

    Accepts parameters either via a nested ``params`` dictionary/object or via direct kwargs.
    """
    box_cfg = {}
    shrink_cfg = {}

    if params is not None:
        # Resolve box config
        if hasattr(params, "__getitem__"):
            try:
                if "box" in params and isinstance(params["box"], (dict, object)):
                    box_cfg = params["box"]
            except Exception:
                pass

        # Resolve shrink config: check ("box", "shrink"), "box" -> "shrink", then top-level "shrink"
        if hasattr(params, "__getitem__"):
            try:
                if ("box", "shrink") in params:
                    shrink_cfg = params["box", "shrink"]
                elif "box" in params and hasattr(params["box"], "__getitem__") and "shrink" in params["box"]:
                    shrink_cfg = params["box"]["shrink"]
                elif "shrink" in params and isinstance(params["shrink"], dict):
                    shrink_cfg = params["shrink"]
            except Exception:
                pass

        if molecules is None and hasattr(params, "__getitem__"):
            try:
                if "molecules" in params:
                    molecules = params["molecules"]
            except Exception:
                pass

        if particles is None and hasattr(params, "__getitem__"):
            try:
                if "particles" in params:
                    particles = params["particles"]
            except Exception:
                pass

    # Resolve values with precedence: explicit kwarg > shrink_cfg / box_cfg
    if total_steps is None:
        total_steps = shrink_cfg.get("total_steps") if isinstance(shrink_cfg, dict) else None
    if total_steps is None:
        raise ValueError("shrink_box requires 'total_steps' specified in kwargs or params.")
    total_steps = int(total_steps)

    if updater_period is None:
        updater_period = shrink_cfg.get("updater_period", 100) if isinstance(shrink_cfg, dict) else 100

    if final_box_length is None and isinstance(shrink_cfg, dict):
        final_box_length = shrink_cfg.get("final_box_length")

    if final_vol_frac is None and isinstance(shrink_cfg, dict):
        final_vol_frac = shrink_cfg.get("final_vol_frac")

    if final_area_frac is None and isinstance(shrink_cfg, dict):
        final_area_frac = shrink_cfg.get("final_area_frac")

    if final_aspect_ratio is None and isinstance(shrink_cfg, dict):
        final_aspect_ratio = shrink_cfg.get("final_aspect_ratio")

    if dimensions is None:
        if isinstance(box_cfg, dict) and "dimensions" in box_cfg:
            dimensions = box_cfg["dimensions"]
        elif hasattr(params, "__getitem__"):
            try:
                if ("box", "dimensions") in params:
                    dimensions = params["box", "dimensions"]
            except Exception:
                pass
    if dimensions is None:
        dimensions = 3

    # Calculate target box length
    if final_box_length is not None:
        new_box_length = final_box_length
    else:
        calc_box_cfg = dict(box_cfg) if isinstance(box_cfg, dict) else {}
        calc_box_cfg["dimensions"] = dimensions
        if final_vol_frac is not None:
            calc_box_cfg["vol_frac"] = final_vol_frac
            calc_box_cfg.pop("box_length", None)
            calc_box_cfg.pop("area_frac", None)
        if final_area_frac is not None:
            calc_box_cfg["area_frac"] = final_area_frac
            calc_box_cfg.pop("box_length", None)
            calc_box_cfg.pop("vol_frac", None)
        if final_aspect_ratio is not None:
            calc_box_cfg["aspect_ratio"] = final_aspect_ratio

        if molecules is None or particles is None:
            raise ValueError("molecules and particles must be provided to compute target box length from volume/area fraction.")

        new_box_length = snap_simulate.system.calc_box_length(
            calc_box_cfg,
            molecules,
            particles
        )

    if not np.iterable(new_box_length):
        n_box_length = np.zeros(3)
        n_box_length[:dimensions] = new_box_length * np.ones(dimensions)
        new_box_length = n_box_length

    if isinstance(box_cfg, dict):
        box_cfg["box_length"] = list(new_box_length)
        box_cfg.pop("vol_frac", None)
        box_cfg.pop("area_frac", None)

    initial_box = sim.state.box
    final_box = hoomd.Box(*new_box_length)

    ramp = hoomd.variant.Ramp(A=0, B=1, t_start=sim.timestep, t_ramp=total_steps)

    if isinstance(updater_period, str):
        if hoomd_objs is not None and "triggers" in hoomd_objs:
            resize_trigger = hoomd_objs["triggers"][updater_period]
        else:
            raise ValueError(f"Trigger key '{updater_period}' not found in hoomd_objs['triggers']")
    elif isinstance(updater_period, hoomd.trigger.Trigger):
        resize_trigger = updater_period
    else:
        resize_trigger = hoomd.trigger.Periodic(int(updater_period))

    try:
        variant = hoomd.variant.box.Interpolate(
            initial_box=initial_box, final_box=final_box, variant=ramp
        )
        box_resize = hoomd.update.BoxResize(trigger=resize_trigger, box=variant)
    except Exception:
        box_resize = hoomd.update.BoxResize(
            trigger=resize_trigger,
            box1=initial_box,
            box2=final_box,
            variant=ramp
        )

    sim.operations.updaters.append(box_resize)
    sim.run(total_steps + 1)
    sim.operations.updaters.remove(box_resize)
    return


