from snap_workflow.utils import io
from snap_workflow.core import data as data_tools
from snap_workflow.cli.utils import parse_remaining, execute_option
from snap_workflow.cli.prompts import get_existing_sweep_name, get_existing_stage_name


def main_data(parsed_command, args):
    data_options = {"collect": collect_data_cmd}
    execute_option('data_option', data_options, parsed_command=parsed_command, args=args)


def collect_data_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    if len(args) > 0 and "s" not in kwargs and "stage" not in kwargs and "stages" not in kwargs:
        kwargs["s"] = list(args)
    sweep_name = get_existing_sweep_name(kwargs, include_all=True, get_input=False, default='all')
    try:
        stage_name = get_existing_stage_name(kwargs, include_all=True, is_list=True, get_input=False, default=['all'])
    except Exception as e:
        raise ValueError(str(e))
    if isinstance(stage_name, list) and len(stage_name) == 1 and stage_name[0] == 'all':
        stage_name = 'all'

    io.warn_unused_kwargs(kwargs)
    if sweep_name == 'all':
        data_tools.collect_data(stage_names=stage_name, verbose=False)
    else:
        data_tools.collect_data(sweep_name, stage_name)
