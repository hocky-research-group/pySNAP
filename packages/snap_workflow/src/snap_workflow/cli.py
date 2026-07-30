import argparse
import sys
import os
import json
from snap_workflow.utils import io
from snap_workflow.utils.constants import *
from snap_workflow.core.workflow import initialize, zip_workflow
from snap_workflow.core.domain.stages import add_stage, print_stages, load_stages
from snap_workflow.core.domain.sweeps import add_sweep, remove_sweep, reset_sweep, print_sweeps, load_sweeps
from snap_workflow.core.domain.variables import add_variable, cast_values
from snap_workflow.core.domain.spoints import submit_spoints
from snap_workflow.core.data import collect_data
from snap_workflow.core.domain.status import set_status, print_status
from snap_workflow.utils.logging import setup_logging


def get_csv_arg(kwargs, keys):
    for k in keys:
        val = kwargs.pop(k, None)
        if val is not None:
            if isinstance(val, list):
                return ",".join(str(x) for x in val)
            return str(val)
    return ""

# --- Prompt / Interactive helpers ---
def prompt_each_stage(prompt):
    stages = load_stages()
    if len(stages) == 0:
        return []
    print(prompt)
    yes_stages = []
    help_str = "(y/n)"
    for stage in stages.keys():
        stage_prompt = f"    {stage}: "
        collector = io.make_yes_no_collector(stage_prompt, help_str)
        if io.is_yes(collector.collect()):
            yes_stages.append(stage)
    return yes_stages

def get_new_stage_name(kwargs):
    stages = list(load_stages().keys())
    prompt = "Enter new stage name: "
    help_string = "The name of the stage to be added"
    input_collector = io.InputCollector(prompt, help_string,
                                         used_exclusions=stages,
                                         exclusions=['all', 'custom'],
                                         keys=["name", "n", "Name", "N"],
                                         add_checks=lambda x: isinstance(x, str),
                                         add_errors="Stage name must be of type 'str'",
                                         char_exclusions=[' ', '\t', '\r', '\n', '/', '\\'])
    stage_name = input_collector.parse_kwargs(kwargs)
    if stage_name is not None:
        return stage_name
    return input_collector.collect()

def get_existing_stage_name(kwargs, include_all=False, is_list=False, get_input=True, default=None):
    stages = load_stages()
    if is_list:
        prompt = "Enter stage names: "
        help_string = "The name of the stages to be added"
    else:
        prompt = "Enter stage name: "
        help_string = "The name of the stage to be added"
    help_string += f" (defaults to '{default}')" if default is not None else ''

    valid_options = list(stages.keys())
    if include_all:
        valid_options += ["all"]
    input_collector = io.InputCollector(prompt, help_string,
                                         valid_options=valid_options,
                                         keys=["s", "S", "stage", "Stage"],
                                         default=default, 
                                         is_list=is_list)

    stage_name = input_collector.parse_kwargs(kwargs)
    if stage_name is not None:
        return stage_name
    if get_input:
        return input_collector.collect()
    else:
        return default

def get_sbatch_details(stage_name):
    prompt = f"Should the {stage_name} stage be submitted by sbatch? "
    submit_collector = io.make_yes_no_collector(prompt)
    submit = submit_collector.collect()
    submit = io.is_yes(submit)
    if submit:
        sbatch_details = dict()
        sbatch_details["--signal"] = "B:INT@60"
        sbatch_details["num_jobs"] = get_parallel_submit(stage_name)
        sbatch_details["multi_submission"] = get_multi_submit(stage_name)
        return sbatch_details
    else:
        return None

def get_parallel_submit(stage_name):
    prompt = f"Enter the number of {stage_name} spoints to be run in parallel on one submission: "
    help_string = "This is the number of spoints that workflow will try to submit on a single sbatch submission"
    input_collector = io.InputCollector(prompt, help_string,
                                         add_checks=str.isdigit,
                                         add_errors="Number must be a positive integer")
    return input_collector.collect()

def get_multi_submit(stage_name):
    prompt = f"Is {stage_name} expected to take multiple sbatch submissions to finish? (y/n) "
    collector = io.make_yes_no_collector(prompt)
    expect_multi = collector.collect()
    if io.is_yes(expect_multi):
        expect_multi = True
    elif io.is_no(expect_multi):
        expect_multi = False
    else:
        print(f"Interpreting {expect_multi} as no")
        print()
        expect_multi = False
    return expect_multi

def get_stage_dependencies(stages, kwargs):
    dep_keys = ["dependent_stage", "dep", "d"]
    help_string = f"Stages that must be run immediately before this stage. Entering multiple stages converges stages. Leaving blank indicates stage has no dependencies. Stages: {list(stages.keys())}"
    prompt = f"Enter immediate stage dependencies: "
    default = []
    collector = io.InputCollector(prompt, help_string, is_list=True,
                                   keys=dep_keys,
                                   valid_options=stages,
                                   default=default)
    dep_stages = collector.parse_kwargs(kwargs)
    if dep_stages is not None:
        return dep_stages
    return collector.collect()

def get_new_var_val(new_var_name):
    prompt = f"What value has been used for {new_var_name} so far? "
    help_str = "The value that all spoints used before now."
    input_collector = io.InputCollector(prompt, help_str)
    return input_collector.collect()

def get_new_variable_name(kwargs):
    from snap_workflow.core.domain.variables import get_variable_names
    variables = get_variable_names()
    prompt = f"Please enter variable name to add: "
    help_str = f"Name of variable you'd like to vary in this workflow"
    keys = ['n', 'N', 'name']
    collector = io.InputCollector(prompt, help_str,
                                   used_exclusions=variables,
                                   char_exclusions=["_"],
                                   keys=keys)
    new_var_name = collector.parse_kwargs(kwargs)
    if new_var_name is None:
        new_var_name = collector.collect()
    return new_var_name

