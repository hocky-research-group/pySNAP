import json
from snap_workflow.utils import io
from snap_workflow import server
from snap_workflow.cli.utils import parse_remaining, execute_option


def main_server(parsed_command, args):
    server_options = {
        "start": server_start_cmd,
        "status": server_status_cmd,
        "auto": server_auto_cmd,
        "autoschedule": server_auto_cmd,
        "reserve": server_reserve_cmd,
        "stop": server_stop_cmd,
        "shutdown": server_shutdown_cmd
    }
    execute_option("server_option", server_options, parsed_command=parsed_command, args=args)


def server_start_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    port = int(kwargs.pop("port", 8080))
    host = kwargs.pop("host", "0.0.0.0")
    debug = kwargs.pop("debug", False)
    if isinstance(debug, str):
        debug = debug.lower() in ("true", "1", "yes", "")
    elif debug is not False:
        debug = True
    io.warn_unused_kwargs(kwargs)
    server.run_server_foreground(host=host, port=port, debug=debug)


def server_status_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    res = server.get_server_status()
    print(json.dumps(res, indent=2))
    io.warn_unused_kwargs(kwargs)


def server_auto_cmd(parsed_command, args):
    from snap_workflow.cli.remote import remote_auto_cmd
    remote_auto_cmd(parsed_command, args)


def server_reserve_cmd(parsed_command, args):
    from snap_workflow.cli.remote import remote_reserve_cmd
    remote_reserve_cmd(parsed_command, args)


def server_stop_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    print("Notice: Dispatchers are decoupled standalone processes. To terminate all server tasks, run 'workflow server shutdown'.")
    io.warn_unused_kwargs(kwargs)


def server_shutdown_cmd(parsed_command, args):
    args, kwargs = parse_remaining(args)
    res = server.shutdown_server()
    msg = res.get("message", "Workflow server shutting down...") if isinstance(res, dict) else "Workflow server shutting down..."
    print(msg)
    io.warn_unused_kwargs(kwargs)
