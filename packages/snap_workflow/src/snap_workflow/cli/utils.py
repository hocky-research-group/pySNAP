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
    elif val is not None:
        valid_cmds = [k for k in options if not k.startswith('-')]
        print(f"Error: Unknown subcommand '{val}' for '{parsed_command}'. Available subcommands: {', '.join(valid_cmds)}", file=sys.stderr)
        sys.exit(1)
    else:
        keys = [k for k in options.keys() if not k.startswith('-')]
        prompt_label = key.replace('_', ' ')
        help_string = f"Action to be taken on {key.split('_')[0]}"
        collector = io.InputCollector(f"Select {prompt_label}: ", help_string, valid_options=keys, keys=[key])
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

    # 2. Top-level completion (no positional command arguments provided yet)
    if not args:
        commands = [
            "init", "stage", "sweep", "variable", "status",
            "spoint", "params", "data", "python", "remote", "server",
            "local", "auto", "zip", "completions", "autocomplete"
        ]
        if prefix:
            commands = [c for c in commands if c.startswith(prefix)]
        return commands

    # 3. Level 1 subcommand mapping (when only 1 positional argument has been provided)
    first_arg = args[0]
    if len(args) == 1:
        mapping = {
            "stage": ["add", "print"],
            "sweep": ["add", "print", "remove"],
            "variable": ["add", "print"],
            "status": ["print", "set", "reset"],
            "spoint": ["reset", "submit"],
            "params": ["set", "convert"],
            "data": ["collect"],
            "python": ["print", "set"],
            "remote": ["add", "setup", "sync", "connect", "print", "reserve", "auto", "autoschedule"],
            "server": ["start", "auto", "autoschedule", "reserve", "stop", "shutdown"],
            "local": ["auto", "autoschedule"],
            "auto": [],
        }
        cmds = mapping.get(first_arg, [])
        if prefix:
            cmds = [c for c in cmds if c.startswith(prefix)]
        return cmds

    # 4. Level 2+ subcommand completions (when 2 or more positional arguments have been provided)
    second_arg = args[1]

    if first_arg == "server":
        if second_arg in ["auto", "autoschedule", "reserve"]:
            if len(args) == 2:
                try:
                    from snap_workflow.remote.io import load_global_remotes, load_local_remotes
                    remotes = ["local"] + list(dict.fromkeys(list(load_local_remotes().keys()) + list(load_global_remotes().keys())))
                    if prefix:
                        remotes = [r for r in remotes if r.startswith(prefix)]
                    return remotes
                except Exception:
                    return ["local"]
            elif second_arg == "reserve" and len(args) == 3:
                try:
                    from snap_workflow.utils import path
                    profiles = []
                    for prof_dir in [path.from_root("sbatch_profiles"), os.path.expanduser("~/.config/snap_workflow/sbatch_profiles")]:
                        if os.path.isdir(prof_dir):
                            for f in os.listdir(prof_dir):
                                if f.endswith((".json", ".yaml", ".yml")):
                                    profiles.append(os.path.splitext(f)[0])
                    profiles = list(dict.fromkeys(profiles))
                    if not profiles:
                        profiles = ["cpu", "gpu"]
                    if prefix:
                        profiles = [p for p in profiles if p.startswith(prefix)]
                    return profiles
                except Exception:
                    return ["cpu", "gpu"]

    elif first_arg == "local":
        if second_arg in ["auto", "autoschedule"]:
            try:
                from snap_workflow.core.domain.stages import load_stages
                st = list(load_stages().keys())
                if prefix:
                    st = [s for s in st if s.startswith(prefix)]
                return st
            except Exception:
                return []

    elif first_arg == "remote":
        if second_arg in ["auto", "autoschedule"]:
            try:
                from snap_workflow.remote.io import load_global_remotes, load_local_remotes
                remotes = ["local"] + list(dict.fromkeys(list(load_local_remotes().keys()) + list(load_global_remotes().keys())))
                if prefix:
                    remotes = [r for r in remotes if r.startswith(prefix)]
                return remotes
            except Exception:
                return ["local"]
        elif second_arg in ["reserve"]:
            if len(args) == 2:
                try:
                    from snap_workflow.remote.io import load_global_remotes, load_local_remotes
                    remotes = list(dict.fromkeys(list(load_local_remotes().keys()) + list(load_global_remotes().keys())))
                    if prefix:
                        remotes = [r for r in remotes if r.startswith(prefix)]
                    return remotes
                except Exception:
                    return []
            elif len(args) == 3:
                try:
                    from snap_workflow.utils import path
                    profiles = []
                    for prof_dir in [path.from_root("sbatch_profiles"), os.path.expanduser("~/.config/snap_workflow/sbatch_profiles")]:
                        if os.path.isdir(prof_dir):
                            for f in os.listdir(prof_dir):
                                if f.endswith((".json", ".yaml", ".yml")):
                                    profiles.append(os.path.splitext(f)[0])
                    profiles = list(dict.fromkeys(profiles))
                    if not profiles:
                        profiles = ["cpu", "gpu"]
                    if prefix:
                        profiles = [p for p in profiles if p.startswith(prefix)]
                    return profiles
                except Exception:
                    return ["cpu", "gpu"]
        elif second_arg in ["sync", "connect", "setup", "print"]:
            try:
                from snap_workflow.remote.io import load_global_remotes, load_local_remotes
                remotes = list(dict.fromkeys(list(load_local_remotes().keys()) + list(load_global_remotes().keys())))
                if prefix:
                    remotes = [r for r in remotes if r.startswith(prefix)]
                return remotes
            except Exception:
                return []
        elif second_arg in ["add", "list"]:
            flags = ["--global", "--host", "--help"]
            if prefix:
                flags = [f for f in flags if f.startswith(prefix)]
            return flags

    elif first_arg in ["status", "spoint"]:
        if second_arg in ["set"]:
            statuses = ["initialized", "submitted", "complete", "error"]
            if prefix:
                statuses = [s for s in statuses if s.startswith(prefix)]
            return statuses
        elif second_arg in ["reset"]:
            targets = ["errors", "params", "sweep", "spoint"]
            if prefix:
                targets = [t for t in targets if t.startswith(prefix)]
            return targets
        elif second_arg in ["print", "list", "submit"]:
            try:
                from snap_workflow.core.domain.sweeps import load_sweeps
                sw = list(load_sweeps().keys()) + ["all"]
                if prefix:
                    sw = [s for s in sw if s.startswith(prefix)]
                return sw
            except Exception:
                return []

    elif first_arg in ["stage"]:
        if second_arg in ["print", "list"]:
            try:
                from snap_workflow.core.domain.stages import load_stages
                st = list(load_stages().keys()) + ["all"]
                if prefix:
                    st = [s for s in st if s.startswith(prefix)]
                return st
            except Exception:
                return []

    elif first_arg in ["sweep"]:
        if second_arg in ["print", "list", "reset", "remove"]:
            try:
                from snap_workflow.core.domain.sweeps import load_sweeps
                sw = list(load_sweeps().keys()) + ["all"]
                if prefix:
                    sw = [s for s in sw if s.startswith(prefix)]
                return sw
            except Exception:
                return []

    elif first_arg == "reset":
        if second_arg == "stage":
            try:
                from snap_workflow.core.domain.stages import load_stages
                st = list(load_stages().keys()) + ["all"]
                if prefix:
                    st = [s for s in st if s.startswith(prefix)]
                return st
            except Exception:
                return []
        elif second_arg == "sweep":
            try:
                from snap_workflow.core.domain.sweeps import load_sweeps
                sw = list(load_sweeps().keys()) + ["all"]
                if prefix:
                    sw = [s for s in sw if s.startswith(prefix)]
                return sw
            except Exception:
                return []
        elif second_arg == "spoint":
            targets = ["errors", "params", "sweep", "spoint"]
            if prefix:
                targets = [t for t in targets if t.startswith(prefix)]
            return targets

    elif first_arg == "set":
        if second_arg in ["status", "spoint"]:
            statuses = ["initialized", "submitted", "complete", "error"]
            if prefix:
                statuses = [s for s in statuses if s.startswith(prefix)]
            return statuses

    return []


def get_shell_completion_script(shell):
    if shell == 'zsh':
        return """#compdef workflow
_workflow_completion() {
    local -a completions
    completions=(${(f)"$(workflow _complete "${words[@]:1}")"})
    _describe 'values' completions
}
compdef _workflow_completion workflow
"""
    return """_workflow_completion() {
    local cur prev words cword
    _get_comp_words_by_ref -n : cur prev words cword 2>/dev/null || {
        cur="${COMP_WORDS[COMP_CWORD]}"
        prev="${COMP_WORDS[COMP_CWORD-1]}"
        words=("${COMP_WORDS[@]}")
        cword=$COMP_CWORD
    }
    local completions
    completions=$(workflow _complete "${words[@]:1}")
    COMPREPLY=( $(compgen -W "$completions" -- "$cur") )
    return 0
}
complete -F _workflow_completion workflow
"""