def get_new_variable_type(var_name, kwargs):
    prompt = f"Enter the data type of {var_name}: "
    help_str = f"The data type of the variable: int(i), float(f), string(s), negative(n))"
    int_options = ["int", "i"]
    float_options = ["float", "f"]
    string_options = ["string", "str", "s"]
    negative_options = ["negative", "neg", "-", "n"]
    valid_options = int_options + float_options + string_options + negative_options
    keys = ['t', 'T', 'type']
    collector = io.InputCollector(prompt, help_str,
                                   keys=keys,
                                   valid_options=valid_options,
                                   is_list=True)
    types = collector.parse_kwargs(kwargs)
    if types is None:
        types = collector.collect()
    has_int = False
    has_float = False
    has_str = False
    has_neg = False
    for i in range(len(types)):
        t = types[i]
        if t in int_options:
            types[i] = "int"
            has_int = True
        elif t in float_options:
            types[i] = "float" 
            has_float = True
        elif t in string_options:
            types[i] = "str" 
            has_str = True
        elif t in negative_options:
            types[i] = "neg" 
            has_neg = True
        else:
            raise Exception("Not an acceptable data type")
    if (has_int and has_float) or (has_str and len(types) > 1):
        raise Exception(f"Variable cannot have this mix of data types: {types}")
    return types

def get_variable_values(variable, types):
    from snap_workflow.core.domain.variables import generate_values
    prompt = f"    {variable}: "
    help_str = f"    Enter values to iterate {variable} through or 'generate'"
    collector = io.InputCollector(prompt, help_str, 
                                   default=list(), is_list=True, 
                                   list_conversion=generate_values)
    cannot_cast = True 
    while cannot_cast:
        values = collector.collect()
        try:
            cast_values(variable, values, types)
            cannot_cast = False
        except Exception:
            print("Unable to cast input values to the appropriate type")
            continue
    return values

def get_stage_variables(kwargs):
    from snap_workflow.core.domain.variables import get_variable_names
    variables = get_variable_names()
    stage_variables = []
    print("Is this stage dependent on the variable: (y/n)")
    for var in variables:
        prompt = f"    {var}? "
        help_str = f"    Indicate whether this stage is dependent on this variable"
        collector = io.make_yes_no_collector(prompt, help_str)
        if io.is_yes(collector.collect()):
            stage_variables.append(var)
    return stage_variables

def get_new_sweep_name(kwargs):
    from snap_workflow.core.domain.sweeps import load_sweeps
    sweeps = load_sweeps()
    sweeps = list(sweeps.keys())
    name_keys = ["name", "n"]
    prompt = f"Enter sweep name: "
    help_str = "The name of the sweep to be added"
    exclusions = ["all", "custom"]
    collector = io.InputCollector(prompt, help_str,
                                   exclusions=exclusions,
                                   keys=name_keys,
                                   used_exclusions=sweeps)
    sweep_name = collector.parse_kwargs(kwargs)
    if sweep_name is not None:
        return sweep_name
    return collector.collect()

def get_existing_sweep_name(kwargs, include_all=False, include_custom=False, is_list=False, get_input=True, default=None):
    from snap_workflow.core.domain.sweeps import load_sweeps
    sweeps = load_sweeps()
    name_keys = ["sweep", "w", "matrix", "m"]

    if is_list:
        prompt = f"Enter sweep names: "
        help_str = "The name of the sweeps to be added"
    else:
        prompt = f"Enter sweep name: "
        help_str = "The name of the sweep to be added"
    help_str += f" (defaults to '{default}')" if default is not None else ''

    valid_options = list(sweeps.keys())
    if include_all:
        valid_options += ["all"]
    if include_custom:
        valid_options += ["custom"]
    collector = io.InputCollector(prompt, help_str,
                                   keys=name_keys,
                                   valid_options=valid_options,
                                   is_list=is_list,
                                   default=default)
    sweep_name = collector.parse_kwargs(kwargs)
    if sweep_name is not None:
        return sweep_name
    elif get_input:
        return collector.collect()
    else:
        return default

def confirm_sweep_removal(type_str, name):
    prompt = f"Are you sure you want to remove {type_str} {name} (y/n)? "
    collector = io.make_yes_no_collector(prompt)
    confirmation = collector.collect()
    if io.is_no(confirmation):
        print(f"{type_str} {name} not removed")
        raise SystemExit
    return

def confirm_hard_sweep_removal(type_str, name):
    prompt = f"Hard removal of {type_str} {name} will completely remove all directories associated with it, permanently deleting any files and/or data inside\n"
    prompt = prompt + f"Are you sure you want to remove hard {type_str} {name} (y/n)? "
    collector = io.make_yes_no_collector(prompt)
    confirmation = collector.collect()
    if io.is_no(confirmation):
        print(f"{type_str} {name} not removed")
        raise SystemExit
    return


