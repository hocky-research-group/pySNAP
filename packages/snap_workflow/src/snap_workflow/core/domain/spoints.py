import os
import sys
import signal
import itertools
import shutil
import json
import subprocess
import time

from snap_workflow.utils.constants import *
from snap_workflow.utils import path, io
from snap_workflow.core.domain import status
from snap_workflow.core.domain import stages as stage_tools
from snap_workflow.core.domain import sweeps as sweep_tools
from snap_workflow.core.params import params
from snap_workflow.utils.time import load_time, write_time
from snap_workflow.utils.io import parse_memory_to_gb
from snap_workflow.utils.logging import logger

def get_spoint_string(spoint_dict):
    if len(spoint_dict) == 0:
        return "."
    var = spoint_dict.keys()
    val = spoint_dict.values()
    spoint = sorted(zip(list(var), list(val)))
    name = ''
    for spoint_var, spoint_val in spoint:
        name += spoint_var + '_' + str(spoint_val) + '_'
    return name[:-1]

def get_spoint_path(stage_name, spoint_dict):
    root = path.get_root()
    spoint_string = get_spoint_string(spoint_dict)
    return os.path.join(root, stage_name, SPOINTS, spoint_string)

def parse_spoint_string(spoint_string):
    if spoint_string == ".":
        return dict()
    split_str = spoint_string.split('_')
    spoint_dict = {}
    for i in range(int(len(split_str)/2)):
        j = 2*i
        key = split_str[j]
        val = split_str[j+1]
        spoint_dict[key] = val
    return spoint_dict

def iter_spoints(sweep_names=None, stage_names=None):
    sweeps = sweep_tools.load_sweeps()
    stages = stage_tools.load_stages()

    if sweep_names is None or sweep_names == "all":
        sweep_names = list(sweeps.keys())
    elif not isinstance(sweep_names, list):
        sweep_names = [sweep_names]

    if stage_names is None or stage_names == "all":
        stage_names = list(stages.keys())
    elif not isinstance(stage_names, list):
        stage_names = [stage_names]

    for sweep_name in sweep_names:
        sweep = sweeps[sweep_name]
        for stage_name in stage_names:
            if stage_name not in sweep["stages"]:
                continue
            stage = stages[stage_name]

            spoint_vars = stage["variables"]
            spoint_vals = [sweep["values"][var] for var in spoint_vars]
            spoint_combinations = list(itertools.product(*spoint_vals))

            for spoint in spoint_combinations:
                spoint_dict = create_spoint_dict(spoint_vars, spoint)
                yield sweep_name, stage_name, spoint_dict
    return

def create_spoint(stage_name, spoint_dict, clear):
    spoint_path = get_spoint_path(stage_name, spoint_dict)
    os.makedirs(spoint_path, exist_ok=True)
    if clear:
        path.clear_directory(spoint_path)

    # Make/Initialize SPOINT_INFO
    os.makedirs(os.path.join(spoint_path, SPOINT_INFO), exist_ok=True)
    write_spoint(spoint_dict, spoint_path)
    if not os.path.isfile(os.path.join(spoint_path, SPOINT_INFO, STATUS)):
        status.write_status(INITIALIZED, spoint_path)
    if not os.path.isfile(os.path.join(spoint_path, SPOINT_INFO, PROGRESS)):
        status.write_progress(NONE, spoint_path)

    return True

def create_spoint_dict(spoint_vars, spoint):
    if spoint is None:
        return dict()
    else:
        return {spoint_var: spoint_val for spoint_var, spoint_val in zip(spoint_vars, spoint)}

def write_spoint(spoint_dict, spoint_dir="."):
    spoint_string = get_spoint_string(spoint_dict)
    with open(os.path.join(spoint_dir, SPOINT_INFO, SPOINT_VARS), 'w') as file:
        file.write(spoint_string)

def load_spoint(spoint_dir="."):
    with open(os.path.join(spoint_dir, SPOINT_INFO, SPOINT_VARS), 'r') as file:
        spoint_string = file.readline()
    return parse_spoint_string(spoint_string)

