import os
import time
import itertools
import logging
from typing import Dict, Any, List, Optional, Tuple

from snap_workflow.utils import path, io
from snap_workflow.utils.constants import PARAMS
from snap_workflow.utils.io import parse_memory_to_gb
from snap_workflow.core.domain import stages as stage_tools, sweeps as sweep_tools, status
from snap_workflow.core.domain.spoints import iter_spoints, get_spoint_path, create_spoint, create_spoint_dict
from snap_workflow.core.params import params as params_tools

logger = logging.getLogger("snap_workflow.server.scheduler")


class SPointScheduler:
    """Server-side scheduler managing candidate selection, resource allocation, and status tracking for SPoints."""

    def __init__(self, default_lease_ttl: float = 60.0):
        self.default_lease_ttl = default_lease_ttl
        self.active_leases: Dict[str, Dict[str, Any]] = {}

    def reclaim_expired_leases(self) -> int:
        """Reclaims any active task leases that have passed their lease_expires_at TTL."""
        now = time.time()
        expired_paths = [
            sp_path for sp_path, lease in self.active_leases.items()
            if lease.get("lease_expires_at", 0) < now
        ]
        for sp_path in expired_paths:
            lease = self.active_leases.pop(sp_path, None)
            if lease:
                logger.warning(
                    "[SCHEDULER] Task lease expired for %s (worker: %s, host: %s). Reclaiming task back to 'initialized'.",
                    sp_path, lease.get("worker_id"), lease.get("host")
                )
                try:
                    status.write_status("initialized", sp_path)
                except Exception as e:
                    logger.debug("Failed to reset status to initialized for %s: %s", sp_path, e)
        return len(expired_paths)

    @property
    def stages_dict(self) -> Dict[str, Any]:
        return stage_tools.load_stages()

    def get_spoints(self, sweep_name: str, stage_name: str) -> List[Dict[str, Any]]:
        self.reclaim_expired_leases()
        result = []
        for s_name, st_name, sp_dict in iter_spoints(sweep_names=[sweep_name], stage_names=[stage_name]):
            sp_path = get_spoint_path(st_name, sp_dict)
            stat_val = "initialized"
            if os.path.exists(sp_path):
                stat_val = status.load_status(sp_path)
            result.append({
                "variables": sp_dict,
                "status": stat_val,
                "path": sp_path
            })
        return result

    def get_spoint(self, sweep_name: str, stage_name: str, spoint_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        stage = self.stages_dict.get(stage_name, {})
        stage_vars = stage.get("variables")
        if stage_vars is not None:
            filtered_dict = {k: v for k, v in spoint_dict.items() if k in stage_vars}
        else:
            filtered_dict = spoint_dict
        sp_path = get_spoint_path(stage_name, filtered_dict)
        if not os.path.exists(sp_path):
            return None
        stat_val = status.load_status(sp_path)
        return {
            "variables": filtered_dict,
            "status": stat_val,
            "path": sp_path
        }

    def record_start(
        self,
        spoint_path: str,
        worker_id: Optional[str] = None,
        pid: Optional[Any] = None,
        host: str = "local",
        ttl: Optional[float] = None
    ) -> bool:
        """Records task execution start and sets active status to 'running'."""
        ttl_val = ttl if ttl is not None else self.default_lease_ttl
        now = time.time()
        norm_path = os.path.abspath(spoint_path)

        # Match either exact path or basename
        target_key = None
        for key in list(self.active_leases.keys()):
            if os.path.abspath(key) == norm_path or key == spoint_path:
                target_key = key
                break

        if target_key:
            self.active_leases[target_key]["started_at"] = now
            self.active_leases[target_key]["pid"] = pid
            self.active_leases[target_key]["lease_expires_at"] = now + ttl_val
        else:
            self.active_leases[spoint_path] = {
                "started_at": now,
                "pid": pid,
                "worker_id": worker_id,
                "host": host,
                "lease_expires_at": now + ttl_val
            }

        try:
            status.write_status("running", spoint_path)
        except Exception as e:
            logger.debug("Failed to write 'running' status for %s: %s", spoint_path, e)
        return True

    def extend_heartbeat(
        self,
        spoint_paths: List[str],
        worker_id: Optional[str] = None,
        ttl: Optional[float] = None
    ) -> int:
        """Extends TTL lease expiration for actively running tasks."""
        ttl_val = ttl if ttl is not None else self.default_lease_ttl
        now = time.time()
        extended = 0

        for sp in spoint_paths:
            norm_sp = os.path.abspath(sp)
            for key in list(self.active_leases.keys()):
                if os.path.abspath(key) == norm_sp or key == sp:
                    self.active_leases[key]["lease_expires_at"] = now + ttl_val
                    extended += 1
                    break
        return extended

    def set_status(self, sweep_name: str, stage_name: str, spoint_dict: Dict[str, Any], status_val: str, host: str = "local") -> None:
        sp_path = get_spoint_path(stage_name, spoint_dict)
        if status_val in ("complete", "error", "incomplete", "initialized"):
            norm_p = os.path.abspath(sp_path)
            for k in list(self.active_leases.keys()):
                if os.path.abspath(k) == norm_p or k == sp_path:
                    self.active_leases.pop(k, None)

        create_spoint(stage_name, spoint_dict, clear=False)
        params_file = os.path.join(sp_path, PARAMS)
        if not os.path.isfile(params_file):
            try:
                params_tools.set_spoint_params(sweep_name, stage_name, spoint_dict)
            except Exception as e:
                logger.warning("Failed to generate params.pkl for %s: %s", sp_path, e)
        status.write_status(status_val, sp_path)

    def handle_worker_shutdown(
        self,
        worker_id: Optional[str] = None,
        host: str = "local",
        active_tasks: Optional[List[str]] = None
    ) -> List[str]:
        """Marks any in-flight active tasks associated with the shutting-down worker as 'incomplete'."""
        affected = []
        task_paths = set(active_tasks or [])

        # Find leases belonging to this worker
        for sp_path, lease_info in list(self.active_leases.items()):
            if (worker_id and lease_info.get("worker_id") == worker_id) or (sp_path in task_paths):
                task_paths.add(sp_path)

        for sp_path in task_paths:
            norm_sp = os.path.abspath(sp_path)
            for k in list(self.active_leases.keys()):
                if os.path.abspath(k) == norm_sp or k == sp_path:
                    self.active_leases.pop(k, None)

            try:
                cur_stat = status.load_status(sp_path)
                if cur_stat in ("running", "submitted", "queued"):
                    status.write_status("incomplete", sp_path)
                    affected.append(sp_path)
                    logger.info("[SCHEDULER] Worker '%s' shut down; marked task '%s' as incomplete.", worker_id, sp_path)
            except Exception as e:
                logger.debug("Failed to update status to incomplete for %s on worker shutdown: %s", sp_path, e)

        return affected

    def acquire_next_available(
        self,
        cpus_avail: int = 1,
        gpu_avail: int = 0,
        mem_avail: float = 0.0,
        min_cpu_running_gpu: int = 0,
        allowed_stages: Optional[List[str]] = None,
        allowed_sweeps: Optional[List[str]] = None,
        exclude_stages: Optional[List[str]] = None,
        exclude_sweeps: Optional[List[str]] = None,
        target_spoints: Optional[List[str]] = None,
        host: str = "local",
        worker_id: Optional[str] = None,
        lease_ttl: Optional[float] = None
    ) -> Optional[Tuple[str, str, Dict[str, Any], str]]:
        self.reclaim_expired_leases()
        sweeps = sweep_tools.load_sweeps()
        stages = stage_tools.load_stages()

        root_dir = path.get_root()
        def _get_stage_res(st_name):
            try:
                cfg = io.load_config(os.path.join(root_dir, st_name, "env"), full_path=True)
                return cfg.get("resources", {})
            except Exception:
                return {}

        target_set = set()
        if target_spoints:
            for tp in target_spoints:
                tp_norm = os.path.normpath(tp).rstrip("/")
                target_set.add(tp_norm)
                target_set.add(os.path.abspath(tp_norm))
                target_set.add(os.path.basename(tp_norm))

        def _search(filter_targets: bool):
            for sweep_name in sweeps.keys():
                if allowed_sweeps and sweep_name not in allowed_sweeps:
                    continue
                if exclude_sweeps and sweep_name in exclude_sweeps:
                    continue

                stage_names_list = sweeps[sweep_name]["stages"]
                if gpu_avail > 0:
                    stage_names_list = sorted(stage_names_list, key=lambda s: int(_get_stage_res(s).get("gpus", 0)), reverse=True)

                for stage_name in stage_names_list:
                    if allowed_stages and stage_name not in allowed_stages:
                        continue
                    if exclude_stages and stage_name in exclude_stages:
                        continue

                    stage = stages.get(stage_name)
                    if not stage:
                        continue

                    res = _get_stage_res(stage_name)
                    cpus_req = int(res.get("cpus", 1))
                    gpus_req = int(res.get("gpus", 0))
                    mem_str = res.get("mem", "0G")
                    mem_req = parse_memory_to_gb(mem_str) if isinstance(mem_str, str) else float(mem_str)

                    if cpus_req > cpus_avail:
                        continue
                    if gpu_avail != -1 and gpus_req > gpu_avail:
                        continue
                    if mem_req > mem_avail and mem_avail > 0:
                        continue

                    if gpus_req == 0 and gpu_avail > 0:
                        pending_gpu_cpus = [
                            int(_get_stage_res(st).get("cpus", 1))
                            for sw in sweeps.values()
                            for st in sw.get("stages", [])
                            if int(_get_stage_res(st).get("gpus", 0)) > 0
                        ]
                        if pending_gpu_cpus:
                            max_gpu_cpus = max(pending_gpu_cpus)
                            if (cpus_avail - cpus_req) + min_cpu_running_gpu < max_gpu_cpus:
                                continue

                    spoint_vars = stage.get("variables", [])
                    spoint_vals = [sweeps[sweep_name]["values"][v] for v in spoint_vars]
                    spoint_combinations = list(itertools.product(*spoint_vals))

                    for spoint_tuple in spoint_combinations:
                        spoint_dict = create_spoint_dict(spoint_vars, spoint_tuple)
                        sp_path = get_spoint_path(stage_name, spoint_dict)
                        sp_norm = os.path.normpath(sp_path).rstrip("/")
                        sp_rel = os.path.relpath(sp_path, root_dir) if root_dir else sp_path

                        if filter_targets and target_set:
                            is_target = (
                                sp_norm in target_set
                                or os.path.abspath(sp_norm) in target_set
                                or sp_rel in target_set
                                or os.path.basename(sp_norm) in target_set
                            )
                            if not is_target:
                                continue

                        if not os.path.exists(sp_path):
                            curr_status = "initialized"
                        else:
                            curr_status = status.load_status(sp_path)

                        if curr_status in ("queued", "submitted", "running", "complete", "error"):
                            continue

                        deps = stage.get("dependencies") if "dependencies" in stage else stage.get("dependent_stages", [])
                        deps_satisfied = True
                        for dep_stage in deps:
                            dep_spoint = self.get_spoint(sweep_name, dep_stage, spoint_dict)
                            if not dep_spoint or dep_spoint["status"] != "complete":
                                deps_satisfied = False
                                break

                        if deps_satisfied:
                            ttl_val = lease_ttl if lease_ttl is not None else self.default_lease_ttl
                            self.active_leases[sp_path] = {
                                "lease_expires_at": time.time() + ttl_val,
                                "worker_id": worker_id,
                                "host": host,
                                "stage": stage_name,
                                "sweep": sweep_name,
                                "spoint_dict": spoint_dict,
                                "started_at": None,
                                "pid": None
                            }
                            self.set_status(sweep_name, stage_name, spoint_dict, "submitted", host=host)
                            vars_str = ", ".join(f"{k}={v}" for k, v in spoint_dict.items()) if isinstance(spoint_dict, dict) else str(spoint_dict)
                            logger.info("[SCHEDULER] Assignment | Dispatcher : %s | Stage : %s | Spoint : %s", host, stage_name, vars_str)
                            return (sweep_name, stage_name, spoint_dict, sp_path)
            return None

        if target_set:
            candidate = _search(filter_targets=True)
            if candidate:
                return candidate
        return _search(filter_targets=False)

    def are_all_complete(
        self,
        allowed_stages: Optional[List[str]] = None,
        allowed_sweeps: Optional[List[str]] = None,
        exclude_stages: Optional[List[str]] = None,
        exclude_sweeps: Optional[List[str]] = None
    ) -> bool:
        sweeps = sweep_tools.load_sweeps()
        stages = stage_tools.load_stages()

        for sweep_name in sweeps.keys():
            if allowed_sweeps and sweep_name not in allowed_sweeps:
                continue
            if exclude_sweeps and sweep_name in exclude_sweeps:
                continue

            for stage_name in sweeps[sweep_name]["stages"]:
                if allowed_stages and stage_name not in allowed_stages:
                    continue
                if exclude_stages and stage_name in exclude_stages:
                    continue

                stage = stages.get(stage_name)
                if not stage:
                    continue

                spoint_vars = stage.get("variables", [])
                spoint_vals = [sweeps[sweep_name]["values"][v] for v in spoint_vars]
                spoint_combinations = list(itertools.product(*spoint_vals))

                for spoint_tuple in spoint_combinations:
                    spoint_dict = create_spoint_dict(spoint_vars, spoint_tuple)
                    sp_path = get_spoint_path(stage_name, spoint_dict)
                    if not os.path.exists(sp_path):
                        return False
                    curr_status = status.load_status(sp_path)
                    if curr_status not in ("complete", "error"):
                        return False

        return True
