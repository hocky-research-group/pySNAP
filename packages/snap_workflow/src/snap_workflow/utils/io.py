import numpy as np
import os,sys
import json
from snap_workflow.utils.constants import GLOBAL_CONFIG_DIR

def extract(kwargs,allowable_keys):# {{{
    extracted = None
    extracted_key = None
    for name in allowable_keys:
        if name not in kwargs:
            continue
        if extracted is not None and kwargs[name] != extracted:
            raise Exception("Extracted multiple arguments for the same variable.\n"+\
                           f"Can only supply one of the following:\n{allowable_keys}")
        extracted_key = name
        extracted = kwargs.pop(name)
    return extracted_key,extracted
# }}}
class InputCollector:# {{{
    def __init__(self,prompt, #{{{
                        help_string=None,
                        is_list = False,
                        default = None,
                        valid_options=None,
                        exclusions=None,
                        used_exclusions=None,
                        char_exclusions=None,
                        add_checks=None,
                        add_errors=None,
                        conversions = None,
                        keys = None,
                        delimiters = None,
                        list_conversion = None,
                        ):
        
        self.set_prompt(prompt)
        self.set_help_string(help_string)
        self.set_is_list(is_list)
        self.set_default(default)
        self.set_valid_options(valid_options)
        self.set_exclusions(exclusions)
        self.set_used_exclusions(used_exclusions)
        self.set_char_exclusions(char_exclusions)
        self.set_add_checks(add_checks)
        self.set_add_errors(add_errors)
        self.set_conversions(conversions)
        self.set_list_conversion(list_conversion)
        self.set_keys(keys)
        self.set_delimiters(delimiters)
        # }}}
    #---- Setters ----{{{
    def set_default(self,default):
        self.default_inputs = ["None","none",""]
        self.default = default
        self.has_default = self.default is not None
    def set_prompt(self,prompt):
        self.prompt = prompt
    def set_help_string(self,help_string):
        self.help_string = help_string
    def set_is_list(self,is_list):
        self.is_list = is_list
    def set_valid_options(self,valid_options):
        self.valid_options = valid_options
    def set_exclusions(self,exclusions):
        self.exclusions = exclusions
    def set_used_exclusions(self,used_exclusions):
        self.used_exclusions = used_exclusions
    def set_char_exclusions(self,char_exclusions):
        self.char_exclusions = char_exclusions
    def set_add_checks(self,add_checks):
        self.add_checks = add_checks
    def set_add_errors(self,add_errors):
        self.add_errors = add_errors
    def set_conversions(self,conversions):
        self.conversions = conversions
    def set_list_conversion(self,list_conversion):
        self.list_conversion = list_conversion
    def set_keys(self,keys):
        self.keys = keys
    def set_delimiters(self,delimiters):
        if delimiters is None:
            self.delimiters = [","," "]
        else:
            self.delimiters = delimiters
    # }}}
    def convert(self,input):# {{{
        if self.conversions is None:
            return input
        if not isinstance(self.conversions,list):
            self.conversions = [self.conversions]
        for convert in self.conversions:
            input = convert(input)
        return input# }}}
    def is_valid(self,input):# {{{
        if input == "help":
            print(self.help_string)
            return None
        if input in self.default_inputs:
            if self.has_default:
                return self.default
            else:
                print(f"Invalid Input: '{input}'")
                print("Must supply a value")
                return None
        if self.valid_options is not None:
            if input not in self.valid_options:
                print(f"Invalid Input: {input} is not a valid option")
                print(f"Valid Options: {self.valid_options}")
                return None
        if self.used_exclusions is not None:
            if input in self.used_exclusions:
                print(f"Invalid Input: {input} is already in use.")
                print(f"Existing Inputs: {self.used_exclusions}")
                return None
        if self.exclusions is not None:
            if input in self.exclusions:
                print(f"Invalid Input: {input} is not allowed due to potential ambiguity.")
                print(f"Invalid Inputs: {self.exclusions}")
                return None
        if self.char_exclusions is not None:
            if np.any([char in input for char in self.char_exclusions]):
                print(f"Invalid Input: {input} has invalid characters")
                print(f"Invalid Characters: {self.char_exclusions}")
                return None
        if self.add_checks is not None:
            if not isinstance(self.add_checks,list):
                self.add_checks = [self.add_checks]
            if self.add_errors is None or not isinstance(self.add_errors,list):
                self.add_errors = [self.add_errors for i in self.add_checks]

            for check,err in zip(self.add_checks,self.add_errors):
                if not check(input):
                    print(f"Invalid Input: {input} does not pass check {check.__name__}")
                    if err is not None:
                        print(err)
                    return None
        return input
