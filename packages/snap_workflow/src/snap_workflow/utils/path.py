import os,sys
from snap_workflow.utils.constants import *
from snap_workflow.utils.exceptions import WorkflowError


def get_root(start_dir="."):
    """Finds the absolute path of the workflow root directory containing .workflow/."""
    curr = os.path.abspath(start_dir)
    while True:
        if os.path.isdir(os.path.join(curr, ".workflow")):
            return curr
        parent = os.path.dirname(curr)
        if parent == curr:
            break
        curr = parent
    raise Exception("Not in a workflow system. Run workflow init to start setup")


def from_root(*paths):
    """Returns an absolute path joined with the workflow root directory."""
    root = get_root()
    if not paths:
        return root
    return os.path.normpath(os.path.join(root, *paths))


def exists(*paths):
    """Checks if a path exists (relative to root if not absolute)."""
    p = paths[0] if len(paths) == 1 and os.path.isabs(paths[0]) else from_root(*paths)
    return os.path.exists(p)


def isfile(*paths):
    """Checks if a path is a file (relative to root if not absolute)."""
    p = paths[0] if len(paths) == 1 and os.path.isabs(paths[0]) else from_root(*paths)
    return os.path.isfile(p)


def isdir(*paths):
    """Checks if a path is a directory (relative to root if not absolute)."""
    p = paths[0] if len(paths) == 1 and os.path.isabs(paths[0]) else from_root(*paths)
    return os.path.isdir(p)


def relpath(path_str, start=None):
    """Returns relative path from start (defaults to workflow root)."""
    if start is None:
        try:
            start = get_root()
        except Exception:
            start = os.getcwd()
    return os.path.relpath(path_str, start)


def rel_to_root(from_dir="."):
    """Returns relative path from from_dir back to the workflow root (e.g. '../..')."""
    abs_from = os.path.abspath(from_dir)
    abs_root = get_root(abs_from)
    return os.path.relpath(abs_root, abs_from)


def abspath(path_str):
    """Returns absolute path."""
    return os.path.abspath(path_str)


def join(*paths):
    """Joins path components."""
    return os.path.join(*paths)


class FromDir:
    def __init__(self, from_dir=None):
        self.start = os.getcwd()
        self.from_dir = from_dir
        return

    def __enter__(self):
        if self.from_dir:
            os.chdir(self.from_dir)
        return self.from_dir

    def __exit__(self, exc_type, exc_val, traceback):
        os.chdir(self.start)
        return

def make_sym(real, link, overwrite=False, relative=True):  # {{{
    real_abs = os.path.abspath(real) if not os.path.isabs(real) else real
    link_abs = os.path.abspath(link) if not os.path.isabs(link) else link
    if relative:
        target = os.path.relpath(real_abs, os.path.dirname(link_abs))
    else:
        target = real_abs

    if not os.path.islink(link_abs):
        os.symlink(target, link_abs)
    elif os.path.islink(link_abs) and not os.path.exists(link_abs):
        os.remove(link_abs)
        os.symlink(target, link_abs)
    elif overwrite:
        os.remove(link_abs)
        os.symlink(target, link_abs)
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
                        data = io.load_json(fpath, full_path=True) if fname.endswith(".json") else io.load_config(fpath, full_path=True)
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

