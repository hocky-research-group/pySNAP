import os
from snap_workflow.utils import constants
from snap_workflow.utils import io as u_io


def load_global_remotes():
    """Loads globally configured remotes from ~/.config/snap_workflow/remotes.json."""
    if not os.path.exists(constants.GLOBAL_CONFIG_DIR):
        os.makedirs(constants.GLOBAL_CONFIG_DIR, exist_ok=True)
    if os.path.isfile(constants.GLOBAL_REMOTES_FILE):
        try:
            return u_io.load_json(constants.GLOBAL_REMOTES_FILE, full_path=True)
        except Exception:
            pass
    return {}


def save_global_remotes(remotes):
    """Saves global remote configurations to ~/.config/snap_workflow/remotes.json."""
    if not os.path.exists(constants.GLOBAL_CONFIG_DIR):
        os.makedirs(constants.GLOBAL_CONFIG_DIR, exist_ok=True)
    u_io.save_json(constants.GLOBAL_REMOTES_FILE, remotes, full_path=True)


def load_local_remotes():
    """Loads local workspace remote configurations from .workflow/remotes.json."""
    try:
        return u_io.load_json(constants.LOCAL_REMOTES_FILE)
    except Exception:
        return {}


def save_local_remotes(remotes):
    """Saves local workspace remote configurations to .workflow/remotes.json."""
    u_io.save_json(constants.LOCAL_REMOTES_FILE, remotes)
