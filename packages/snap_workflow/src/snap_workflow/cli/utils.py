import os
import sys
from snap_workflow.utils import io


def parse_remaining(args):
    kwargs = dict()
    new_args = list()
    key = None
    val = list()

    def assign_val():
        nonlocal val, key, kwargs
        if key is not None:
            if len(val) == 1:
                kwargs[key] = val[0]
            elif len(val) == 0:
                kwargs[key] = True
            else:
                kwargs[key] = val
        val = list()
        key = None

    for arg in args:
        if arg.startswith("-"):
            assign_val()
            key = arg.lstrip("-")
        else:
            if key is None:
                new_args.append(arg)
            else:
                val.append(arg)
    assign_val()
    return new_args, kwargs


def execute_option(key, options, parsed_command, args):
    if len(args) == 0:
        val = None
    else:
        val = args[0]

    if val in options:
        args.pop(0)
        options[val](parsed_command, args)
    else:
        keys = list(options.keys())
        help_string = f"Action to be taken on {key.split('_')[0]}"
        collector = io.InputCollector(f"Select {key}: ", help_string, valid_options=keys, keys=[key])
        parsed_val = collector.parse_kwargs(dict())
        if parsed_val is not None:
            options[parsed_val](parsed_command, args)
        else:
            choice = collector.collect()
            options[choice](parsed_command, args)


def get_csv_arg(kwargs, keys):
    for k in keys:
        val = kwargs.pop(k, None)
        if val is not None:
            if isinstance(val, list):
                return ",".join(str(x) for x in val)
            return str(val)
    return ""


def get_data_format(kwargs):
    prompt = "Format: "
    help_string = "file format to convert parameters to"
    input_collector = io.InputCollector(prompt, help_string,
                                         valid_options=["yaml", "yml", "json"],
                                         keys=["format", "f", "Format", "F"])

    res = input_collector.parse_kwargs(kwargs)
    if res is not None:
        return res
    return input_collector.collect()


def get_script_path(kwargs):
    prompt = "Enter script path: "
    help_string = "The path of the python file containing the workflow instructions"
    collector = io.InputCollector(prompt, help_string,
                                   keys=["f", "script", "F", "Script"],
                                   add_checks=lambda x: isinstance(x, str) and os.path.exists(x),
                                   add_errors="Path must point to a valid file")

    return collector.parse_kwargs(kwargs)


def get_completions(args=None, prefix="", shell='bash'):
    if args is None:
        args = []
    if isinstance(args, str):
        shell = args
        args = []
        if shell in ['bash', 'zsh']:
            return get_shell_completion_script(shell)

    if prefix and prefix.startswith("-"):
        flags = ["--dry-run", "--test", "--force", "--help", "-h", "-f", "-w", "-s", "-e", "-g", "--global"]
        return [f for f in flags if f.startswith(prefix)]

    if args and args[-1] in ["-s", "-S", "--stage", "--stages"]:
        try:
            from snap_workflow.core.domain.stages import load_stages
            st = list(load_stages().keys()) + ["all"]
            if prefix:
                st = [s for s in st if s.startswith(prefix)]
            return st
        except Exception:
            return []

    if args and args[-1] in ["-w", "-W", "--sweep", "--sweeps"]:
        try:
            from snap_workflow.core.domain.sweeps import load_sweeps
            sw = list(load_sweeps().keys()) + ["all"]
            if prefix:
                sw = [s for s in sw if s.startswith(prefix)]
            return sw
        except Exception:
            return []

    if not args:
        commands = ["init", "build", "stage", "sweep", "variable", "status", "reset", "convert", "set", "remove", "collect", "zip", "submit", "remote", "server", "spoint", "add", "print", "update", "plot", "clean", "completions", "autocomplete"]
        if prefix:
            commands = [c for c in commands if c.startswith(prefix)]
        return commands

    first_arg = args[0]
    mapping = {
        "stage": ["add", "print", "list"],
        "sweep": ["add", "print", "list", "reset", "remove"],
        "variable": ["add", "print", "list"],
        "status": ["print", "list", "set", "reset", "submit"],
        "spoint": ["print", "list", "set", "reset", "submit"],
        "remote": ["add", "setup", "sync", "connect", "list"],
        "server": ["start", "submit"],
        "add": ["stage", "sweep", "variable"],
        "remove": ["sweep"],
        "reset": ["stage", "sweep", "spoint"],
        "print": ["stage", "sweep", "variable", "spoint", "status"],
        "set": ["status", "spoint", "params", "python"]
    }
    cmds = mapping.get(first_arg, [])
    if prefix:
        cmds = [c for c in cmds if c.startswith(prefix)]
    return cmds


def get_shell_completion_script(shell):
    if shell == 'zsh':
        return "#compdef workflow\n"
    return "_workflow_completion"
