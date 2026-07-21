import os, sys
import numpy as np
import json
from .tools import decode
class System_Params:# {{{
    def __init__(self,param_path,stages = None,variables = None):# {{{
        if os.path.isfile(param_path):
            self._load_pickle(param_path)
            return
        elif os.path.isdir(param_path):
            self._load_directory(param_path,stages,variables)
            return
        else:
            raise Exception(f"{param_path} is neither a file nor directory")# }}}
    def _load_pickle(self,param_path):# {{{
        import pickle
        if param_path.split(".")[-1] != "pkl":
            param_path = param_path + ".pkl"
        with open(param_path,"rb") as file:
            for key,val in pickle.load(file).__dict__.items():
                setattr(self,key,val)
        self.param_path = param_path
        return# }}}
    def _load_directory(self,param_path,stages,variables):# {{{
        self.param_path = param_path
        self.params = self._build(param_path)

        if stages is not None:
            self.set_stages(stages)

        if variables is not None:
            self.update_variables(variables)
        self.parse_variables()

        return# }}}
    def __getitem__(self, key):# {{{
        if not isinstance(key,tuple):
            return self.params[key]
        current_item = self.params
        for k in key:
            current_item = current_item[k]
        return current_item# }}}
    def __setitem__(self,key,value):# {{{
        if not isinstance(key,tuple):
            self.params[key] = value
            return
        current_item = self.params
        for k in key[:-1]:
            current_item = current_item[k]
        current_item[key[-1]] = value# }}}
    def __contains__(self,item):# {{{
        return item in self.params# }}}
    def _build(self,param_path):# {{{
        params = dict()
        for f in os.listdir(param_path):
            ext = f.split(".")[-1].lower()
            if ext == "json":
                with open(param_path+"/"+f) as file:
                    try:
                        params[f.split(".")[0]] = json.load(file)
                    except Exception as e:
                        raise Exception(f"Failed parsing {f}: {e.args[-1]}")
            elif ext in ["yaml", "yml"]:
                try:
                    import yaml
                except ImportError:
                    raise ImportError("The 'pyyaml' package is required to read YAML parameter files. Please install it using 'pip install pyyaml'.")
                with open(param_path+"/"+f) as file:
                    try:
                        params[f.split(".")[0]] = yaml.safe_load(file)
                    except Exception as e:
                        raise Exception(f"Failed parsing {f}: {e.args[-1]}")
            elif os.path.isdir(param_path+"/"+f):
                params[f] = self._build(param_path+"/"+f)
        return params# }}}
    def parse_variables(self):# {{{
        if "variables" in self.params:
            self.variables = self.params.pop("variables")
        else:
            self.variables = dict()
        self._find_directives(self.params)
        self.params["variables"] = self.variables# }}}
    def _find_directives(self,items):# {{{
        if isinstance(items,dict):
            keyvals = items.items()
        elif isinstance(items,list):
            keyvals = enumerate(items)
        else:
            estr="Unexpected collection of items: type {type(items)}"
            raise Exception(estr)

        for key,val in keyvals:
            if isinstance(val,str):
                if len(val) == 0:
                    continue
                parts = val.split("_")
                if len(parts) == 0 or len(parts[0]) == 0:
                    continue
                if parts[0][0] == "!":
                    new_val = self._parse_directives(list(parts[0]),
                                               str().join(parts[1:]))
                    items[key] = new_val
            elif np.iterable(val):
                self._find_directives(val)# }}}
    def set_directives(self):# {{{
        self.variables = self.params.pop("variables")
        self._find_directives(self.params)
        self.params["variables"] = self.variables# }}}
    def _parse_directives(self,dirs,value):# {{{
        if "m" in dirs and len(dirs) != 2:
            raise Exception("Conflicting directives: math must be the only directive")
        if "m" in dirs:
            from .parse_math import parse_math
            value = parse_math(value,self.variables)
            dirs.remove("m")
        if "v" in dirs:
            if value not in self.variables:
                return '!' + ''.join(dirs) + "_" + value
            value = self.variables[value]
            dirs.remove('v')
        if "f" in dirs and "i" in dirs:
            raise Exception("Conflicting directives: float and int")
        if "f" in dirs:
            value = float(value)
            dirs.remove('f')
        if "i" in dirs:
            value = int(float(value))
            dirs.remove('i')
        if "n" in dirs:
            value = -value
        dirs.remove("!")
        return value# }}}
    def set_stages(self,stage_names):# {{{
        if not isinstance(stage_names,list):
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
        return self# }}}
    def get_run_dict(self,var_names):# {{{
        run_dict = dict()
        key = "run" if "run" in self.params else "job"
        for var_name in var_names:
            var_path = self[key,var_name,"var_path"]
            var_value = self[tuple(var_path)]
            run_dict[var_name] = var_value
        return run_dict# }}}
    def decode_run_dict(self,run_dict):# {{{
        key = "run" if "run" in self.params else "job"
        for var_name,var_val in run_dict.items():
            var_info = self[key,var_name]
            var_dval = decode(var_val,var_info['encode'])
            run_dict[var_name] = var_dval
        return run_dict# }}}
    get_job_dict = get_run_dict
    decode_job_dict = decode_run_dict
    def update_variables(self,new_variables):# {{{
        if "variables" not in self.params:
            self.params["variables"] = new_variables
        self.params["variables"].update(new_variables)
    # }}}
    def update(self):# {{{
        if "update" not in self:
            return

        updates = self["update"]
        if isinstance(updates,dict):
            updates = list(updates.values())

        for update_info in updates:
            value = update_info["update_value"]
            encode = update_info["encode"]
            update_path = update_info["update_path"]

            dval = decode(value,encode)
            self[tuple(update_path)] = dval

        return
            # }}}
    def pickle(self,path):# {{{
        import pickle
        if path.split(".")[-1] != "pkl":
            path = path + ".pkl"
        with open(path, 'wb') as file:
            pickle.dump(self,file,protocol=pickle.HIGHEST_PROTOCOL)# }}}
#}}}
