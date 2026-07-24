import os, sys, warnings
import numpy as np
import json
from snap_workflow.core.params.tools import decode


class SystemParams:  # {{{
    def __init__(self, param_path, stages=None, variables=None):  # {{{
        if isinstance(param_path, SystemParams):
            self.param_path = param_path.param_path
            self.params = param_path.params
            self.variables = getattr(param_path, "variables", {})
            if stages is not None:
                self.set_stages(stages)
            if variables is not None:
                self.update_variables(variables)
            return
        elif isinstance(param_path, (dict, list)):
            self.param_path = None
            self.params = param_path
            self.variables = variables if variables is not None else {}
            if stages is not None:
                self.set_stages(stages)
            return
        elif isinstance(param_path, str) and os.path.isfile(param_path):
            self._load_pickle(param_path)
            return
        elif isinstance(param_path, str) and os.path.isdir(param_path):
            self._load_directory(param_path, stages, variables)
            return
        else:
            raise Exception(f"{param_path} is neither a file nor directory")
            # }}}

    def _load_pickle(self, param_path):  # {{{
        import pickle

        if param_path.split(".")[-1] != "pkl":
            param_path = param_path + ".pkl"
        with open(param_path, "rb") as file:
            for key, val in pickle.load(file).__dict__.items():
                setattr(self, key, val)
        self.param_path = param_path

        stored_hash = getattr(self, "source_hash", None)
        if stored_hash is not None:
            try:
                from snap_workflow.utils import path
                spoint_dir = os.path.dirname(os.path.abspath(param_path))
                root_rel = path.get_root(spoint_dir)
                root_params_dir = os.path.abspath(os.path.join(spoint_dir, root_rel, "params"))
                if os.path.isdir(root_params_dir):
                    from snap_workflow.core.params import compute_params_hash
                    current_hash = compute_params_hash(root_params_dir)
                    if current_hash is not None and current_hash != stored_hash:
                        warnings.warn(
                            "Parameter source configuration in 'params/' has changed since this SPoint was initialized (source hash mismatch). Consider running 'workflow reset params' or 'workflow reset spoint'.",
                            UserWarning,
                            stacklevel=2,
                        )
            except Exception:
                pass
        return  # }}}

    def to_dict(self):  # {{{
        def convert(obj):
            if isinstance(obj, dict):
                return {str(k) if isinstance(k, tuple) else k: convert(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [convert(v) for v in obj]
            elif hasattr(obj, "item"):
                return obj.item()
            elif hasattr(obj, "tolist"):
                return obj.tolist()
            else:
                return obj

        res = {
            "params": convert(self.params),
            "variables": convert(self.variables),
        }
        source_hash = getattr(self, "source_hash", None)
        if source_hash:
            res["source_hash"] = source_hash
        return res  # }}}

    def export_readable(self, export_path, format="json"):  # {{{
        data = self.to_dict()
        format_lower = format.lower()
        if format_lower == "json":
            if not export_path.endswith(".json"):
                export_path = export_path + ".json"
            with open(export_path, "w") as f:
                json.dump(data, f, indent=4)
        elif format_lower in ["yaml", "yml"]:
            try:
                import yaml
            except ImportError:
                raise ImportError(
                    "The 'pyyaml' package is required to export YAML. Please install it using 'pip install pyyaml'."
                )
            if not (export_path.endswith(".yaml") or export_path.endswith(".yml")):
                export_path = export_path + ".yaml"
            with open(export_path, "w") as f:
                yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
        else:
            raise ValueError(f"Unsupported format '{format}'. Supported formats: 'json', 'yaml'.")
        return export_path  # }}}

    def _load_directory(self, param_path, stages, variables):  # {{{
        self.param_path = param_path
        self.params = self._build(param_path)

        if stages is not None:
            self.set_stages(stages)

        if variables is not None:
            self.update_variables(variables)
        self.parse_variables()

        return  # }}}

    def __getitem__(self, key):  # {{{
        if not isinstance(key, tuple):
            return self.params[key]
        current_item = self.params
        for k in key:
            current_item = current_item[k]
        return current_item  # }}}

    def __setitem__(self, key, value):  # {{{
        if isinstance(value, System_Params):
            value = value.params

        if not isinstance(key, tuple):
            self.params[key] = value
            return
        current_item = self.params
        for k in key[:-1]:
            current_item = current_item[k]
        current_item[key[-1]] = value  # }}}

    def pop(self, *args, **kwargs):  # {{{
        _NO_DEFAULT = object()
        default = kwargs.pop("default", _NO_DEFAULT)
        if kwargs:
            raise TypeError(f"pop() got unexpected keyword arguments: {list(kwargs.keys())}")

        if not args:
            raise TypeError("pop() expected at least 1 argument, got 0")

        if isinstance(args[0], (tuple, list)):
            keys = tuple(args[0])
            if len(args) == 2 and default is _NO_DEFAULT:
                default = args[1]
            elif len(args) > 2:
                raise TypeError("pop() expected at most 2 positional arguments when passing a tuple key")
        else:
            keys = args
            curr = self.params
            valid_path = True
            for k in keys[:-1]:
                if isinstance(curr, dict) and k in curr:
                    curr = curr[k]
                elif isinstance(curr, list) and isinstance(k, int) and 0 <= k < len(curr):
                    curr = curr[k]
                else:
                    valid_path = False
                    break

            if valid_path and ((isinstance(curr, dict) and keys[-1] in curr) or (isinstance(curr, list) and isinstance(keys[-1], int) and 0 <= keys[-1] < len(curr))):
                keys = args
            elif len(args) > 1 and default is _NO_DEFAULT:
                default = args[-1]
                keys = args[:-1]
                if len(keys) == 1 and isinstance(keys[0], (tuple, list)):
                    keys = tuple(keys[0])
            else:
                keys = args

        current_item = self.params
        for k in keys[:-1]:
            if isinstance(current_item, dict) and k in current_item:
                current_item = current_item[k]
            elif isinstance(current_item, list) and isinstance(k, int) and 0 <= k < len(current_item):
                current_item = current_item[k]
            else:
                if default is not _NO_DEFAULT:
                    return default
                raise KeyError(f"Key path {keys} not found in parameters")

        last_key = keys[-1]
        if isinstance(current_item, dict) and last_key in current_item:
            return current_item.pop(last_key)
        elif isinstance(current_item, list) and isinstance(last_key, int) and 0 <= last_key < len(current_item):
            return current_item.pop(last_key)
        else:
            if default is not _NO_DEFAULT:
                return default
            raise KeyError(f"Key or index '{last_key}' not found in parameters")
        # }}}

    def __contains__(self, item):  # {{{
        return item in self.params  # }}}

    def _build(self, param_path):  # {{{
        params = dict()
        for f in os.listdir(param_path):
            ext = f.split(".")[-1].lower()
            if ext == "json":
                with open(param_path + "/" + f) as file:
                    try:
                        params[f.split(".")[0]] = json.load(file)
                    except Exception as e:
                        raise Exception(f"Failed parsing {f}: {e.args[-1]}")
            elif ext in ["yaml", "yml"]:
                try:
                    import yaml
                except ImportError:
                    raise ImportError(
                        "The 'pyyaml' package is required to read YAML parameter files. Please install it using 'pip install pyyaml'."
                    )
                with open(param_path + "/" + f) as file:
                    try:
                        params[f.split(".")[0]] = yaml.safe_load(file)
                    except Exception as e:
                        raise Exception(f"Failed parsing {f}: {e.args[-1]}")
            elif os.path.isdir(param_path + "/" + f):
                params[f] = self._build(param_path + "/" + f)
        return params  # }}}

    def parse_variables(self):  # {{{
        if "variables" in self.params:
            self.variables = self.params.pop("variables")
        else:
            self.variables = dict()
        self._find_directives(self.params)
        self.params["variables"] = self.variables  # }}}

    def _find_directives(self, items):  # {{{
        if isinstance(items, dict):
            keyvals = items.items()
        elif isinstance(items, list):
            keyvals = enumerate(items)
        else:
            estr = f"Unexpected collection of items: type {type(items)}"
            raise Exception(estr)

        for key, val in keyvals:
            if isinstance(val, str):
                if len(val) == 0:
                    continue
                parts = val.split("_")
                if len(parts) == 0 or len(parts[0]) == 0:
                    continue
                if parts[0][0] == "!":
                    new_val = self._parse_directives(list(parts[0]), str().join(parts[1:]))
                    items[key] = new_val
            elif np.iterable(val):
                self._find_directives(val)  # }}}

    def set_directives(self):  # {{{
        self.variables = self.params.pop("variables")
        self._find_directives(self.params)
        self.params["variables"] = self.variables  # }}}

    def _parse_directives(self, dirs, value):  # {{{
        if "m" in dirs and len(dirs) != 2:
            raise Exception("Conflicting directives: math must be the only directive")
        if "m" in dirs:
            from snap_workflow.core.params.parse_math import parse_math

            value = parse_math(value, self.variables)
            dirs.remove("m")
        if "v" in dirs:
            if value not in self.variables:
                return "!" + "".join(dirs) + "_" + value
            value = self.variables[value]
            dirs.remove("v")
        if "f" in dirs and "i" in dirs:
            raise Exception("Conflicting directives: float and int")
        if "f" in dirs:
            value = float(value)
            dirs.remove("f")
        if "i" in dirs:
            value = int(float(value))
            dirs.remove("i")
        if "n" in dirs:
            value = -value
        dirs.remove("!")
        return value  # }}}

    def set_stages(self, stage_names):  # {{{
        warnings.warn(
            "System_Params.set_stages() is deprecated and will be removed in a future release. Please manipulate stage parameter dictionaries directly.",
            DeprecationWarning,
            stacklevel=2,
        )
        if not isinstance(stage_names, list):
            stage_names = [stage_names]
        for stage_name in stage_names:
            if stage_name not in self.params:
                continue
            stage_info = self.params[stage_name]
            for stage_key, stage_val in stage_info.items():
                if stage_key == stage_name:
                    continue
                elif stage_key in self.params:
                    self.params[stage_key].update(stage_val)
                else:
                    self.params[stage_key] = stage_val
        return self  # }}}

    def get_run_dict(self, var_names):  # {{{
        run_dict = dict()
        key = "run" if "run" in self.params else "job"
        for var_name in var_names:
            var_path = self[key, var_name, "var_path"]
            var_value = self[tuple(var_path)]
            run_dict[var_name] = var_value
        return run_dict  # }}}

    def decode_run_dict(self, run_dict):  # {{{
        key = "run" if "run" in self.params else "job"
        for var_name, var_val in run_dict.items():
            var_info = self[key, var_name]
            var_dval = decode(var_val, var_info["encode"])
            run_dict[var_name] = var_dval
        return run_dict  # }}}

    get_job_dict = get_run_dict
    decode_job_dict = decode_run_dict

    def update_variables(self, new_variables):  # {{{
        if "variables" not in self.params:
            self.params["variables"] = new_variables
        self.params["variables"].update(new_variables)
        # }}}

    def update(self):  # {{{
        if "update" not in self.params:
            return

        updates = self.params["update"]
        if isinstance(updates, dict):
            updates = list(updates.values())
        elif isinstance(updates, System_Params):
            updates = list(updates.params.values())

        for update_info in updates:
            if isinstance(update_info, System_Params):
                update_info = update_info.params
            value = update_info["update_value"]
            encode = update_info["encode"]
            update_path = update_info["update_path"]

            dval = decode(value, encode)
            self[tuple(update_path)] = dval

        return
        # }}}

    def pickle(self, path):  # {{{
        import pickle

        if path.split(".")[-1] != "pkl":
            path = path + ".pkl"
        with open(path, "wb") as file:
            pickle.dump(self, file, protocol=pickle.HIGHEST_PROTOCOL)  # }}}
# }}}

# Backward compatibility alias
System_Params = SystemParams