def reset_spoint(spoint_dir=".", hard=False):
    var_file = os.path.join(spoint_dir, SPOINT_INFO, SPOINT_VARS)
    abs_path = os.path.abspath(spoint_dir)
    if not os.path.isfile(var_file):
        raise ValueError(f"Error: Current working directory '{abs_path}' is not an SPoint directory.")

    spoint_dict = load_spoint(spoint_dir)
    root = path.get_root(spoint_dir)
    abs_root = os.path.abspath(root)
    rel_path = os.path.relpath(abs_path, abs_root)
    parts = os.path.normpath(rel_path).split(os.sep)

    if len(parts) < 3 or parts[1] != SPOINTS:
        raise ValueError(f"Error: Current working directory '{abs_path}' is not an SPoint directory.")
    stage_name = parts[0]

    info_dir = os.path.join(spoint_dir, SPOINT_INFO)
    if hard:
        path.clear_directory(spoint_dir)

    os.makedirs(info_dir, exist_ok=True)
    write_spoint(spoint_dict, spoint_dir)
    status.write_status(INITIALIZED, spoint_dir)
    status.write_progress(NONE, spoint_dir)
    write_time([], spoint_dir)

    params.set_spoint_params(None, stage_name, spoint_dict)
    relink_spoint_dependencies(stage_name, spoint_dict)

def relink_spoint_dependencies(stage_name, spoint_dict):
    sweeps = sweep_tools.load_sweeps()
    for sweep_name, sweep in sweeps.items():
        if stage_name not in sweep["stages"]:
            continue
        sweep_values = sweep["values"]
        match = True
        for var, val in spoint_dict.items():
            if var not in sweep_values:
                match = False
                break
            str_vals = [str(v) for v in sweep_values[var]]
            if str(val) not in str_vals:
                match = False
                break
        if match:
            dep_info = get_dependent_spoint_info(stage_name, sweep_name, spoint_dict)
            link_dependent_spoint(stage_name, spoint_dict, dep_info)

def spoint_still_defined(sname, stage_name, spoint_dict):
    sweeps = sweep_tools.load_sweeps()
    for sweep_name, sweep in sweeps.items():
        if sname == sweep_name:
            continue
        if stage_name not in sweep["stages"]:
            continue
        sweep_values = sweep["values"]
        not_found = False
        for var, val in spoint_dict.items():
            if val not in sweep_values[var]:
                not_found = True
                break
        if not_found:
            continue
        return True
    return False

def check_submittable(sweep_name, stage_name, spoint_dict):
    dont_submit = [RUNNING, SUBMITTED, COMPLETE, ERROR]

    spoint_path = get_spoint_path(stage_name, spoint_dict)
    spoint_status = status.load_status(spoint_path)
    if spoint_status in dont_submit:
        return False

    dep_stages = get_dependent_spoint_info(stage_name, sweep_name, spoint_dict)
    for dep_name, dep_stage in dep_stages.items():
        dep_path = os.path.join(spoint_path, dep_name)
        if len(dep_stage["conv_vars"]) == 0:
            if status.load_status(dep_path) != COMPLETE:
                return False
        else:
            conv_vars = dep_stage["conv_vars"]
            for conv_spoint in dep_stage["conv_spoints"]:
                conv_dict = {var: val for var, val in zip(conv_vars, conv_spoint)}
                conv_path = os.path.join(dep_path, get_spoint_string(conv_dict))
                if status.load_status(conv_path) != COMPLETE:
                    return False
    return True


def get_dependent_spoint_info(stage_name, sweep_name, spoint_dict):
    stages = stage_tools.load_stages()
    stage = stages[stage_name]

    sweeps = sweep_tools.load_sweeps()
    sweep_values = sweeps[sweep_name]["values"]

    spoint_vars = list(spoint_dict.keys())

    dep_stages = stage["dependent_stages"]
    all_dep_info = {}
    for dep_stage in dep_stages:
        dep_vars = stages[dep_stage]["variables"]
        dep_info = {}

        prop_vars = list(set(dep_vars) & set(spoint_vars))
        dep_info["prop_vars"] = prop_vars

        conv_vars = list(set(dep_vars) - set(spoint_vars))
        dep_info["conv_vars"] = conv_vars
        conv_vals = [sweep_values[var] for var in conv_vars]
        conv_spoints = list(itertools.product(*conv_vals))
        dep_info["conv_spoints"] = conv_spoints

        all_dep_info[dep_stage] = dep_info
    return all_dep_info

def link_dependent_spoint(stage_name, spoint_dict, dep_info):
    spoint_path = path.from_root(get_spoint_path(stage_name, spoint_dict))
    for dep_stage, info in dep_info.items():
        prop_vars = info["prop_vars"]
        conv_vars = info["conv_vars"]
        dep_dict = {var: spoint_dict[var] for var in prop_vars}

        dep_dir = os.path.join(spoint_path, dep_stage)
        if len(conv_vars) == 0:
            dep_link = dep_dir
            dep_target = path.from_root(get_spoint_path(dep_stage, dep_dict))
            path.make_sym(dep_target, dep_link, overwrite=True)
        else:
            new_dep_stage_dir = dep_dir
            if os.path.isdir(new_dep_stage_dir):
                shutil.rmtree(new_dep_stage_dir)
            os.makedirs(new_dep_stage_dir, exist_ok=True)

            for conv in info["conv_spoints"]:
                conv_dict = {var: val for var, val in zip(conv_vars, conv)}
                conv_link = os.path.join(new_dep_stage_dir, get_spoint_string(conv_dict))
                conv_dict = {**conv_dict, **dep_dict}
                dep_target = path.from_root(get_spoint_path(dep_stage, conv_dict))
                path.make_sym(dep_target, conv_link, overwrite=True)