def get_completions(args_before, current_token):
    top_options = ["init", "update", "submit", "add", "print", "set", "reset", "convert", "plot", "collect", "zip", "remove", "server", "remote", "stage", "sweep", "variable", "status", "spoint", "autocomplete"]

    sub_options = {
        "add": ["stage", "sweep", "variable"],
        "print": ["status", "stages", "sweeps"],
        "set": ["status", "python"],
        "reset": ["errors", "params", "spoint", "sweep"],
        "convert": ["params"],
        "remove": ["sweep"],
        "server": ["start", "submit"],
        "remote": ["add", "setup"],
        "stage": ["add", "print", "list"],
        "sweep": ["add", "print", "list", "reset", "remove"],
        "variable": ["add"],
        "status": ["print", "set"],
        "spoint": ["reset", "submit"],
        "autocomplete": ["bash", "zsh"],
    }

    def get_stages():
        try:
            return list(load_stages().keys())
        except Exception:
            return []

    def get_sweeps():
        try:
            return list(load_sweeps().keys())
        except Exception:
            return []

    def get_remotes():
        remotes = ["local"]
        try:
            from snap_workflow.utils.constants import GLOBAL_REMOTES_FILE
            import json
            if os.path.isfile(GLOBAL_REMOTES_FILE):
                with open(GLOBAL_REMOTES_FILE, "r") as f:
                    data = json.load(f)
                remotes.extend(data.keys())
        except Exception:
            pass
        return remotes

    def get_profiles():
        try:
            if os.path.isdir("workers"):
                profiles = set()
                for f in os.listdir("workers"):
                    if f.endswith(".json") or f.endswith(".yml") or f.endswith(".yaml"):
                        profiles.add(f.rsplit(".", 1)[0])
                    elif os.path.isfile(os.path.join("workers", f)):
                        profiles.add(f)
                return sorted(list(profiles))
        except Exception:
            pass
        return ["cpu", "gpu"]

    if not args_before:
        return [opt for opt in top_options if opt.startswith(current_token)]

    first_cmd = args_before[0]

    # Special handling for flags/options completion
    if current_token.startswith("-"):
        flags_map = {
            "submit": ["--test", "--no_sbatch", "-s", "--stage", "-w", "--sweep"],
            "collect": ["-v", "--verbose", "-s", "--stage"],
            "zip": ["--include_spoints", "-s", "--stage", "-w", "--sweep"],
            "remote": {
                "add": ["--host"],
                "setup": ["--path"],
            },
            "server": {
                "start": ["--host", "--port"],
                "submit": ["--profile", "--num-workers", "--sbatch-args", "-s", "--stage", "-w", "--sweep", "-xs", "--exclude-stage", "-xw", "--exclude-sweep"],
            },
            "sweep": {
                "reset": ["-w", "--sweep"],
                "remove": ["-w", "--sweep", "-f", "--force", "--hard"],
            },
            "status": {
                "print": ["-s", "--stage", "-w", "--sweep"],
                "set": ["-s", "--stage", "-w", "--sweep"],
            },
            "spoint": {
                "reset": ["-s", "--stage", "-w", "--sweep"],
                "submit": ["--test", "--no_sbatch", "-s", "--stage", "-w", "--sweep"],
            },
        }
        if first_cmd in flags_map:
            opts = flags_map[first_cmd]
            if isinstance(opts, dict) and len(args_before) > 1:
                sub_cmd = args_before[1]
                opts = opts.get(sub_cmd, [])
                if sub_cmd == "submit" and len(args_before) > 2 and args_before[2] == "worker":
                    opts = flags_map["server"]["submit"]
            return [opt for opt in opts if opt.startswith(current_token)]
        return []

    # If the user is completing values for flags:
    if len(args_before) >= 1:
        last_arg = args_before[-1]
        if last_arg in ["-s", "--stage", "--stage_names", "-stage_names", "--exclude-stage", "-xs"]:
            stages = get_stages() + ["all"]
            return [stg for stg in stages if stg.startswith(current_token)]
        if last_arg in ["-w", "--sweep", "--sweep_names", "-sweep_names", "--exclude-sweep", "-xw"]:
            sweeps = get_sweeps() + ["all"]
            return [swp for swp in sweeps if swp.startswith(current_token)]
        if last_arg in ["--profile"]:
            profiles = get_profiles()
            return [p for p in profiles if p.startswith(current_token)]

    # Sub-command completions
    if first_cmd in sub_options:
        opts = sub_options[first_cmd]
        if len(args_before) == 1:
            return [opt for opt in opts if opt.startswith(current_token)]

        sub_cmd = args_before[1]
        if first_cmd == "remote":
            if sub_cmd == "setup":
                if len(args_before) == 2:
                    return [r for r in get_remotes() if r.startswith(current_token)]
        elif first_cmd == "server":
            if sub_cmd == "submit":
                if len(args_before) == 2:
                    return [opt for opt in ["worker", "auto"] if opt.startswith(current_token)]
                elif len(args_before) == 3 and args_before[2] in ["worker", "auto"]:
                    return [r for r in get_remotes() if r.startswith(current_token)]
        elif (first_cmd == "print" and sub_cmd == "status") or (first_cmd == "status" and sub_cmd == "print"):
            if len(args_before) == 2:
                return [s for s in get_sweeps() + ["all"] if s.startswith(current_token)]
        elif (first_cmd == "reset" and sub_cmd == "sweep") or (first_cmd == "sweep" and sub_cmd == "reset"):
            if len(args_before) == 2:
                return [s for s in get_sweeps() if s.startswith(current_token)]

    # Positional completions for top-level commands
    if first_cmd == "collect":
        already_typed = set(args_before[1:])
        stages = get_stages() + ["all"]
        return [stg for stg in stages if stg.startswith(current_token) and stg not in already_typed]

    return []

def print_autocomplete_source(shell):
    if shell == "bash":
        print("""_workflow_completion() {
    local IFS=$'\\n'
    local response
    response=$(env COMP_WORDS="${COMP_WORDS[*]}" \\
                   COMP_CWORD="$COMP_CWORD" \\
                   _WORKFLOW_COMPLETE=bash_complete \\
                   "${COMP_WORDS[0]}")
    for completion in $response; do
        COMPREPLY+=( "$completion" )
    done
    return 0
}
complete -F _workflow_completion workflow""")
    elif shell == "zsh":
        print("""#compdef workflow
_workflow_completion() {
    local -a read_completions
    read_completions=("${(@f)$(env COMP_WORDS="${words[*]}" \\
                        COMP_CWORD="$((CURRENT - 1))" \\
                        _WORKFLOW_COMPLETE=bash_complete \\
                        workflow)}")
    compadd -a read_completions
}
compdef _workflow_completion workflow""")

def main_autocomplete(parsed_command, args):
    args, kwargs = parse_remaining(args)
    shell = args[0] if args else "bash"
    if shell not in ["bash", "zsh"]:
        raise ValueError("Supported shells: 'bash', 'zsh'")
    
    if shell == "bash":
        print("# Run this command to enable tab completion in Bash:")
        print('eval "$(_WORKFLOW_COMPLETE=bash_source workflow)"')
    elif shell == "zsh":
        print("# Run this command to enable tab completion in Zsh:")
        print('eval "$(_WORKFLOW_COMPLETE=zsh_source workflow)"')
    raise SystemExit

# --- CLI Action Handlers ---
def command_line_tool():
    setup_logging()
    try:
        workflow_command()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(1)

def workflow_command():
    # Handle autocompletion first if requested
    env_complete = os.environ.get("_WORKFLOW_COMPLETE")
    if env_complete:
        if env_complete in ["bash_source", "zsh_source"]:
            print_autocomplete_source(env_complete.split("_")[0])
            raise SystemExit
        elif env_complete == "bash_complete":
            comp_words_str = os.environ.get("COMP_WORDS", "")
            words = comp_words_str.split() if comp_words_str else []
            comp_cword = int(os.environ.get("COMP_CWORD", "0"))
            
            # Determine current token and previous arguments
            if comp_cword < len(words):
                current_token = words[comp_cword]
                args_before = words[1:comp_cword]
            else:
                current_token = ""
                args_before = words[1:]
                
            completions = get_completions(args_before, current_token)
            for c in completions:
                print(c)
            raise SystemExit

    main_precheck_options = ["init", "update", "autocomplete"]
    main_precheck_functions = [main_init, main_update, main_autocomplete]
    main_precheck_options = {main_precheck_options[i]: main_precheck_functions[i] 
                             for i in range(len(main_precheck_options))}
    if execute_option("main_option", main_precheck_options, required=False, parsed_command="workflow"):
        raise SystemExit

    from snap_workflow.utils.version import check_version
    check_version()
    
    main_options = ["submit", "add", "print", "set", "reset", "convert", "plot", "collect", "zip", "remove", "server", "remote", "stage", "sweep", "variable", "status", "spoint"]
    main_functions = [main_submit, main_add, main_print, main_set, main_reset, main_convert, main_plot, 
                      main_collect, main_zip, main_remove, main_server, main_remote,
                      main_stage, main_sweep, main_variable, main_status, main_spoint]
    main_options = {main_options[i]: main_functions[i] for i in range(len(main_options))}
    execute_option("main_option", main_options, parsed_command="workflow")

