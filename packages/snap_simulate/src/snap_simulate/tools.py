import os, sys
import json

def get_options(info):# {{{
    if "options" in info:
        options = info["options"]
    else:
        options = {}

    if "options_encoding" in info:
        options_encoding = info["options_encoding"]
        options = decode(options,options_encoding)
    return options# }}}
def decode(value,encode):# {{{
    if isinstance(value,list):
        if encode == "tuple":
            return tuple(value)

        ret = []
        for val,enc in zip(value,encode):
            ret.append(decode(val,enc))
        return ret
    elif isinstance(value,dict):
        ret = {}
        for key in value.keys():
            if key in encode:
                ret[key] = decode(value[key],encode[key])
            else:
                ret[key] = value[key]
        return ret
    else:
        if isinstance(encode,list):
            ret = value
            for enc in encode:
                ret = decode(ret,enc)
            return ret
        elif encode == "direct":
            return value
        elif encode == "negative":
            return -value
        elif encode == "int":
            return int(value)
        elif encode == "float":
            return float(value)
        elif encode == "json":
            with open(value) as file:
                ret = json.load(file)
            return ret
        else:
            raise ValueError(f"Can't decode encoding type {encode}")# }}}
def recursive_print(object_dictionary,level = 0):# {{{
    for name, obj in object_dictionary.items():
        print('    '*level, name)
        if isinstance(obj,dict):
            recursive_print(obj,level+1)
    return# }}}
def dict_defines(dic, key):# {{{
    return key in dic and dic[key] is not None
# }}}
