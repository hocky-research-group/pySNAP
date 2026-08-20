from snap_workflow.utils import io
from snap_workflow.core.domain import variables as var_tools
from snap_workflow.cli.utils import parse_remaining, execute_option
from snap_workflow.cli.prompts import prompt_each_stage, get_values


def main_variable(parsed_command, args):
    variable_options = {
        "add": add_variable_cmd,
        "print": print_variable_cmd,
        "list": print_variable_cmd,
    }
    execute_option("variable_option", variable_options, parsed_command=parsed_command, args=args)


def print_variable_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    var_name = kwargs.pop("v", kwargs.pop("var", kwargs.pop("variable", "all")))
    if len(args) > 0 and var_name == "all":
        var_name = args.pop(0)
    io.warn_unused_kwargs(kwargs)
    var_tools.print_variables(var_name)


def add_variable_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    name = kwargs.pop("n", kwargs.pop("name", None))
    if name is None:
        if len(args) > 0:
            name = args.pop(0)
        else:
            raise ValueError("Must provide variable name")
    var_type = kwargs.pop("t", kwargs.pop("type", None))
    if var_type is not None and not isinstance(var_type, list):
        var_type = [var_type]
    add_to_stages = kwargs.pop("s", kwargs.pop("stages", None))
    if add_to_stages is not None and not isinstance(add_to_stages, list):
        add_to_stages = [add_to_stages]
    if add_to_stages is None:
        add_to_stages = prompt_each_stage("Add variable to which stages?")
    default_val = kwargs.pop("d", kwargs.pop("default", None))
    has_values = any(k in kwargs for k in ["value", "v", "Value", "V", "values", "Values"])
    values = get_values(kwargs, var=name, types=var_type, is_list=True) if has_values else None
    io.warn_unused_kwargs(kwargs)
    var_tools.add_variable(name, values, add_to_stages=add_to_stages, default_val=default_val)
