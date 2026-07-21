import os,sys
import shutil
from .strings import *

#---- Main ----
def add_workers(*args,**kwargs):# {{{
    from . import path

    #General Setup
    root = path.get_root()
    workers_dir = root+"/workers"
    os.makedirs(workers_dir,exist_ok = True)

    print("Getting new worker info. Enter help at any time for options.")
    workers = load_workers()
    worker_names = list(workers.keys())

    if not os.isfile(workers_dir + "/worker.sh"):
        shutil.copy(os.path.dirname(__file__)+"/templates/worker.sh",
                    workers_dir)
# }}}

#---- IO ----
def load_workers():# {{{
    from . import io
    return io.load_json(WORKERS)# }}}
def save_workers(stages):# {{{
    from . import io
    return io.save_json(WORKERS,workers)# }}}
def make_workers():# {{{
    from . import io
    return io.make_json(WORKERS)# }}}

#---- Support ----
def get_new_worker_name(kwargs):#{{{
    from . import io
    worker_names = list(get_workers().keys)
    prompt = "Please enter the name by which this worker should be identified: ",
    help_str = "The name which workflow will associate with the new worker."
    keys = ["N","n","Name","name"]
    collector = io.Input_Collector(prompt,help_str,
                                   used_exclusions = worker_names,
                                   keys = keys)
    name = collector.parse_kwargs(kwargs)
    if name is not None:
        return name
    else:
        return collector.collect()
    #}}}