def main_init(parsed_command, args):
    args, kwargs = parse_remaining(args)
    from snap_workflow.core.workflow import check_existing_root
    try:
        check_existing_root()
    except ValueError as e:
        print(f"{e} Exiting.")
        raise SystemExit

    prompt = "Initialize system in current directory (y/n)? "
    collector = io.make_yes_no_collector(prompt)
    confirmation = collector.collect()
    if io.is_no(confirmation):
        print("System not initialized")
        raise SystemExit

    # Check and configure template format preference
    global_dir = GLOBAL_CONFIG_DIR
    global_config_file = os.path.join(global_dir, "config.json")
    default_format = None
    if os.path.isfile(global_config_file):
        try:
            with open(global_config_file, 'r') as f:
                default_format = json.load(f).get("default_format")
        except Exception:
            pass

    if not default_format:
        format_prompt = "Select default template configuration format (json/yaml) [json]: "
        format_collector = io.InputCollector(format_prompt, valid_options=["json", "yaml"], default="json")
        default_format = format_collector.collect()
        
        if default_format == "yaml":
            try:
                import yaml
            except ImportError:
                print("The 'pyyaml' package is required to use YAML templates. Please install it using 'pip install pyyaml' and try again.")
                raise SystemExit

        # Save preference
        os.makedirs(global_dir, exist_ok=True)
        config_data = {}
        if os.path.isfile(global_config_file):
            try:
                with open(global_config_file, 'r') as f:
                    config_data = json.load(f)
            except Exception:
                pass
        config_data["default_format"] = default_format
        with open(global_config_file, 'w') as f:
            json.dump(config_data, f, indent=4)

    initialize()
    raise SystemExit

def main_update(parsed_command, args):
    from snap_workflow.utils.version import update
    args, kwargs = parse_remaining(args)
    update(*args, **kwargs)
    raise SystemExit

def main_submit(parsed_command, args):
    args, kwargs = parse_remaining(args)
    test_submit = kwargs.pop("test", False)
    no_sbatch = kwargs.pop("no_sbatch", False)

    sweep_names = get_existing_sweep_name(kwargs, include_all=True, is_list=True, get_input=True, default="all")
    stage_names = get_existing_stage_name(kwargs, include_all=True, is_list=True, get_input=True, default="all")

    io.warn_unused_kwargs(kwargs)

    def num_submits_prompt():
        return int(input(f"How many times would you like to submit the above: "))

    submit_spoints(sweep_names=sweep_names, stage_names=stage_names, test_submit=test_submit, no_sbatch=no_sbatch, num_submits=num_submits_prompt)

def main_add(parsed_command, args):
    add_options = ["stage", "sweep", "variable"]
    add_functions = [add_stage_cmd, add_sweep_cmd, add_variable_cmd]
    add_options = {add_options[i]: add_functions[i] for i in range(len(add_options))}
    execute_option("add_option", add_options, parsed_command=parsed_command, args=args)

def add_stage_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    print("Getting stage info. Enter help at any time for options.")
    stage_name = get_new_stage_name(kwargs)
    sbatch_details = get_sbatch_details(stage_name)
    stage_variables = get_stage_variables(kwargs)
    stages_dict = load_stages()
    stage_dependencies = get_stage_dependencies(stages_dict, kwargs)

    add_stage(stage_name, sbatch_details, stage_variables, stage_dependencies)
    print(f"Stage {stage_name} created\n")

def add_sweep_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    sweep_name = get_new_sweep_name(kwargs)

    stage_inclusion_prompt = "For each stage, indicate whether to include in the sweep: (y/n)"
    include_stages = prompt_each_stage(stage_inclusion_prompt)

    from snap_workflow.core.domain.variables import load_variables
    variables = load_variables()
    print("Enter a list of values for each variable below.")
    variable_values = dict()
    for variable, types in variables.items():
        new_values = get_variable_values(variable, types)
        variable_values[variable] = new_values

    print(f"Creating sweep {sweep_name}.\n")
    add_sweep(sweep_name, include_stages, variable_values, overwrite=False)

def add_variable_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    new_var_name = get_new_variable_name(kwargs)
    new_var_types = get_new_variable_type(new_var_name, kwargs)

    add_to_stage_prompt = f"For each stage, indicate if {new_var_name} should be added:"
    add_to_stages = prompt_each_stage(add_to_stage_prompt)

    from snap_workflow.core.domain.sweeps import load_sweeps
    sweeps = load_sweeps()
    default_val = None
    if len(sweeps) > 0:
        default_val = get_new_var_val(new_var_name)

    add_variable(new_var_name, new_var_types, add_to_stages, default_val)

def main_print(parsed_command, args):
    print_options = ["status", "stages", "sweeps"]
    print_functions = [print_status_cmd, print_stages_cmd, print_sweeps_cmd]
    print_options = {print_options[i]: print_functions[i] for i in range(len(print_options))}
    execute_option("print_option", print_options, parsed_command=parsed_command, args=args)

def print_status_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    sweep_names = None
    if len(args) == 1:
        sweep_names = args[0]
    elif len(args) > 1:
        raise ValueError("Usage: 'workflow print status [sweep_name]'")

    if sweep_names is None:
        sweep_names = get_existing_sweep_name(kwargs, include_all=True, is_list=True, get_input=False, default="all")
    from snap_workflow.core.domain.sweeps import load_sweeps
    if sweep_names == "all":
        sweep_names = list(load_sweeps().keys())

    stage_names = get_existing_stage_name(kwargs, include_all=True, is_list=True, get_input=False, default="all")
    if stage_names == "all":
        stage_names = list(load_stages().keys())

    io.warn_unused_kwargs(kwargs)
    print_status(sweep_names, stage_names)

