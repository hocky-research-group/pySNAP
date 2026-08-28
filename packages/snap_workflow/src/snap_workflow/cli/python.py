import os
import sys
import shutil
from snap_workflow.utils import io, path
from snap_workflow.utils.constants import LOCAL_CONFIG, GLOBAL_CONFIG_DIR
from snap_workflow.core.domain.stages import load_stages, set_python_config
from snap_workflow.cli.utils import parse_remaining, execute_option
from snap_workflow.cli.prompts import get_existing_stage_name


def print_python_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    root = path.get_root()
    
    # 1. Global Python
    global_cfg_file = os.path.join(GLOBAL_CONFIG_DIR, LOCAL_CONFIG)
    global_py = None
    if os.path.isfile(global_cfg_file):
        try:
            g_data = io.load_json(global_cfg_file, full_path=True)
            global_py = g_data.get("default_python_env")
        except Exception:
            pass
    if not global_py:
        global_py = shutil.which("python3") or sys.executable

    # 2. Project Python
    proj_cfg_file = os.path.join(root, ".workflow", "config.json")
    proj_py = None
    if os.path.isfile(proj_cfg_file):
        try:
            p_data = io.load_json(proj_cfg_file, full_path=True)
            proj_py = p_data.get("default_python_env")
        except Exception:
            pass

    print(f"{'SCOPE':<20} {'PYTHON INTERPRETER PATH'}")
    print("-" * 70)
    print(f"{'Global Fallback':<20} {global_py}")
    proj_str = proj_py if proj_py else f"(inherits global: {global_py})"
    print(f"{'Project Default':<20} {proj_str}")
    print(f"{'Current Active':<20} {sys.executable}")

    stages = load_stages()
    if stages:
        print()
        print(f"{'STAGE':<20} {'STAGE PYTHON PATH'}")
        print("-" * 70)
        for st in stages:
            st_dir = os.path.join(root, st)
            env_file = None
            for ext in [".json", ".yaml", ".yml"]:
                candidate = os.path.join(st_dir, f"env{ext}")
                if os.path.isfile(candidate):
                    env_file = candidate
                    break
            st_py = "(default)"
            if env_file:
                try:
                    env_data = io.load_config(os.path.join(st_dir, "env"), full_path=True)
                    if env_data.get("python_path"):
                        st_py = env_data["python_path"]
                except Exception:
                    pass
            print(f"{st:<20} {st_py}")
    io.warn_unused_kwargs(kwargs)
    print("\n(For a list of all python subcommands, run 'workflow python help')")


def set_python_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    py_path = args[0] if len(args) > 0 else kwargs.pop("p", kwargs.pop("python", kwargs.pop("path", None)))
    if not py_path:
        py_path = sys.executable

    is_global = kwargs.pop("global", False) or kwargs.pop("g", False)
    stage_name = get_existing_stage_name(kwargs, include_all=True, is_list=True, get_input=False, default=None)
    io.warn_unused_kwargs(kwargs)

    if stage_name:
        set_python_config(python_path=py_path, stage_names=stage_name)
    elif is_global:
        set_python_config(python_path=py_path, is_global=True)
    else:
        root = path.get_root()
        cfg_file = os.path.join(root, ".workflow", "config.json")
        cfg = {}
        if os.path.isfile(cfg_file):
            try:
                cfg = io.load_json(cfg_file, full_path=True)
            except Exception:
                cfg = {}
        cfg["default_python_env"] = py_path
        io.save_json(cfg_file, cfg, full_path=True)
        print(f"Updated project default_python_env to '{py_path}'")


def help_python_cmd(parsed_command, args):
    print("Available subcommands for 'workflow python':")
    print("  print                      Display configured Python interpreters (global, project, stage)")
    print("  set [path] [-s S] [--global] Set the Python interpreter path (defaults to current active)")


def main_python(parsed_command, args):
    if not args or args[0].startswith("-"):
        return print_python_cmd(parsed_command, args)

    python_options = {
        "print": print_python_cmd,
        "set": set_python_cmd,
        "help": help_python_cmd,
        "--help": help_python_cmd,
        "-h": help_python_cmd,
    }
    execute_option("python_option", python_options, parsed_command=parsed_command, args=args)
