import os
import sys
import shutil
import subprocess
import importlib.util
import logging
from snap_workflow.utils import path, io
from snap_workflow.utils.constants import SPOINTS, SPOINT_INFO
from snap_workflow.utils.io import load_global_remotes, load_local_remotes
from snap_workflow.core.domain import spoints as spoint_tools
from snap_workflow.remote.ssh import get_control_path_args, ensure_remote_ssh_master

logger = logging.getLogger("snap_workflow.core.sync")

def get_auto_sync_patterns(stage_name):
    """Loads collect.py in isolation and returns the AUTO_SYNC glob list if defined."""
    root = path.get_root()
    collect_file = os.path.join(root, stage_name, "collect.py")
    if os.path.isfile(collect_file):
        try:
            # Load the module in isolation to avoid caching / pollution issues
            spec = importlib.util.spec_from_file_location(f"collect_sync_{stage_name}", collect_file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return getattr(module, "AUTO_SYNC", [])
        except Exception as e:
            logger.warning("Failed to load AUTO_SYNC from %s: %s", collect_file, e)
    return []

def measure_directory_size(remote, host, remote_path, spoint_rel_path):
    """Returns the size of the SPoint directory in bytes."""
    root = path.get_root()
    if remote == "local":
        local_dir = os.path.join(root, spoint_rel_path)
        if not os.path.isdir(local_dir):
            return 0
        total_size = 0
        for dirpath, _, filenames in os.walk(local_dir):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if os.path.exists(fp):
                    total_size += os.path.getsize(fp)
        return total_size
    else:
        # Measure remotely using ssh + du -sb
        target_path = f"{remote_path}/{spoint_rel_path}"
        try:
            cmd = ["ssh"] + get_control_path_args() + [host, f"du -sb {target_path}"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0 and res.stdout.strip():
                # Extract first token (the size in bytes)
                size_str = res.stdout.strip().split()[0]
                return int(size_str)
        except Exception as e:
            logger.warning("Failed to measure remote directory size for %s: %s", target_path, e)
        return 0

def pull_spoint_data(remote, host, remote_path, spoint_rel_path, stage_name, verbose=False):
    """Pulls only files matching the AUTO_SYNC patterns of the stage back to the local Hub."""
    if remote == "local":
        return

    patterns = get_auto_sync_patterns(stage_name)
    if not patterns:
        if verbose:
            logger.info("[SYNC] No AUTO_SYNC patterns defined for stage '%s'. Skipping pull.", stage_name)
        return

    root = path.get_root()
    local_dest = os.path.join(root, spoint_rel_path)
    os.makedirs(local_dest, exist_ok=True)

    rsync_flag = "-avz" if verbose else "-az"
    rsync_cmd = ["rsync", rsync_flag, "-e", "ssh " + " ".join(get_control_path_args())]
    rsync_cmd.append('--include=*/')
    for pat in patterns:
        rsync_cmd.append(f'--include={pat}')
    rsync_cmd.append('--exclude=*')

    source_uri = f"{host}:{remote_path}/{spoint_rel_path}/"
    rsync_cmd.extend([source_uri, f"{local_dest}/"])

    if verbose:
        logger.info("[SYNC] Pulling AUTO_SYNC files for %s: %s", spoint_rel_path, " ".join(rsync_cmd))
    try:
        subprocess.run(rsync_cmd, check=True, capture_output=not verbose)
    except subprocess.CalledProcessError as e:
        err_out = e.stderr.decode('utf-8', errors='replace') if e.stderr else str(e)
        logger.error("Failed to pull AUTO_SYNC files for %s: %s", spoint_rel_path, err_out)


def push_dependency_data(remote, host, remote_path, dep_spoint_rel_path, verbose=False):
    """Pushes local Hub directory of the dependency SPoint to the target Spoke."""
    if remote == "local":
        return

    root = path.get_root()
    local_src = os.path.join(root, dep_spoint_rel_path)
    if not os.path.isdir(local_src):
        logger.warning("Local dependency directory %s does not exist. Skipping push.", local_src)
        return

    parent_remote_dir = os.path.dirname(f"{remote_path}/{dep_spoint_rel_path}")
    try:
        ssh_cmd = ["ssh"] + get_control_path_args() + [host, f"mkdir -p {parent_remote_dir}"]
        subprocess.run(ssh_cmd, check=True, timeout=10, capture_output=not verbose)
    except Exception as e:
        logger.error("Failed to create remote parent directory %s: %s", parent_remote_dir, e)
        return

    dest_uri = f"{host}:{remote_path}/{dep_spoint_rel_path}/"
    rsync_flag = "-avz" if verbose else "-az"
    rsync_cmd = [
        "rsync", rsync_flag,
        "-e", "ssh " + " ".join(get_control_path_args()),
        f"{local_src}/", dest_uri
    ]
    if verbose:
        logger.info("[SYNC] Pushing dependency data for %s: %s", dep_spoint_rel_path, " ".join(rsync_cmd))
    try:
        subprocess.run(rsync_cmd, check=True, capture_output=not verbose)
    except subprocess.CalledProcessError as e:
        err_out = e.stderr.decode('utf-8', errors='replace') if e.stderr else str(e)
        logger.error("Failed to push dependency data for %s: %s", dep_spoint_rel_path, err_out)


def transit_sync_dependency(source_remote, source_host, source_path, dest_remote, dest_host, dest_path, dep_rel_path, stage_name, verbose=False):
    """Performs transient transit sync of dependency (pull all, push all, delete from Hub, restore AUTO_SYNC)."""
    root = path.get_root()
    if source_remote != "local" and dest_remote != "local":
        local_temp = os.path.join(root, ".workflow", "tmp", "sync", dep_rel_path)
    else:
        local_temp = os.path.join(root, dep_rel_path)

    rsync_flag = "-avz" if verbose else "-az"

    if source_remote != "local":
        os.makedirs(local_temp, exist_ok=True)
        source_uri = f"{source_host}:{source_path}/{dep_rel_path}/"
        pull_cmd = [
            "rsync", rsync_flag,
            "-e", "ssh " + " ".join(get_control_path_args()),
            source_uri, f"{local_temp}/"
        ]
        if verbose:
            logger.info("[SYNC] Transit pull: %s", " ".join(pull_cmd))
        try:
            subprocess.run(pull_cmd, check=True, capture_output=not verbose)
        except subprocess.CalledProcessError as e:
            err_out = e.stderr.decode('utf-8', errors='replace') if e.stderr else str(e)
            logger.error("Failed transit pull for %s: %s", dep_rel_path, err_out)
            return

    if dest_remote != "local":
        parent_remote_dir = os.path.dirname(f"{dest_path}/{dep_rel_path}")
        try:
            subprocess.run(["ssh"] + get_control_path_args() + [dest_host, f"mkdir -p {parent_remote_dir}"], check=True, timeout=10, capture_output=not verbose)
        except Exception as e:
            logger.error("Failed transit remote mkdir %s: %s", parent_remote_dir, e)
            return

        dest_uri = f"{dest_host}:{dest_path}/{dep_rel_path}/"
        push_cmd = [
            "rsync", rsync_flag,
            "-e", "ssh " + " ".join(get_control_path_args()),
            f"{local_temp}/", dest_uri
        ]
        if verbose:
            logger.info("[SYNC] Transit push: %s", " ".join(push_cmd))
        try:
            subprocess.run(push_cmd, check=True, capture_output=not verbose)
        except subprocess.CalledProcessError as e:
            err_out = e.stderr.decode('utf-8', errors='replace') if e.stderr else str(e)
            logger.error("Failed transit push for %s: %s", dep_rel_path, err_out)
            return

    if source_remote != "local" and dest_remote != "local":
        if verbose:
            logger.info("[SYNC] Cleaning up transient local directory: %s", local_temp)
        shutil.rmtree(local_temp, ignore_errors=True)
        pull_spoint_data(source_remote, source_host, source_path, dep_rel_path, stage_name, verbose=verbose)


def pull_worker_logs(remote_type, host, remote_path, verbose=False):
    """Pulls all worker logs from the remote Spoke back to the local Hub's workers/logs directory."""
    if remote_type == "local":
        return

    root = path.get_root()
    local_dest = os.path.join(root, "workers", "logs")
    os.makedirs(local_dest, exist_ok=True)

    rsync_flag = "-avz" if verbose else "-az"
    rsync_cmd = [
        "rsync", rsync_flag,
        "-e", "ssh " + " ".join(get_control_path_args()),
        f"{host}:{remote_path}/workers/logs/", f"{local_dest}/"
    ]
    if verbose:
        logger.info("[SYNC] Pulling worker logs: %s", " ".join(rsync_cmd))
    try:
        subprocess.run(rsync_cmd, check=True, capture_output=not verbose)
    except Exception as e:
        logger.error("Failed to pull worker logs: %s", e)


def push_workflow_structure(remote_name_or_host, remote_path=None, verbose=False):
    """Pushes the complete workflow directory structure (including .workflow, params, and SPoint metadata) to remote, excluding simulation output binaries."""
    if not remote_name_or_host or remote_name_or_host == "local":
        return

    g_remotes = load_global_remotes()
    l_remotes = load_local_remotes()

    host = remote_name_or_host
    if remote_name_or_host in l_remotes:
        host = l_remotes[remote_name_or_host].get("host", host)
        if remote_path is None:
            remote_path = l_remotes[remote_name_or_host].get("path")
    if remote_name_or_host in g_remotes:
        if remote_name_or_host not in l_remotes or "host" not in l_remotes[remote_name_or_host]:
            host = g_remotes[remote_name_or_host].get("host", host)
        if remote_path is None:
            remote_path = g_remotes[remote_name_or_host].get("path")

    if not remote_path:
        root_dir = path.get_root()
        dirname = os.path.basename(os.path.abspath(root_dir))
        remote_path = f"~/{dirname}"

    ensure_remote_ssh_master(host)
    root = path.get_root()
    dest_uri = f"{host}:{remote_path}/"
    rsync_flag = "-avz" if verbose else "-az"
    rsync_cmd = [
        "rsync", rsync_flag,
        "-e", "ssh " + " ".join(get_control_path_args()),
        "--exclude", "*.gsd",
        "--exclude", "*.npy",
        "--exclude", "*.npz",
        "--exclude", "*.log",
        "--exclude", "*.tar.gz",
        "--exclude", "*.zip",
        "--exclude", ".git/",
        "--exclude", "slurm_out/",
        "--exclude", "temp/",
        "--exclude", "__pycache__/",
        "--exclude", "**/env.json",
        "--exclude", "**/env.yaml",
        "--exclude", "**/env.yml",
        "--exclude", ".workflow/config.json",
        "--exclude", "workers/logs/",
        f"{root}/", dest_uri
    ]
    if verbose:
        logger.info("[SYNC] Pushing full workflow structure to %s: %s", host, " ".join(rsync_cmd))
    try:
        subprocess.run(rsync_cmd, check=True, capture_output=not verbose)
    except subprocess.CalledProcessError as e:
        err_out = e.stderr.decode('utf-8', errors='replace') if e.stderr else str(e)
        logger.error("Failed to push workflow structure to %s: %s", host, err_out)
        raise


def pull_spoint_statuses(host, remote_path, stages=None, sweeps=None, verbose=False):
    """Pulls SPoint info and status files from remote to local."""
    try:
        ensure_remote_ssh_master(host)
    except Exception as e:
        logger.warning("Could not establish SSH master connection for status pull: %s", e)

    root = path.get_root()
    rsync_flag = "-avz" if verbose else "-az"
    for sweep_name, stage_name, spoint_dict in spoint_tools.iter_spoints(sweeps, stages):
        spoint_rel_path = spoint_tools.get_spoint_string(spoint_dict)
        rel_spoint_dir = os.path.join(stage_name, SPOINTS, spoint_rel_path)

        remote_info_dir = f"{host}:{remote_path}/{rel_spoint_dir}/{SPOINT_INFO}/"
        local_info_dir = os.path.join(root, rel_spoint_dir, SPOINT_INFO)
        os.makedirs(local_info_dir, exist_ok=True)

        rsync_cmd = [
            "rsync", rsync_flag,
            "-e", "ssh " + " ".join(get_control_path_args()),
            remote_info_dir, f"{local_info_dir}/"
        ]
        try:
            subprocess.run(rsync_cmd, check=True, capture_output=not verbose)
        except Exception as e:
            logger.debug("Failed to pull spoint info for %s: %s", rel_spoint_dir, e)

        pull_spoint_data("remote", host, remote_path, os.path.join(stage_name, SPOINTS, spoint_rel_path), stage_name, verbose=verbose)


def sync_remote(remote_name_or_host, direction="push", stages=None, sweeps=None, verbose=False):
    """Syncs workflow structure, SPoints, worker logs, or statuses between local and remote."""
    if not remote_name_or_host or remote_name_or_host == "local":
        print("Remote is 'local'. Nothing to sync.")
        return

    g_remotes = load_global_remotes()
    l_remotes = load_local_remotes()
    r_info = l_remotes.get(remote_name_or_host) or g_remotes.get(remote_name_or_host)
    if not r_info:
        raise ValueError(f"Remote '{remote_name_or_host}' is not registered.")

    host = r_info.get("host", remote_name_or_host)
    remote_path = l_remotes.get(remote_name_or_host, {}).get("path") or g_remotes.get(remote_name_or_host, {}).get("path")

    if not remote_path:
        root_dir = path.get_root()
        dirname = os.path.basename(os.path.abspath(root_dir))
        remote_path = f"~/{dirname}"

    print(f"Syncing with remote '{remote_name_or_host}' ({host}:{remote_path}) [direction={direction}]...")

    if direction in ["push", "both", "all", "sync"]:
        push_workflow_structure(remote_name_or_host, remote_path=remote_path, verbose=verbose)
        print(f"Pushed workflow structure and parameters to '{remote_name_or_host}' ({host}:{remote_path}).")

    if direction in ["pull", "both", "all"]:
        pull_worker_logs("remote", host, remote_path, verbose=verbose)
        pull_spoint_statuses(host, remote_path, stages=stages, sweeps=sweeps, verbose=verbose)
        print(f"Pulled status, worker logs, and data from '{remote_name_or_host}' ({host}:{remote_path}).")

