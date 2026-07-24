import os
import sys
import shutil
import subprocess
import importlib.util
import logging
from snap_workflow.utils import path, io

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
            cmd = ["ssh", host, f"du -sb {target_path}"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0 and res.stdout.strip():
                # Extract first token (the size in bytes)
                size_str = res.stdout.strip().split()[0]
                return int(size_str)
        except Exception as e:
            logger.warning("Failed to measure remote directory size for %s: %s", target_path, e)
        return 0

def pull_spoint_data(remote, host, remote_path, spoint_rel_path, stage_name):
    """Pulls only files matching the AUTO_SYNC patterns of the stage back to the local Hub."""
    if remote == "local":
        return

    patterns = get_auto_sync_patterns(stage_name)
    if not patterns:
        logger.info("No AUTO_SYNC patterns defined for stage '%s'. Skipping pull.", stage_name)
        return

    root = path.get_root()
    local_dest = os.path.join(root, spoint_rel_path)
    os.makedirs(local_dest, exist_ok=True)

    # Build rsync command with include/exclude glob filters
    # Format: rsync -avz --include="*/" --include="pat1" ... --exclude="*" host:source/ dest/
    rsync_cmd = ["rsync", "-avz"]
    # Allow directory traversal so includes are matched nested
    rsync_cmd.append('--include=*/')
    for pat in patterns:
        rsync_cmd.append(f'--include={pat}')
    rsync_cmd.append('--exclude=*')

    # Ensure trailing slash on source to copy contents
    source_uri = f"{host}:{remote_path}/{spoint_rel_path}/"
    rsync_cmd.extend([source_uri, f"{local_dest}/"])

    logger.info("Pulling AUTO_SYNC files for %s: %s", spoint_rel_path, " ".join(rsync_cmd))
    try:
        subprocess.run(rsync_cmd, check=True)
    except subprocess.CalledProcessError as e:
        logger.error("Failed to pull AUTO_SYNC files for %s: %s", spoint_rel_path, e)

def push_dependency_data(remote, host, remote_path, dep_spoint_rel_path):
    """Pushes local Hub directory of the dependency SPoint to the target Spoke."""
    if remote == "local":
        return

    root = path.get_root()
    local_src = os.path.join(root, dep_spoint_rel_path)
    if not os.path.isdir(local_src):
        logger.warning("Local dependency directory %s does not exist. Skipping push.", local_src)
        return

    # Ensure remote parent directory exists
    parent_remote_dir = os.path.dirname(f"{remote_path}/{dep_spoint_rel_path}")
    try:
        subprocess.run(["ssh", host, f"mkdir -p {parent_remote_dir}"], check=True, timeout=10)
    except Exception as e:
        logger.error("Failed to create remote parent directory %s: %s", parent_remote_dir, e)
        return

    dest_uri = f"{host}:{remote_path}/{dep_spoint_rel_path}/"
    rsync_cmd = ["rsync", "-avz", f"{local_src}/", dest_uri]
    logger.info("Pushing dependency data for %s: %s", dep_spoint_rel_path, " ".join(rsync_cmd))
    try:
        subprocess.run(rsync_cmd, check=True)
    except subprocess.CalledProcessError as e:
        logger.error("Failed to push dependency data for %s: %s", dep_spoint_rel_path, e)

def transit_sync_dependency(source_remote, source_host, source_path, dest_remote, dest_host, dest_path, dep_rel_path, stage_name):
    """Performs transient transit sync of dependency (pull all, push all, delete from Hub, restore AUTO_SYNC)."""
    root = path.get_root()
    if source_remote != "local" and dest_remote != "local":
        local_temp = os.path.join(root, ".workflow", "tmp", "sync", dep_rel_path)
    else:
        local_temp = os.path.join(root, dep_rel_path)

    # Step 1: Pull full dependency from source to local Hub (if source is remote)
    if source_remote != "local":
        os.makedirs(local_temp, exist_ok=True)
        source_uri = f"{source_host}:{source_path}/{dep_rel_path}/"
        pull_cmd = ["rsync", "-avz", source_uri, f"{local_temp}/"]
        logger.info("Transit pull: %s", " ".join(pull_cmd))
        try:
            subprocess.run(pull_cmd, check=True)
        except subprocess.CalledProcessError as e:
            logger.error("Failed transit pull for %s: %s", dep_rel_path, e)
            return

    # Step 2: Push full dependency from local Hub to destination (if destination is remote)
    if dest_remote != "local":
        # Ensure remote parent directory exists
        parent_remote_dir = os.path.dirname(f"{dest_path}/{dep_rel_path}")
        try:
            subprocess.run(["ssh", dest_host, f"mkdir -p {parent_remote_dir}"], check=True, timeout=10)
        except Exception as e:
            logger.error("Failed transit remote mkdir %s: %s", parent_remote_dir, e)
            return

        dest_uri = f"{dest_host}:{dest_path}/{dep_rel_path}/"
        push_cmd = ["rsync", "-avz", f"{local_temp}/", dest_uri]
        logger.info("Transit push: %s", " ".join(push_cmd))
        try:
            subprocess.run(push_cmd, check=True)
        except subprocess.CalledProcessError as e:
            logger.error("Failed transit push for %s: %s", dep_rel_path, e)
            return

    # Step 3: Clean up full folder from local Hub (if either end was remote)
    # Note: If destination was local, we keep it because the user explicitly ran it locally.
    if source_remote != "local" and dest_remote != "local":
        logger.info("Cleaning up transient local directory: %s", local_temp)
        shutil.rmtree(local_temp, ignore_errors=True)

        # Step 4: Restore only the AUTO_SYNC subset to local Hub
        pull_spoint_data(source_remote, source_host, source_path, dep_rel_path, stage_name)

def pull_worker_logs(remote_type, host, remote_path):
    """Pulls all worker logs from the remote Spoke back to the local Hub's worker_logs directory."""
    if remote_type == "local":
        return

    root = path.get_root()
    local_dest = os.path.join(root, "worker_logs")
    os.makedirs(local_dest, exist_ok=True)

    rsync_cmd = ["rsync", "-avz", f"{host}:{remote_path}/worker_logs/", f"{local_dest}/"]
    logger.info("Pulling worker logs: %s", " ".join(rsync_cmd))
    try:
        subprocess.run(rsync_cmd, check=True)
    except Exception as e:
        logger.error("Failed to pull worker logs: %s", e)
