import os
import sys
import subprocess
import threading
import logging
from typing import List, Tuple, Set, Optional

logger = logging.getLogger(__name__)


def detect_system_resources():
    """Detects available CPU cores, GPUs, and system memory in GB."""
    cpus = os.cpu_count() or 1
    slurm_cpus = os.getenv("SLURM_CPUS_ON_NODE")
    if slurm_cpus is not None:
        try:
            cpus = int(slurm_cpus)
        except ValueError:
            pass
    gpus = 0
    try:
        cuda_vis_env = os.getenv("CUDA_VISIBLE_DEVICES")
        slurm_gpus_env = os.getenv("SLURM_GPUS_ON_NODE")
        if cuda_vis_env is not None:
            cuda_vis = str(cuda_vis_env).strip()
            if cuda_vis.lower() in ("none", "void", "-1"):
                gpus = -1
            elif cuda_vis:
                gpus = len([x for x in cuda_vis.split(",") if x.strip()])
        elif slurm_gpus_env is not None:
            try:
                gpus = int(slurm_gpus_env)
            except ValueError:
                gpus = 1
        else:
            try:
                res = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True)
                if res.returncode == 0:
                    lines = [line for line in res.stdout.strip().split("\n") if line.strip()]
                    gpus = len(lines)
            except Exception:
                gpus = 0

            if gpus == 0:
                try:
                    import torch
                    if torch.cuda.is_available():
                        gpus = torch.cuda.device_count()
                except Exception:
                    pass
    except Exception:
        gpus = 1

    mem_gb = 16.0
    try:
        if sys.platform != "win32":
            res = subprocess.run(["free", "-b"], capture_output=True, text=True)
            if res.returncode == 0:
                lines = res.stdout.strip().split("\n")
                if len(lines) > 1:
                    tokens = lines[1].split()
                    total_bytes = int(tokens[1])
                    mem_gb = total_bytes / (1024 ** 3)
    except Exception:
        pass

    return cpus, gpus, mem_gb


class ResourcePool:
    """
    Manages atomic checkout and checkin of GPU device IDs and CPU core IDs.
    
    GPU IDs: Subset of visible GPUs (parsed from CUDA_VISIBLE_DEVICES or detected via system).
    CPU Core IDs: Subset of allowed CPU cores (parsed from os.sched_getaffinity(0) or system cores).
    """

    def __init__(self, cpus_total: Optional[int] = None, gpus_total: Optional[int] = None):
        self._lock = threading.Lock()

        # Cores this process may actually run on. Under a batch scheduler the job's
        # cgroup exposes an arbitrary subset of the node's cores, and pinning to any
        # core outside it fails.
        if hasattr(os, "sched_getaffinity"):
            try:
                allowed = sorted(os.sched_getaffinity(0))
            except Exception:
                allowed = list(range(os.cpu_count() or 1))
        else:
            allowed = list(range(os.cpu_count() or 1))

        if cpus_total is not None and cpus_total > 0:
            self.all_cpus: List[int] = allowed[:cpus_total]
        else:
            self.all_cpus = allowed

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
