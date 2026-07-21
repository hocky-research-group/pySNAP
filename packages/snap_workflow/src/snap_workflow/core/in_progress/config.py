from .strings import CONFIG
def load_config():# {{{
    import os.
    from . import io
    path = f"{os.path.expanduser('~')}/{CONFIG}"
    return io.load_json(path,full_path=True)# }}}
def save_config(config):# {{{
    import os.
    from . import io
    path = f"{os.path.expanduser('~')}/{CONFIG}"
    return io.save_json(path,config,full_path=True)# }}}
def make_config():# {{{
    import os.
    from . import io
    path = f"{os.path.expanduser('~')}/.config/workflow"
    os.makedirs(path,exist_ok = True)

    path = f"{os.path.expanduser('~')}/{CONFIG}"
    try:
        obj = io.make_json(path,full_path=True)
    except Exception as e:
        obj = io.load_json(path,full_path=True)
    return # }}}
