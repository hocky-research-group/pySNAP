from snap_workflow.utils import io
from snap_workflow.core.params import params as param_tools
from snap_workflow.cli.utils import parse_remaining, execute_option, get_data_format


def convert_params_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    data_format = get_data_format(kwargs)
    io.warn_unused_kwargs(kwargs)
    param_tools.convert_params(format=data_format)


def set_params_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    data_format = get_data_format(kwargs)
    io.warn_unused_kwargs(kwargs)
    param_tools.set_default_format(data_format)


def main_params(parsed_command, args):
    param_options = {
        "set": set_params_cmd,
        "convert": convert_params_cmd,
    }
    execute_option("params_option", param_options, parsed_command=parsed_command, args=args)
