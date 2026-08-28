import os
import itertools
import logging
from typing import Dict, Any, List, Optional, Tuple

from snap_workflow.utils import path, io
from snap_workflow.utils.constants import PARAMS
from snap_workflow.utils.io import parse_memory_to_gb
from snap_workflow.core.domain import stages as stage_tools, sweeps as sweep_tools, status
from snap_workflow.core.domain.spoints import iter_spoints, get_spoint_path, create_spoint, create_spoint_dict

logger = logging.getLogger("snap_workflow.server.scheduler")


class SPointScheduler:
    """Server-side scheduler managing candidate selection, resource allocation, and status tracking for SPoints."""

    def __init__(self):
        pass

    @property
    def stages_dict(self) -> Dict[str, Any]:
        return stage_tools.load_stages()

    def get_spoints(self, sweep_name: str, stage_name: str) -> List[Dict[str, Any]]:
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

    def set_status(self, sweep_name: str, stage_name: str, spoint_dict: Dict[str, Any], status_val: str, host: str = "local") -> None:
        sp_path = get_spoint_path(stage_name, spoint_dict)
        create_spoint(stage_name, spoint_dict, clear=False)
        params_file = os.path.join(sp_path, PARAMS)
        if not os.path.isfile(params_file):
            try:
                from snap_workflow.core.params import params as params_tools
                params_tools.set_spoint_params(sweep_name, stage_name, spoint_dict)
            except Exception as e:
                logger.warning("Failed to generate params.pkl for %s: %s", sp_path, e)
        status.write_status(status_val, sp_path)

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
        host: str = "local"
    ) -> Optional[Tuple[str, str, Dict[str, Any], str]]:
        sweeps = sweep_tools.load_sweeps()
        stages = stage_tools.load_stages()

        root_dir = path.get_root()
        def _get_stage_res(st_name):
            try:
                cfg = io.load_config(os.path.join(root_dir, st_name, "env"), full_path=True)
                return cfg.get("resources", {})
            except Exception:
                return {}

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
                        self.set_status(sweep_name, stage_name, spoint_dict, "submitted", host=host)
                        vars_str = ", ".join(f"{k}={v}" for k, v in spoint_dict.items()) if isinstance(spoint_dict, dict) else str(spoint_dict)
                        logger.info("[SCHEDULER] Assignment | Dispatcher : %s | Stage : %s | Spoint : %s", host, stage_name, vars_str)
                        return (sweep_name, stage_name, spoint_dict, sp_path)

        return None

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
