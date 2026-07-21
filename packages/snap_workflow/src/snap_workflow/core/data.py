import numpy as np
import sys
import os
import pickle
import importlib.util

from . import spoints
from . import path
from . import io
from . import stages as stage_tools
from . import variables
from .time import load_time

def collect_data(stage_names=None, verbose=False):
    sys.dont_write_bytecode = True

    stages = stage_tools.load_stages()
    if stage_names is None or stage_names == "all":
        stage_names = list(stages.keys())
    elif not isinstance(stage_names, list):
        stage_names = [stage_names]

    with path.From_Root():
        for stage_name in stage_names:
            if stage_name not in stages:
                continue

            collect_file = os.path.join(stage_name, "collect.py")
            if not os.path.isfile(collect_file):
                continue

            # Load the stage's collect module in isolation
            spec = importlib.util.spec_from_file_location("collect", collect_file)
            if spec is None or spec.loader is None:
                continue
            collect_module = importlib.util.module_from_spec(spec)
            
            # Add stage path temporarily during module loading to support local imports
            orig_path = sys.path.copy()
            sys.path.insert(0, os.path.abspath(stage_name))
            try:
                spec.loader.exec_module(collect_module)

                if verbose:
                    print(f"Collecting {stage_name} data")
                collected = _collect_data(stage_name, collect_module, verbose)
                if not verbose and collected:
                    print(f"Collected {stage_name} data")
            finally:
                sys.path = orig_path

def _collect_data(stage_name, collect_module, verbose):
    data = Data_Manager()
    for sweep_name, sname, spoint_dict in spoints.iter_spoints(stage_names=stage_name):
        with path.From_Root():
            spoint_string = spoints.get_spoint_string(spoint_dict)
            spoint_path = spoints.get_spoint_path(stage_name, spoint_dict)

            if verbose:
                print(f"    {spoint_string}")

            spoint_dict = variables.cast_combo_dict(spoint_dict)
            spoint_dict["sweep"] = sweep_name

            with path.From_Dir(spoint_path):
                data_dict = None
                try:
                    data_dict = collect_module.collect()
                    data_dict["time"] = load_time(sum=True)
                except Exception as e:
                    if verbose:
                        print("    Failed to collect data")
                        print("    ", e)

                if data_dict is not None:
                    if verbose:
                        print("    Data collection successful")
                        print("    ", spoint_dict)
                    data._add(spoint_dict, data_dict)

    if len(data) == 0:
        return False
    with path.From_Root():
        data.pickle(os.path.join("data", stage_name))
    return True

