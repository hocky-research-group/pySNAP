from snap_workflow.utils import io
from snap_workflow.core.domain import variables as var_tools
from snap_workflow.cli.utils import parse_remaining, execute_option
from snap_workflow.cli.prompts import prompt_each_stage, get_variable_name, get_variable_type, get_default_val


def print_variable_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    var_name = kwargs.pop("v", kwargs.pop("var", kwargs.pop("variable", "all")))
    if len(args) > 0 and var_name == "all":
        var_name = args.pop(0)
    io.warn_unused_kwargs(kwargs)
    var_tools.print_variables(var_name)
    print("\n(For a list of all variable subcommands, run 'workflow variable help')")


def add_variable_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    if len(args) > 0 and "name" not in kwargs and "n" not in kwargs:
        kwargs["name"] = args.pop(0)
    name = get_variable_name(kwargs, args)
    var_type = get_variable_type(kwargs)

    add_to_stages = kwargs.pop("s", kwargs.pop("stages", None))
    if add_to_stages is not None and not isinstance(add_to_stages, list):
        add_to_stages = [add_to_stages]
    if add_to_stages is None:
        add_to_stages = prompt_each_stage(f"Add variable '{name}' to which stages?")

    default_val = get_default_val(kwargs, name, var_type)
    io.warn_unused_kwargs(kwargs)
    var_tools.add_variable(name, var_type, add_to_stages=add_to_stages, default_val=default_val)


def help_variable_cmd(parsed_command, args):
    print("Available subcommands for 'workflow variable':")
    print("  print [name] [-v V]               Print registered variables, types, and defaults")
    print("  add [name]                        Register a new variable (interactive wizard)")


def main_variable(parsed_command, args):
    if not args or args[0].startswith("-"):
        return print_variable_cmd(parsed_command, args)

    variable_options = {
        "print": print_variable_cmd,
        "add": add_variable_cmd,
        "help": help_variable_cmd,
        "--help": help_variable_cmd,
        "-h": help_variable_cmd,
    }
    execute_option("variable_option", variable_options, parsed_command=parsed_command, args=args)
