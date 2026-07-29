def __getattr__(name):
    if name in ("send_request", "worker_loop", "detect_system_resources", "parse_memory_to_gb"):
        from . import runner
        return getattr(runner, name)
    elif name in ("launch_local_workers", "launch_remote_workers"):
        from . import slurm
        return getattr(slurm, name)
    elif name == "setup_remote_cluster":
        from snap_workflow.remote.setup import setup_remote_cluster
        return setup_remote_cluster
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "send_request",
    "worker_loop",
    "detect_system_resources",
    "parse_memory_to_gb",
    "launch_local_workers",
    "launch_remote_workers",
    "setup_remote_cluster"
]