def print_stages_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    io.warn_unused_kwargs(kwargs)
    print_stages()

def print_sweeps_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    io.warn_unused_kwargs(kwargs)
    print_sweeps()

def main_set(parsed_command, args):
    set_options = ["status", "python"]
    set_functions = [set_status_cmd, set_python_cmd]
    set_options = {set_options[i]: set_functions[i] for i in range(len(set_options))}
    execute_option("set_option", set_options, parsed_command=parsed_command, args=args)

def set_status_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    if len(args) == 1:
        new_status = args[0]
        old_status = None
    elif len(args) == 2:
        old_status = args[0]
        new_status = args[1]
    else:
        raise ValueError("Usage 'workflow set status [from_status] to_status [-w sweep_names] [-s stage_names]'")

    sweep_names = get_existing_sweep_name(kwargs, include_all=True, is_list=True, get_input=True, default="all")
    stage_names = get_existing_stage_name(kwargs, include_all=True, is_list=True, get_input=True, default="all")
    io.warn_unused_kwargs(kwargs)

    set_status(new_status, old_status, sweep_names, stage_names)

def set_python_cmd(parsed_command, args):
    from snap_workflow.core.domain.stages import set_python_config
    args, kwargs = parse_remaining(args)
    python_path = args[0] if len(args) > 0 else None
    is_global = kwargs.pop("global", False) or kwargs.pop("g", False)
    stage_arg = get_csv_arg(kwargs, ["stage", "s"])

    if not is_global and not stage_arg:
        is_global = True

    stage_names = [x.strip() for x in stage_arg.split(",") if x.strip()] if stage_arg else []

    io.warn_unused_kwargs(kwargs)
    set_python_config(python_path=python_path, is_global=is_global, stage_names=stage_names)

def main_remove(parsed_command, args):
    remove_options = ["sweep"]
    remove_functions = [remove_sweep_cmd]
    remove_options = {remove_options[i]: remove_functions[i] for i in range(len(remove_options))}
    execute_option("remove_option", remove_options, parsed_command=parsed_command, args=args)

def remove_sweep_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    force = kwargs.pop("force", False) or kwargs.pop("f", False)
    hard = kwargs.pop("hard", False)
    if len(args) > 0 and "sweep" not in kwargs and "w" not in kwargs and "matrix" not in kwargs and "m" not in kwargs:
        kwargs["sweep"] = args[0]
    sweep_name = get_existing_sweep_name(kwargs, get_input=True)

    if not force:
        confirm_sweep_removal("sweep", sweep_name)
        if hard:
            confirm_hard_sweep_removal("sweep", sweep_name)

    remove_sweep(sweep_name, hard=hard)
    print(f"Removed sweep {sweep_name}")

def main_reset(parsed_command, args):
    reset_options = ["errors", "params", "spoint", "sweep"]
    reset_functions = [reset_errors_cmd, reset_params_cmd, reset_spoint_cmd, reset_sweep_cmd]
    reset_options = {reset_options[i]: reset_functions[i] for i in range(len(reset_options))}
    execute_option("reset_option", reset_options, parsed_command=parsed_command, args=args)

def reset_errors_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    if len(args) > 0 and "sweep" not in kwargs and "w" not in kwargs and "matrix" not in kwargs and "m" not in kwargs:
        kwargs["sweep"] = args[0]
    sweep_names = get_existing_sweep_name(kwargs, include_all=True, is_list=True, get_input=True, default="all")
    stage_names = get_existing_stage_name(kwargs, include_all=True, is_list=True, get_input=True, default="all")
    io.warn_unused_kwargs(kwargs)

    set_status("initialized", "error", sweep_names, stage_names)

def reset_params_cmd(parsed_command, args):
    from snap_workflow.core.params import set_params
    args, kwargs = parse_remaining(args)
    if len(args) > 0 and "sweep" not in kwargs and "w" not in kwargs and "matrix" not in kwargs and "m" not in kwargs:
        kwargs["sweep"] = args[0]
    sweep_names = get_existing_sweep_name(kwargs, include_all=True, is_list=True, get_input=True, default="all")
    stage_names = get_existing_stage_name(kwargs, include_all=True, is_list=True, get_input=True, default="all")
    io.warn_unused_kwargs(kwargs)

    set_params(sweep_name=sweep_names, stage_name=stage_names)

def reset_spoint_cmd(parsed_command, args):
    from snap_workflow.core.domain import spoints
    args, kwargs = parse_remaining(args)
    hard = kwargs.pop("hard", False)
    force = kwargs.pop("force", False) or kwargs.pop("f", False)
    io.warn_unused_kwargs(kwargs)

    cwd = os.getcwd()
    try:
        spoints.load_spoint(cwd)
    except Exception:
        print(f"Error: Current working directory '{cwd}' is not an SPoint directory.", file=sys.stderr)
        raise SystemExit(1)

    if hard and not force:
        prompt = f"Resetting SPoint with --hard will completely clear all files inside '{cwd}'.\n"
        prompt += f"Are you sure you want to reset this SPoint (y/n)? "
        collector = io.make_yes_no_collector(prompt)
        confirmation = collector.collect()
        if io.is_no(confirmation):
            print("SPoint reset cancelled.")
            raise SystemExit(0)

    try:
        spoints.reset_spoint(cwd, hard=hard)
        prefix = "Hard reset" if hard else "Reset"
        print(f"{prefix} SPoint in '{cwd}' successfully.")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(1)

def reset_sweep_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    force = kwargs.pop("force", False) or kwargs.pop("f", False)
    hard = kwargs.pop("hard", False)
    if len(args) > 0 and "sweep" not in kwargs and "w" not in kwargs and "matrix" not in kwargs and "m" not in kwargs:
        kwargs["sweep"] = args[0]
    sweep_name = get_existing_sweep_name(kwargs, get_input=True)
    io.warn_unused_kwargs(kwargs)

    if hard and not force:
        prompt = f"Resetting sweep {sweep_name} with --hard will completely clear all files inside its directories.\n"
        prompt += f"Are you sure you want to reset sweep {sweep_name} (y/n)? "
        collector = io.make_yes_no_collector(prompt)
        confirmation = collector.collect()
        if io.is_no(confirmation):
            print(f"Sweep {sweep_name} not reset")
            raise SystemExit

    reset_sweep(sweep_name, hard=hard)

