import os,sys
from snap_workflow.utils.constants import *
def get_root(relative_to="."):# {{{
    start = os.getcwd()
    os.chdir(relative_to)
    old_path = ''
    new_path = os.path.realpath('.')
    count = 0
    while new_path != old_path:
        if os.path.isdir(new_path + "/.workflow"):
            ret_path = f".{'/..'*count}"
            os.chdir(start)
            return ret_path
        old_path = new_path
        new_path = os.path.realpath(new_path + "/..")
        count += 1
    os.chdir(start)
    raise Exception("Not in a workflow system. Run workflow init to start setup")

# }}}
class FromRoot():# {{{
    def __init__(self):
        return

    def __enter__(self):
        self.start = os.getcwd()
        self.root = get_root()
        os.chdir(self.root)
        return

    def __exit__(self,exc_type,exc_val,traceback):
        os.chdir(self.start)
        return
# }}}
class FromDir():# {{{
    def __init__(self,from_dir=None):
        self.start = os.getcwd()
        self.from_dir = from_dir
        return

    def __enter__(self):
        os.chdir(self.from_dir)
        return

    def __exit__(self,exc_type,exc_val,traceback):
        os.chdir(self.start)
        return
# }}}

def make_sym(real,link,overwrite=False):# {{{
    if not os.path.islink(link):
        os.symlink(real,link) 
    elif os.path.islink(link) and not os.path.exists(link):
        os.remove(link)
        os.symlink(real,link) 
    elif overwrite:
        os.remove(link)
        os.symlink(real,link) 
    return
# }}}
def clear_directory(job_path):# {{{
    import shutil
    for filename in os.listdir(job_path):
        file_path = os.path.join(job_path,filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print('Failed to delete %s. Reason: %s' % (file_path, e))# }}}

def get_default_python_file():
    from snap_workflow.utils import constants
    global_dir = getattr(constants, "GLOBAL_CONFIG_DIR", os.path.expanduser("~/.config/snap_workflow"))
    default_py = getattr(constants, "DEFAULT_PYTHON", "default_python")
    return os.path.join(global_dir, default_py)

def ensure_default_python_path(python_path=None, overwrite=False):
    target_file = get_default_python_file()
    if os.path.isfile(target_file) and not overwrite:
        try:
            with open(target_file, "r") as f:
                val = f.read().strip()
                if val:
                    return val
        except Exception:
            pass

    if not python_path:
        python_path = sys.executable
    try:
        os.makedirs(os.path.dirname(target_file), exist_ok=True)
        with open(target_file, "w") as f:
            f.write(str(python_path).strip() + "\n")
    except Exception:
        pass
    return python_path

def load_python_path(stage=None):
    from snap_workflow.utils import io
    from snap_workflow.utils.exceptions import WorkflowError

    # 1. Stage Level (if stage is provided)
    if stage:
        try:
            root = get_root()
            stage_dir = os.path.join(root, stage)
            for fname in ("env.json", "env.yaml", "env.yml"):
                fpath = os.path.join(stage_dir, fname)
                if os.path.isfile(fpath):
                    try:
                        data = io.load_json(fpath, full_path=True) if fname.endswith(".json") else io.load_yaml(fpath, full_path=True)
                        py_val = data.get("python_path")
                        if py_val and py_val != "FIXME":
                            return py_val
                    except Exception:
                        pass
        except Exception:
            pass

    # 2. Project Level
    try:
        root = get_root()
        local_cfg = os.path.join(root, ".workflow", "config.json")
        if os.path.isfile(local_cfg):
            try:
                data = io.load_json(local_cfg, full_path=True)
                py_val = data.get("default_python_env")
                if py_val and py_val != "FIXME":
                    return py_val
            except Exception:
                pass
    except Exception:
        pass

    # 3. Global Level
    def_file = get_default_python_file()
    if os.path.isfile(def_file):
        try:
            with open(def_file, "r") as f:
                val = f.read().strip()
                if val and val != "FIXME":
                    return val
        except Exception:
            pass

    raise WorkflowError("No valid Python interpreter path found in stage, project, or global configuration.")