# }}}
    def collect(self):# {{{
        if not self.is_list:
            return self.collect_single()
        else:
            return self.collect_list()#}}}
    def collect_single(self):# {{{
        user_input = None
        while user_input is None:
            user_input = input(self.prompt)
            user_input = user_input.strip()
            user_input = self.is_valid(user_input)
        return self.convert(user_input)# }}}
    def collect_list(self):# {{{
        user_input = None
        while user_input is None:
            user_input = input(self.prompt)
            user_input = user_input.strip()
            user_input = self.check_list_input(user_input)
        return user_input
        #}}}

    def check_list_input(self,user_input,key = None):#{{{
        if user_input in self.default_inputs:
            return self.default

        user_input = self.split_input(user_input)
        converted_input = []
        has_none = False
        for user_in in user_input:
            user_in = self.is_valid(user_in)
            if user_in is None:
                has_none = True
                converted_input.append(user_in)
            else:
                converted_input.append(self.convert(user_in))

        user_input = converted_input
        if has_none and key is not None:
            raise Exception(f"{user_in} is an invalid argument for key {key}")
        elif has_none:
            print("List contains the above errors. Please input list again")
            print()
            user_input = None

        if self.list_conversion is not None:
            user_input = self.list_conversion(user_input)
        return user_input
        # }}}
    def parse_kwargs(self,kwargs):#{{{
        if not self.is_list:
            return self.parse_single(kwargs)
        else:
            return self.parse_list(kwargs)
        #}}}
    def parse_single(self,kwargs):# {{{
        key,user_input = extract(kwargs,self.keys)
        if user_input is None:
            return user_input
        user_input = self.is_valid(user_input)
        if user_input is not None:
            return self.convert(user_input)
        else:
            raise Exception(f"{user_input} is in invalid argument for key {key}")
    # }}}
    def parse_list(self,kwargs):# {{{
        key,user_input = extract(kwargs,self.keys)

        if user_input is None:
            return user_input
        if isinstance(user_input,list):
            user_input = ' '.join(user_input)

        user_input = self.check_list_input(user_input,key=key)
        return user_input
    # }}}
    def split_input(self,input):# {{{
        delimiters = self.delimiters
        orig_input = input
        for delim in delimiters:
            input = input.replace(delim,' ')
        input = input.split()
        return input# }}}
# }}}

yes = ['y','Y',"yes","Yes"]
no = ['n','N',"no","No"]
def make_yes_no_collector(prompt,help_string = None):# {{{
    if help_string is None:
        help_string = "Please enter yes or no"
    collector = InputCollector(prompt,help_string = help_string,valid_options=yes+no)
    return collector#}}}
def is_yes(answer):# {{{
    return answer in yes# }}}
def is_no(answer):# {{{
    return answer in no# }}}

def warn_unused_kwargs(kwargs):# {{{
    if len(kwargs) == 0:
        return
    print("**WARNING** Unused keyword arguments:")
    for key,val in kwargs.items():
        print("    ",key,":",val)
    print()
    return# }}}

def recursive_print(object_dictionary,level = 0):# {{{
    for name, obj in object_dictionary.items():
        if isinstance(obj,dict):
            print('    '*level, name)
            recursive_print(obj,level+1)
        else:
            print('    '*level, name,":", obj)
    return
# }}}
def load_json(path, full_path = False):# {{{
    from snap_workflow.utils import path as w_path
    from snap_workflow.utils.constants import WORKFLOW
    if not full_path:
        root_path = w_path.get_root()
        path = root_path + WORKFLOW + path
    if not os.path.isfile(path):
        raise Exception(f"Cannot load JSON {path}. File does not exist")

    with open(path,'r') as handle:
        obj = json.load(handle)
    return obj
# }}}
def make_json(path, full_path = False,obj = None):# {{{
    from snap_workflow.utils import path as w_path
    from snap_workflow.utils.constants import WORKFLOW
    if not full_path:
        root_path = w_path.get_root()
        path = root_path + WORKFLOW + path
    if os.path.isfile(path):
        raise Exception(f"Cannot make JSON {path}. File already exists")

    if obj is None:
        obj = {}
    save_json(path,obj,full_path=True)

    return obj
# }}}
def save_json(path,obj,full_path = False):# {{{
    from snap_workflow.utils import path as w_path
    from snap_workflow.utils.constants import WORKFLOW
    if not full_path:
        root_path = w_path.get_root()
        path = root_path + WORKFLOW + path
    with open(path,'w') as handle:
        obj = json.dump(obj,handle,indent = 4)
    return obj
# }}}

def load_config(path, full_path=False):
    from snap_workflow.utils import path as w_path
    from snap_workflow.utils.constants import WORKFLOW
    if not full_path:
        root_path = w_path.get_root()
        path = root_path + WORKFLOW + path
        
    json_file = path if path.endswith(".json") else path + ".json"
    if os.path.isfile(json_file):
        with open(json_file, 'r') as handle:
            return json.load(handle)
            
    yaml_file = path if (path.endswith(".yaml") or path.endswith(".yml")) else path + ".yaml"
    if not os.path.isfile(yaml_file):
        alt_yaml = yaml_file[:-4] + "yml"
        if os.path.isfile(alt_yaml):
            yaml_file = alt_yaml
            
    if os.path.isfile(yaml_file):
        try:
            import yaml
        except ImportError:
            raise ImportError("The 'pyyaml' package is required to read YAML parameter files. Please install it using 'pip install pyyaml'.")
        with open(yaml_file, 'r') as handle:
            return yaml.safe_load(handle)
            
    raise FileNotFoundError(f"Cannot load config {path}. File does not exist as JSON or YAML.")

def save_config(path, obj, format="json", full_path=False):
    from snap_workflow.utils import path as w_path
    from snap_workflow.utils.constants import WORKFLOW
    if not full_path:
        root_path = w_path.get_root()
        path = root_path + WORKFLOW + path
        
    if format == "yaml" or format == "yml":
        try:
            import yaml
        except ImportError:
            raise ImportError("The 'pyyaml' package is required to write YAML parameter files. Please install it using 'pip install pyyaml'.")
        yaml_file = path if (path.endswith(".yaml") or path.endswith(".yml")) else path + ".yaml"
        with open(yaml_file, 'w') as handle:
            yaml.safe_dump(obj, handle, default_flow_style=False)
        return obj
    else:
        json_file = path if path.endswith(".json") else path + ".json"
        with open(json_file, 'w') as handle:
            json.dump(obj, handle, indent=4)
        return obj

def get_default_format():
    global_config_file = os.path.join(GLOBAL_CONFIG_DIR, "config.json")
    if os.path.isfile(global_config_file):
        try:
            with open(global_config_file, 'r') as f:
                cfg = json.load(f)
            return cfg.get("default_format", "json")
        except Exception:
            return "json"
    return "json"
