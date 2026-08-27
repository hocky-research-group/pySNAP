import argparse
from snap_workflow.dispatcher.runner import dispatcher_loop
from snap_workflow.dispatcher.slurm import slurm_dispatcher_loop

def main():
    parser = argparse.ArgumentParser(description="SNAP Workflow Dispatcher Node")
    parser.add_argument("server_url", type=str, nargs="?", default=None, help="Server URL")
    parser.add_argument("token", type=str, nargs="?", default=None, help="Authentication token")
    parser.add_argument("--mode", type=str, default="subprocess", choices=["subprocess", "slurm"], help="Dispatcher execution mode")
    parser.add_argument("--cpus", type=int, default=None, help="Number of CPU cores (subprocess mode)")
    parser.add_argument("--gpus", type=int, default=None, help="Number of GPUs (subprocess mode)")
    parser.add_argument("--mem", type=float, default=None, help="RAM memory in GB (subprocess mode)")
    parser.add_argument("--max-jobs", type=int, default=50, help="Max queued jobs (slurm mode)")
    parser.add_argument("--stages", type=str, default="", help="Stages filter")
    parser.add_argument("--sweeps", type=str, default="", help="Sweeps filter")
    parser.add_argument("--exclude_stages", type=str, default="", help="Exclude stages filter")
    parser.add_argument("--exclude_sweeps", type=str, default="", help="Exclude sweeps filter")
    parser.add_argument("--host", type=str, default="local", help="Host identifier")
    parser.add_argument("--worker_id", type=str, default=None, help="Worker ID")
    parser.add_argument("--connect-timeout", type=float, default=300.0, help="Connection timeout in seconds")

    args = parser.parse_args()

    if args.mode == "slurm":
        slurm_dispatcher_loop(
            server_url=args.server_url,
            token=args.token,
            max_queued_jobs=args.max_jobs,
            stages=args.stages,
            sweeps=args.sweeps,
            exclude_stages=args.exclude_stages,
            exclude_sweeps=args.exclude_sweeps,
            host=args.host,
            connect_timeout=args.connect_timeout
        )
    else:
        dispatcher_loop(
            server_url=args.server_url,
            token=args.token,
            cpus_total=args.cpus,
            gpus_total=args.gpus,
            mem_total=args.mem,
            stages=args.stages,
            sweeps=args.sweeps,
            exclude_stages=args.exclude_stages,
            exclude_sweeps=args.exclude_sweeps,
            host=args.host,
            worker_id=args.worker_id,
            connect_timeout=args.connect_timeout
        )

if __name__ == "__main__":
    main()
