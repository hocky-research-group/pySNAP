def __getattr__(name):
    if name in ("send_request", "dispatcher_loop", "worker_loop", "subprocess_dispatcher_loop", "detect_system_resources", "parse_memory_to_gb", "SubprocessDispatcher"):
        from . import runner
        return getattr(runner, name)
    elif name in ("BaseDispatcher",):
        from . import base
        return getattr(base, name)
    elif name in ("SlurmDispatcher", "slurm_dispatcher_loop"):
        from . import slurm
        return getattr(slurm, name)
    elif name in ("DispatcherController",):
        from . import controller
        return getattr(controller, name)
    elif name in ("ResourcePool",):
        from . import resource_allocator
        return getattr(resource_allocator, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "BaseDispatcher",
    "SubprocessDispatcher",
    "SlurmDispatcher",
    "DispatcherController",
    "send_request",
    "dispatcher_loop",
    "worker_loop",
    "subprocess_dispatcher_loop",
    "slurm_dispatcher_loop",
    "detect_system_resources",
    "parse_memory_to_gb",
    "ResourcePool",
]