class SPointManager():
    def __init__(self, save_func=None, stop_func=None, report_to=None):
        self.main_dir = os.getcwd()
        self.save_func = save_func or stop_func
        if report_to is None:
            report_to = os.environ.get("REPORT_TO")
            if not report_to:
                for i, arg in enumerate(sys.argv):
                    if arg == "--report-to" and i + 1 < len(sys.argv):
                        report_to = sys.argv[i + 1]
                        break
        self.report_to = report_to
        return

    @property
    def stop_func(self):
        return self.save_func

    @stop_func.setter
    def stop_func(self, value):
        self.save_func = value

    def __enter__(self):
        os.makedirs(os.path.join(self.main_dir, SPOINT_INFO), exist_ok=True)
        if not os.path.isfile(os.path.join(self.main_dir, SPOINT_INFO, TIME)):
            write_time([], self.main_dir)
        if not os.path.isfile(os.path.join(self.main_dir, SPOINT_INFO, STATUS)):
            status.write_status(INITIALIZED, self.main_dir)
        if not os.path.isfile(os.path.join(self.main_dir, SPOINT_INFO, PROGRESS)):
            status.write_progress("None", self.main_dir)

        self.time = load_time(self.main_dir)
        self.starting_status = status.load_status(self.main_dir)
        self.progress = status.load_progress(self.main_dir)
        self._set_running()
        self.start_time = time.time()
        signal.signal(signal.SIGINT, signal.default_int_handler)
        try:
            signal.signal(signal.SIGTERM, signal.default_int_handler)
        except Exception:
            pass
        return self

    def __exit__(self, exc_type, exc_val, traceback):
        self.time.append(time.time()-self.start_time)
        write_time(self.time, self.main_dir)
        final_status = COMPLETE
        exit_code = 0
        if exc_type is None:
            self._set_complete()
            final_status = COMPLETE
            exit_code = 0
        elif exc_type == KeyboardInterrupt:
            self._set_incomplete()
            self._run_stop_func()
            final_status = INCOMPLETE
            exit_code = 1
        else:
            self._set_error()
            self._run_stop_func()
            final_status = ERROR
            exit_code = 2

        if self.report_to and isinstance(self.report_to, str) and (self.report_to.startswith("http://") or self.report_to.startswith("https://")):
            self._notify_server(final_status, exit_code)

    def _notify_server(self, final_status, exit_code):
        try:
            import urllib.request, json
            url = f"{self.report_to.rstrip('/')}/update_status"
            payload = json.dumps({
                "spoint_path": self.main_dir,
                "status": final_status,
                "exit_code": exit_code
            }).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            token = os.environ.get("SERVER_TOKEN")
            if token:
                headers["Authorization"] = f"Bearer {token}"
            req = urllib.request.Request(url, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as response:
                pass
        except Exception as e:
            print(f"Warning: Failed to report status to server '{self.report_to}': {e}")

    def _run_stop_func(self):
        if self.save_func is None:
            return
        try:
            self.save_func()
        except Exception as e:
            print()
            print("Exception caught while running the user-defined save_func:")
            print(e)
            self._set_error()
        return

    def _set_complete(self):
        status.write_status(COMPLETE, self.main_dir)
        return

    def _set_incomplete(self):
        status.write_status(INCOMPLETE, self.main_dir)
        return

    def _set_error(self):
        status.write_status(ERROR, self.main_dir)
        return

    def _set_running(self):
        status.write_status(RUNNING, self.main_dir)
        return

    def set_save_func(self, save_func):
        self.save_func = save_func
        return

    def set_stop_func(self, stop_func):
        self.set_save_func(stop_func)
        return

    def set_progress(self, progress):
        status.write_progress(progress, self.main_dir)
        self.progress = progress
        return

    def check_progress(self, progress):
        if progress is None:
            progress = "None"
        return progress == self.progress

    def load_params(self):
        return params.load_params(self.main_dir)

    def _track_nvidia(self):
        raise NotImplementedError

# Backward compatibility aliases
SPoint_Manager = SPointManager