def main_convert(parsed_command, args):
    convert_options = ["params"]
    convert_functions = [convert_params_cmd]
    convert_options = {convert_options[i]: convert_functions[i] for i in range(len(convert_options))}
    execute_option("convert_option", convert_options, parsed_command=parsed_command, args=args)

def convert_params_cmd(parsed_command, args):
    from snap_workflow.core.params import convert_params
    from snap_workflow.core.domain import spoints
    args, kwargs = parse_remaining(args)
    fmt = kwargs.pop("format", "json")
    
    cwd = os.getcwd()
    is_spoint_dir = False
    try:
        spoints.load_spoint(cwd)
        is_spoint_dir = True
    except Exception:
        is_spoint_dir = False

    if is_spoint_dir and "sweep" not in kwargs and "stage" not in kwargs and "w" not in kwargs and "s" not in kwargs:
        res = convert_params(spoint_dir=cwd, format=fmt)
        print(f"Converted parameter file for SPoint in {cwd} -> {res[0]}")
    else:
        sweep_names = get_existing_sweep_name(kwargs, include_all=True, is_list=True, get_input=False, default="all")
        stage_names = get_existing_stage_name(kwargs, include_all=True, is_list=True, get_input=False, default="all")
        io.warn_unused_kwargs(kwargs)
        res = convert_params(sweep_name=sweep_names, stage_name=stage_names, format=fmt)
        print(f"Converted parameter files for {len(res)} SPoint(s).")

def main_plot(parsed_command, args):
    pass

def main_collect(parsed_command, args):
    args, kwargs = parse_remaining(args)
    verbose_key, verbose = io.extract(kwargs, ["verbose", "v"])
    verbose = verbose is not None

    stages = load_stages()
    valid_stages = list(stages.keys())

    if len(args) > 0:
        stage_names = []
        for arg in args:
            if arg in valid_stages:
                stage_names.append(arg)
            elif arg == "all":
                stage_names = "all"
                break
            else:
                raise ValueError(f"'{arg}' is not a valid stage. Valid stages: {valid_stages}")
    else:
        stage_names = get_existing_stage_name(kwargs, include_all=True, is_list=True, get_input=False, default="all")

    io.warn_unused_kwargs(kwargs)
    collect_data(stage_names=stage_names, verbose=verbose)

def main_zip(parsed_command, args):
    args, kwargs = parse_remaining(args)
    usage_string = "Usage: 'workflow zip zip_name [--include_spoints] [-w sweep_name] [-s stage_name]'"
    if len(args) == 1:
        zip_name = args[0]
    else:
        raise ValueError(usage_string)

    from snap_workflow.core.domain.sweeps import load_sweeps
    sweeps = load_sweeps()
    sweep_names = get_existing_sweep_name(kwargs, include_all=True, is_list=True, get_input=False, default="all")
    if sweep_names == "all":
        sweep_names = list(sweeps.keys())

    stage_names = get_existing_stage_name(kwargs, include_all=True, is_list=True, get_input=False, default="all")
    if stage_names == "all":
        stage_names = list(load_stages().keys())

    include_spoints = kwargs.pop("include_spoints", False) or kwargs.pop("C", False)

    zip_workflow(zip_name, sweep_names, stage_names, include_spoints)

def execute_option(top_var, options, args=None, parsed_command=None, required=True):
    if parsed_command is None:
        parsed_command = ''

    parser = argparse.ArgumentParser()
    parser.add_argument(top_var, type=str, help=f"{options}")
    if args is None:
        args, extra_args = parser.parse_known_args()
    else:
        args, extra_args = parser.parse_known_args(args)

    val = vars(args)[top_var]
    if val is None:
        if required:
            raise ValueError(f"Missing required option for '{parsed_command} [{top_var}]'. Options: {list(options.keys())}")
        return False

    top = val.lower()
    if top in options:
        parsed_command += f" {top}"
        options[top](parsed_command, extra_args)
        return True
    elif required:
        raise ValueError(f"{top} not a valid option for '{parsed_command} [{top_var}]'. " +
                         f"Options include: {list(options.keys())}")
    else:
        return False

def parse_remaining(all_args):
    kwargs = dict()
    key = None
    val = []
    def assign_val():
        if key is None:
            kwargs["args"] = val
        else:
            if len(val) == 0:
                kwargs[key] = True
            elif len(val) == 1:
                kwargs[key] = val[0]
            else:
                kwargs[key] = val
    for i in range(len(all_args)):
        arg = all_args[i]
        if "-" == arg[0]:
            assign_val()
            val = []
            if '--' == arg[:2]:
                if "=" in arg:
                    arg, new_val = arg.split("=")
                    val.append(new_val)
                key = arg[2:]
            elif '-' == arg[:1]:
                key = arg[1:]
        else:
            val.append(arg)
    assign_val()
    return kwargs.pop("args"), kwargs

def load_global_remotes():
    from snap_workflow.utils.constants import GLOBAL_REMOTES_FILE, GLOBAL_CONFIG_DIR
    if not os.path.exists(GLOBAL_CONFIG_DIR):
        os.makedirs(GLOBAL_CONFIG_DIR, exist_ok=True)
    if os.path.isfile(GLOBAL_REMOTES_FILE):
        try:
            return io.load_json(GLOBAL_REMOTES_FILE, full_path=True)
        except Exception:
            pass
    return {}

def save_global_remotes(remotes):
    from snap_workflow.utils.constants import GLOBAL_REMOTES_FILE, GLOBAL_CONFIG_DIR
    if not os.path.exists(GLOBAL_CONFIG_DIR):
        os.makedirs(GLOBAL_CONFIG_DIR, exist_ok=True)
    io.save_json(GLOBAL_REMOTES_FILE, remotes, full_path=True)

def load_local_remotes():
    from snap_workflow.utils.constants import LOCAL_REMOTES_FILE
    if os.path.isfile(f".workflow/{LOCAL_REMOTES_FILE}"):
        try:
            return io.load_json(LOCAL_REMOTES_FILE)
        except Exception:
            pass
    return {}

