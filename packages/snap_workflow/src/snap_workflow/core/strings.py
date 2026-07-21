import os

CONFIG = ".config/workflow/config.json"
LOCAL_CONFIG = "config.json"
SPOINT_INFO = ".spoint_info"
COMBO_INFO = SPOINT_INFO
COMBO_VARS = "var.dat"
SPOINTS = "spoints"
COMBOS = SPOINTS
SWEEPS = "sweeps.json"
STAGES = "stages.json"
VARIABLES = "variables.json"
VERSION = "version.json"

STATUS = "status"
INITIALIZED = "initialized"
SUBMITTED = "submitted"
RUNNING = "running"
COMPLETE = "complete"
INCOMPLETE = "incomplete"
ERROR = "error"
WORKFLOW = "/.workflow/"

PROGRESS = "progress"
NONE = "None"

PARAMS = "params.pkl"
ALL_STATUS = [INITIALIZED,SUBMITTED,RUNNING,COMPLETE,INCOMPLETE,ERROR]

TIME = "spoint_time"
WORKERS = "workers.json"

CLUSTERS_FILE = ".workflow/clusters.json"
SERVER_INFO = ".workflow/server_info.json"
SERVER_LOG = ".workflow/server.log"

GLOBAL_CONFIG_DIR = os.path.expanduser("~/.snap_workflow")
GLOBAL_REMOTES_FILE = os.path.join(GLOBAL_CONFIG_DIR, "remotes.json")
LOCAL_REMOTES_FILE = "remotes.json"