class Data_Manager:
    def __init__(self, data_path=None):
        self.iter_count = None
        if data_path is not None:
            if data_path.split(".")[-1] != "dm":
                data_path = data_path + ".dm"
            try:
                root_path = path.get_root()
                candidate = os.path.join(root_path, "data", data_path)
                if not os.path.isfile(data_path) and os.path.isfile(candidate):
                    data_path = candidate
            except Exception:
                pass
            if not os.path.isfile(data_path):
                raise ValueError(f"data_path '{data_path}' is not a valid pickle file")
            with open(data_path, "rb") as file:
                loaded = pickle.load(file)
                for key, val in loaded.__dict__.items():
                    setattr(self, key, val)
            self.data_path = data_path 
        else:
            self.var_names = None
            self.var_vals = []
            self.data_names = None
            self.data_vals = []
            self.np_updated = False

    def _add(self, var_dict, data_dict):
        if self.var_names is None:
            self._add_var_data_names(var_dict, data_dict)

        self._verify_variables(var_dict)
        self._verify_data(data_dict)

        self._add_vars(var_dict)
        self._add_data(data_dict)
        self.np_updated = False

    def pickle(self, path):
        if path.split(".")[-1] != "dm":
            path = path + ".dm"
        with open(path, 'wb') as file:
            pickle.dump(self, file, protocol=pickle.HIGHEST_PROTOCOL)

    def save(self, path):
        self.pickle(path)
        return

    def unique(self, var_name):
        vals = self[var_name]
        return np.unique(vals)

    def split(self, var_name, enum=False):
        vals = self.unique(var_name)
        for i, val in enumerate(vals):
            dm = self == (var_name, val)
            if enum:
                yield i, val, dm
            else:
                yield val, dm

    def get_run(self, **kwargs):
        dm_f = self
        for var, val in kwargs.items():
            if var not in self.var_names:
                continue
            dm_f = dm_f[dm_f[var] == val]
        runs_list = [run for run in dm_f]
        if len(runs_list) == 1:
            return runs_list[0]
        return runs_list

    def get_runs(self, **kwargs):
        return self.get_run(**kwargs)

    get_job = get_run
    get_jobs = get_runs

    def _verify_variables(self, var_dict):
        var_mismatch_string = "Variable Mismatch: All data in a data manager " +\
                              "must be added with the same variables"
        new_vars = list(var_dict.keys())
        if self.var_names is None:
            self.var_names = new_vars
        if self.num_vars != len(new_vars):
            raise Exception(var_mismatch_string)
        for i in range(self.num_vars):
            if self.var_names[i] not in var_dict or new_vars[i] not in self.var_names:
                raise Exception(var_mismatch_string)
        return

    def _verify_data(self, data_dict):
        data_mismatch_string = "Data Mismatch: All data in a data manager " +\
                               "must be added with the same data"
        new_data = list(data_dict.keys())
        if self.data_names is None:
            self.data_names = new_data
        if self.num_data != len(new_data):
            raise Exception(data_mismatch_string)
        for i in range(self.num_data):
            if self.data_names[i] not in data_dict or new_data[i] not in self.data_names:
                raise Exception(data_mismatch_string)
        return

    def _add_var_data_names(self, var_dict, data_dict):
        var_dict = dict(sorted(var_dict.items()))
        var_names = list(var_dict.keys())
        self.var_names = var_names
        self.num_vars = len(var_names)

        data_dict = dict(sorted(data_dict.items()))
        data_names = list(data_dict.keys())
        self.data_names = data_names
        self.num_data = len(data_names)
        return

    def _add_vars(self, var_dict):
        var_dict = dict(sorted(var_dict.items()))
        var_vals = list(var_dict.values())
        self.var_vals.append(var_vals)
        return

    def _add_data(self, data_dict):
        data_dict = dict(sorted(data_dict.items()))
        data_vals = list(data_dict.values())
        self.data_vals.append(data_vals)
        return

    def _update_np(self):
        num_entries = len(self.var_vals)
        self.np_vars = np.empty((num_entries, self.num_vars), dtype=object)
        for i, val in enumerate(self.var_vals):
            self.np_vars[i] = val

        num_entries = len(self.data_vals)
        self.np_data = np.empty((num_entries, self.num_data), dtype=object)
        for i, j in enumerate(self.data_vals):
            self.np_data[i] = j 

        self.np_updated = True
        return

    def _get_var(self, name):
        if not self.np_updated:
            self._update_np()

        if name in self.var_names:
            idx = self.var_names.index(name)
            return self.np_vars[:, idx]
        elif name in self.data_names:
            idx = self.data_names.index(name)
            return self.np_data[:, idx]
        else:
            raise ValueError(f"'{name}' not a variable or data name in this Data_Manager")

    def _filter(self, conditions):
        if not self.np_updated:
            self._update_np()

        num_entries = len(self.var_vals)
        flag = np.ones(num_entries, dtype=bool)
        for condition in conditions:
            if len(condition) != num_entries:
                raise ValueError("Each condition in a filter must be a boolean array with the same length as the number of data points in the Data_Manager")
            flag = flag & condition
        int_flag = np.arange(num_entries, dtype=int)[flag]

        new_data_manager = Data_Manager()
        new_data_manager.var_names = self.var_names
        new_data_manager.num_vars = self.num_vars
        new_data_manager.var_vals = [self.var_vals[i] for i in int_flag]
        new_data_manager.np_vars = self.np_vars[flag]
        new_data_manager.data_names = self.data_names
        new_data_manager.num_data = self.num_data
        new_data_manager.data_vals = [self.data_vals[i] for i in int_flag]
        new_data_manager.np_data = self.np_data[flag]
        new_data_manager.np_updated = True
        return new_data_manager

    def __getitem__(self, args):
        if len(args) == 0:
            raise Exception("Cannot interpret nothing")
        if isinstance(args, str):
            return self._get_var(args)
        elif isinstance(args, np.ndarray):
            return self._filter((args,))
        return self._filter(args)

    def __iter__(self):
        return self

    def __next__(self):
        if self.iter_count is None:
            self.iter_count = 0
            self._update_np()
        if self.iter_count == len(self.var_vals):
            self.iter_count = None
            raise StopIteration
        i = self.iter_count
        self.iter_count += 1
        var_dict = {self.var_names[j]: self.np_vars[i, j] for j in range(self.num_vars)}
        data_dict = {self.data_names[j]: self.np_data[i, j] for j in range(self.num_data)}
        data_dict.update(var_dict)
        return data_dict

    def __len__(self):
        return len(self.var_vals)

    def _seperate_other(self, other):
        try:
            if len(other) != 2:
                raise Exception()
            var, val = other
            if not isinstance(var, str):
                raise Exception()
            return var, val
        except Exception:
            raise Exception("Data_Manager can only be compared to tuple (or list) values of length two containing a variable name and value")

    def _comparison_filter(self, other, op):
        if len(other) != 2:
            raise Exception("Data manager filters can only be applied via comparison when comparing with iterables of length 2 (egs. dm >= [variable,value])")
        var, val = other
        vals = self[var]
        if op == ">":
            flags = vals > val
        elif op == ">=":
            flags = vals >= val
        elif op == "<":
            flags = vals < val
        elif op == "<=":
            flags = vals <= val
        elif op == "==":
            flags = vals == val
        elif op == "!=":
            flags = vals != val
        return self[flags]

    def __gt__(self, other):
        return self._comparison_filter(other, ">")
    def __ge__(self, other):
        return self._comparison_filter(other, ">=")
    def __lt__(self, other):
        return self._comparison_filter(other, "<")
    def __le__(self, other):
        return self._comparison_filter(other, "<=")
    def __eq__(self, other):
        return self._comparison_filter(other, "==")
    def __ne__(self, other):
        return self._comparison_filter(other, "!=")

    __gte__ = __ge__
    __lte__ = __le__
    __neq__ = __ne__