def save_local_remotes(remotes):
    from snap_workflow.utils.constants import LOCAL_REMOTES_FILE
    io.save_json(LOCAL_REMOTES_FILE, remotes)

def main_server(parsed_command, args):
    server_options = ["start", "submit"]
    server_functions = [server_start_cmd, server_submit_cmd]
    server_options = {server_options[i]: server_functions[i] for i in range(len(server_options))}
    execute_option("server_option", server_options, parsed_command=parsed_command, args=args)

def server_start_cmd(parsed_command, args):
    from snap_workflow.server import run_server_foreground
    args, kwargs = parse_remaining(args)
    host = kwargs.pop("host", "127.0.0.1")
    port = int(kwargs.pop("port", "0"))
    io.warn_unused_kwargs(kwargs)
    run_server_foreground(host=host, port=port)

def server_submit_cmd(parsed_command, args):
    server_submit_options = ["worker", "auto"]
    server_submit_functions = [server_submit_worker_cmd, server_submit_auto_cmd]
    server_submit_options = {server_submit_options[i]: server_submit_functions[i] for i in range(len(server_submit_options))}
    execute_option("server_submit_option", server_submit_options, parsed_command=parsed_command, args=args)

def server_submit_auto_cmd(parsed_command, args):
    import json
    from snap_workflow.utils import io
    from snap_workflow.utils import path
    from snap_workflow.utils.constants import SERVER_INFO
    from snap_workflow.worker import send_request
    args, kwargs = parse_remaining(args)
    
    def get_csv_arg(kwargs, keys):
        for k in keys:
            val = kwargs.pop(k, None)
            if val is not None:
                if isinstance(val, list):
                    return ",".join(str(x) for x in val)
                return str(val)
        return ""

    stages = get_csv_arg(kwargs, ["stage", "s"])
    sweeps = get_csv_arg(kwargs, ["sweep", "w", "matrix", "m"])
    exclude_stages = get_csv_arg(kwargs, ["exclude-stage", "exclude_stage", "xs"])
    exclude_sweeps = get_csv_arg(kwargs, ["exclude-sweep", "exclude_sweep", "exclude-matrix", "exclude_matrix", "xw", "xm"])

    if len(args) != 1:
        raise ValueError("Usage: 'workflow server submit auto remote_name [--stage S] [--sweep W] [--exclude-stage XS] [--exclude-sweep XW]'")
    name = args[0]
    
    # 1. Enforce manager server pre-flight check
    if not os.path.isfile(SERVER_INFO):
        raise ValueError("Manager server is not running. Please start it using 'workflow server start'.")
        
    with open(SERVER_INFO, "r") as f:
        server_info = json.load(f)
        
    port = server_info["port"]
    token = server_info["token"]
    
    io.warn_unused_kwargs(kwargs)
    
    # 2. Make REST request to server POST /submit_auto
    url = f"http://127.0.0.1:{port}/submit_auto"
    payload = {
        "remote": name,
        "stages": stages,
        "sweeps": sweeps,
        "exclude_stages": exclude_stages,
        "exclude_sweeps": exclude_sweeps
    }
    
    resp = send_request(url, token, data=payload)
    if resp and resp.get("status") == "success":
        print(f"Successfully registered server-side auto-scheduler for remote '{name}'.")
        print("Server logs are written to '.workflow/server.log' and individual spoint output is captured in '<spoint_dir>/spoint.log'.")
    else:
        err = resp.get("message") if resp else "Connection error"
        print(f"Error: Failed to register auto-scheduler: {err}")

def server_submit_worker_cmd(parsed_command, args):
    from snap_workflow.utils.constants import SERVER_INFO
    from snap_workflow.worker import send_request
    from snap_workflow.worker import launch_remote_workers, launch_local_workers
    args, kwargs = parse_remaining(args)
    
    def get_csv_arg(kwargs, keys):
        for k in keys:
            val = kwargs.pop(k, None)
            if val is not None:
                if isinstance(val, list):
                    return ",".join(str(x) for x in val)
                return str(val)
        return ""

    stages = get_csv_arg(kwargs, ["stage", "s"])
    sweeps = get_csv_arg(kwargs, ["sweep", "w", "matrix", "m"])
    exclude_stages = get_csv_arg(kwargs, ["exclude-stage", "exclude_stage", "xs"])
    exclude_sweeps = get_csv_arg(kwargs, ["exclude-sweep", "exclude_sweep", "exclude-matrix", "exclude_matrix", "xw", "xm"])

    if len(args) != 2:
        raise ValueError("Usage: 'workflow server submit worker remote_name profile_name [--num-workers N] [--sbatch-args S] [--stage S] [--sweep W] [--exclude-stage XS] [--exclude-sweep XW]'")
    name = args[0]
    profile = args[1]
    
    # 1. Enforce manager server pre-flight check
    if not os.path.isfile(SERVER_INFO):
        raise ValueError("Manager server is not running. Please start it using 'workflow server start'.")
        
    # 2. Check the server queue for pending compatible tasks
    from snap_workflow.core.domain.sweeps import load_sweeps
    from snap_workflow.core.domain.stages import load_stages
    from snap_workflow.core.domain import status
    from snap_workflow.core.domain import spoints
    
    try:
        sweeps_dict = load_sweeps()
        stages_dict = load_stages()
        
        allowed_stages = {x.strip() for x in stages.split(",") if x.strip()}
        allowed_sweeps = {x.strip() for x in sweeps.split(",") if x.strip()}
        ex_stages = {x.strip() for x in exclude_stages.split(",") if x.strip()}
        ex_sweeps = {x.strip() for x in exclude_sweeps.split(",") if x.strip()}
        
        target_sweeps = list(sweeps_dict.keys())
        if allowed_sweeps:
            target_sweeps = [s for s in target_sweeps if s in allowed_sweeps]
        if ex_sweeps:
            target_sweeps = [s for s in target_sweeps if s not in ex_sweeps]
            
        target_stages = list(stages_dict.keys())
        if allowed_stages:
            target_stages = [s for s in target_stages if s in allowed_stages]
        if ex_stages:
            target_stages = [s for s in target_stages if s not in ex_stages]
            
        pending_count = 0
        for sweep_name, stage_name, spoint_dict in spoints.iter_spoints(sweep_names=target_sweeps, stage_names=target_stages):
            spoint_path = spoints.get_spoint_path(stage_name, spoint_dict)
            st = status.load_status(spoint_path)
            if st not in [status.COMPLETE, status.ERROR]:
                pending_count += 1
                
        if pending_count == 0:
            print("Warning: There are no pending/running compatible tasks left in the workflow.")
            print("Submitting this worker may result in immediate shutdown upon connecting.")
    except Exception as e:
        print(f"Warning: Pre-flight task queue check failed: {e}")

    num_workers = int(kwargs.pop("num-workers", kwargs.pop("num_workers", "1")))
    sbatch_args = kwargs.pop("sbatch-args", kwargs.pop("sbatch_args", ""))
    kwargs.pop("concurrency", None)
    kwargs.pop("profile", None)
    
    io.warn_unused_kwargs(kwargs)
    
    # 3. Make REST request to server POST /submit_worker
    from snap_workflow.worker import send_request
    with open(SERVER_INFO, "r") as f:
        server_info = json.load(f)
    port = server_info["port"]
    token = server_info["token"]
    
    url = f"http://127.0.0.1:{port}/submit_worker"
    payload = {
        "name": name,
        "profile": profile,
        "num_workers": num_workers,
        "sbatch_args": sbatch_args,
        "stages": stages,
        "sweeps": sweeps,
        "exclude_stages": exclude_stages,
        "exclude_sweeps": exclude_sweeps
    }
    
    resp = send_request(url, token, data=payload)
    if resp and resp.get("status") == "success":
        print(resp.get("message", f"Worker allocation for '{name}' submitted successfully."))
    else:
        err = resp.get("message") if resp else "Connection error"
        print(f"Error: Failed to submit worker: {err}")

