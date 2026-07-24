from .workflow import initialize, zip_workflow
from .data import collect_data, DataManager, Data_Manager
from .domain import (
    add_stage, print_stages, load_stages, validate_stage_resources,
    add_sweep, remove_sweep, reset_sweep, print_sweeps, load_sweeps,
    add_variable, get_variable_names,
    submit_spoints, SPointManager, SPoint_Manager, load_spoint,
    set_status, print_status
)
from .params import load_params
from snap_workflow.server import run_server_foreground
from snap_workflow.worker import worker_loop, launch_remote_workers
from snap_workflow.utils import (
    WorkflowError,
    StageNotFoundError,
    StageAlreadyExistsError,
    SweepNotFoundError,
    SweepAlreadyExistsError,
    VariableAlreadyExistsError,
    VariableNotFoundError,
    ConversionError,
    ServerNotRunningError
)

SPoint_Manager = SPoint_Manager
load_spoint = load_spoint
submit_spoints = submit_spoints

Combo_Manager = SPoint_Manager
load_combo = load_spoint
submit_combos = submit_spoints
Job_Manager = SPoint_Manager
load_job = load_spoint

__all__ = [
    "initialize", "zip_workflow", "collect_data", "Data_Manager",
    "add_stage", "print_stages", "load_stages", "validate_stage_resources",
    "add_sweep", "remove_sweep", "reset_sweep", "print_sweeps", "load_sweeps",
    "add_variable", "get_variable_names",
    "submit_spoints", "SPoint_Manager", "load_spoint",
    "set_status", "print_status",
    "load_params", "run_server_foreground", "worker_loop", "launch_remote_workers",
    "WorkflowError", "StageNotFoundError", "StageAlreadyExistsError",
    "SweepNotFoundError", "SweepAlreadyExistsError", "VariableAlreadyExistsError",
    "VariableNotFoundError", "ConversionError", "ServerNotRunningError"
]
