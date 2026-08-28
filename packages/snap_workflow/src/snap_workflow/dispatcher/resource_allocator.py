import os
import threading
import logging
from typing import List, Tuple, Set, Optional

logger = logging.getLogger(__name__)


class ResourcePool:
    """
    Manages atomic checkout and checkin of GPU device IDs and CPU core IDs.
    
    GPU IDs: Subset of visible GPUs (parsed from CUDA_VISIBLE_DEVICES or detected via system).
    CPU Core IDs: Subset of allowed CPU cores (parsed from os.sched_getaffinity(0) or system cores).
    """

    def __init__(self, cpus_total: Optional[int] = None, gpus_total: Optional[int] = None):
        self._lock = threading.Lock()

        if cpus_total is not None and cpus_total > 0:
            self.all_cpus: List[int] = list(range(cpus_total))
        else:
            # Detect baseline CPU cores
            if hasattr(os, "sched_getaffinity"):
                try:
                    self.all_cpus = sorted(list(os.sched_getaffinity(0)))
                except Exception:
                    self.all_cpus = list(range(os.cpu_count() or 1))
            else:
                self.all_cpus = list(range(os.cpu_count() or 1))

        # Detect baseline GPU IDs
        cuda_vis = os.getenv("CUDA_VISIBLE_DEVICES")
        if cuda_vis is not None and cuda_vis.strip().lower() in ("none", "void", "-1"):
            self.all_gpus: List[int] = []
        elif cuda_vis is not None and any(x.strip().isdigit() for x in cuda_vis.split(",")):
            try:
                self.all_gpus = [int(x.strip()) for x in cuda_vis.split(",") if x.strip().isdigit()]
            except Exception:
                self.all_gpus = []
            if gpus_total is not None and gpus_total >= 0 and gpus_total < len(self.all_gpus):
                self.all_gpus = self.all_gpus[:gpus_total]
        elif gpus_total is not None:
            if gpus_total <= 0:
                self.all_gpus = []
            else:
                self.all_gpus = list(range(gpus_total))
        else:
            try:
                from snap_workflow.dispatcher.runner import detect_system_resources
                _, detected_gpus, _ = detect_system_resources()
                if detected_gpus > 0:
                    self.all_gpus = list(range(detected_gpus))
                else:
                    self.all_gpus = []
            except Exception:
                self.all_gpus = []

        self.avail_cpus: Set[int] = set(self.all_cpus)
        self.avail_gpus: Set[int] = set(self.all_gpus)

    @property
    def cpus_avail(self) -> int:
        """Returns the number of currently free CPU cores."""
        with self._lock:
            return len(self.avail_cpus)

    @property
    def gpus_avail(self) -> int:
        """Returns the number of currently free GPU devices."""
        with self._lock:
            return len(self.avail_gpus)

    def acquire(self, req_cpus: int = 1, req_gpus: int = 0) -> Tuple[List[int], List[int]]:
        """
        Acquires requested number of CPU core IDs and GPU device IDs.
        Returns: (assigned_cpu_cores, assigned_gpu_ids)
        Raises ValueError if insufficient available resources.
        """
        with self._lock:
            req_cpus = max(1, req_cpus)
            req_gpus = max(0, req_gpus)

            if len(self.avail_cpus) < req_cpus:
                raise ValueError(f"Insufficient CPUs available: requested {req_cpus}, available {len(self.avail_cpus)}")
            if req_gpus > 0 and len(self.avail_gpus) < req_gpus:
                raise ValueError(f"Insufficient GPUs available: requested {req_gpus}, available {len(self.avail_gpus)}")

            assigned_cpus = sorted(list(self.avail_cpus))[:req_cpus]
            for c in assigned_cpus:
                self.avail_cpus.remove(c)

            assigned_gpus = []
            if req_gpus > 0:
                assigned_gpus = sorted(list(self.avail_gpus))[:req_gpus]
                for g in assigned_gpus:
                    self.avail_gpus.remove(g)

            return assigned_cpus, assigned_gpus

    def release(self, cpu_cores: List[int], gpu_ids: List[int]) -> None:
        """
        Releases CPU core IDs and GPU device IDs back into the pool.
        """
        with self._lock:
            for c in cpu_cores:
                if c in self.all_cpus:
                    self.avail_cpus.add(c)
            for g in gpu_ids:
                if g in self.all_gpus:
                    self.avail_gpus.add(g)