def main_remote(parsed_command, args):
    remote_options = ["add", "setup"]
    remote_functions = [remote_add_cmd, remote_setup_cmd]
    remote_options = {remote_options[i]: remote_functions[i] for i in range(len(remote_options))}
    execute_option("remote_option", remote_options, parsed_command=parsed_command, args=args)

def remote_add_cmd(parsed_command, args):
    from snap_workflow.utils import io
    import subprocess
    args, kwargs = parse_remaining(args)
    if len(args) != 1:
        raise ValueError("Usage: 'workflow remote add name --host host_address'")
    name = args[0]
    host = kwargs.pop("host", None)
    if host is None:
        raise ValueError("Missing required keyword argument '--host'.")
    
    io.warn_unused_kwargs(kwargs)
    
    # Pre-flight SSH connection check
    check_cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", host, "echo ok"]
    try:
        res = subprocess.run(check_cmd, capture_output=True, text=True, check=True)
        if res.stdout.strip() != "ok":
            raise ValueError(f"SSH connection test to '{host}' failed.")
    except Exception as e:
        raise ValueError(f"Cannot connect to remote host '{host}' via SSH: {e}. Please verify hostname and credentials before registering the remote.")

    remotes = load_global_remotes()
    remotes[name] = {"host": host}
    save_global_remotes(remotes)
    print(f"Registered remote '{name}' globally with host {host}.")

def remote_setup_cmd(parsed_command, args):
    from snap_workflow.utils import io
    from snap_workflow.worker import send_request
    from snap_workflow.remote.setup import setup_remote_cluster
    args, kwargs = parse_remaining(args)
    if len(args) != 1:
        raise ValueError("Usage: 'workflow remote setup name [--path remote_path]'")
    name = args[0]
    
    # Load connection globally
    global_remotes = load_global_remotes()
    if name not in global_remotes:
        raise ValueError(f"Remote '{name}' is not registered globally. Register it first using 'workflow remote add'.")
    host = global_remotes[name]["host"]
    
    # Get local path mapping
    local_remotes = load_local_remotes()
    remote_path = kwargs.pop("path", None)
    if remote_path is not None:
        local_remotes[name] = {"path": remote_path}
        save_local_remotes(local_remotes)
        print(f"Updated local path for remote '{name}' to: {remote_path}")
    else:
        if name in local_remotes:
            remote_path = local_remotes[name]["path"]
        else:
            root_dir = path.get_root()
            dirname = os.path.basename(os.path.abspath(root_dir))
            remote_path = f"~/{dirname}"
            local_remotes[name] = {"path": remote_path}
            save_local_remotes(local_remotes)
            print(f"Initialized local path for remote '{name}' to default: {remote_path}")
            
    io.warn_unused_kwargs(kwargs)
    
    resolved_path = setup_remote_cluster(
        remote_host=host,
        remote_path=remote_path
    )
    if resolved_path != remote_path:
        local_remotes = load_local_remotes()
        local_remotes[name] = {"path": resolved_path}
        save_local_remotes(local_remotes)
        print(f"Automatically updated saved path config to: {resolved_path}")

def main_stage(parsed_command, args):
    stage_options = ["add", "print", "list"]
    stage_functions = [add_stage_cmd, print_stages_cmd, print_stages_cmd]
    stage_options = {stage_options[i]: stage_functions[i] for i in range(len(stage_options))}
    execute_option("stage_option", stage_options, parsed_command=parsed_command, args=args)

def main_sweep(parsed_command, args):
    sweep_options = ["add", "print", "list", "reset", "remove"]
    sweep_functions = [add_sweep_cmd, print_sweeps_cmd, print_sweeps_cmd, reset_sweep_cmd, remove_sweep_cmd]
    sweep_options = {sweep_options[i]: sweep_functions[i] for i in range(len(sweep_options))}
    execute_option("sweep_option", sweep_options, parsed_command=parsed_command, args=args)

def main_variable(parsed_command, args):
    variable_options = ["add"]
    variable_functions = [add_variable_cmd]
    variable_options = {variable_options[i]: variable_functions[i] for i in range(len(variable_options))}
    execute_option("variable_option", variable_options, parsed_command=parsed_command, args=args)

def main_status(parsed_command, args):
    status_options = ["print", "set"]
    status_functions = [print_status_cmd, set_status_cmd]
    status_options = {status_options[i]: status_functions[i] for i in range(len(status_options))}
    execute_option("status_option", status_options, parsed_command=parsed_command, args=args)

def main_spoint(parsed_command, args):
    spoint_options = ["reset", "submit"]
    spoint_functions = [reset_spoint_cmd, main_submit]
    spoint_options = {spoint_options[i]: spoint_functions[i] for i in range(len(spoint_options))}
    execute_option("spoint_option", spoint_options, parsed_command=parsed_command, args=args)

