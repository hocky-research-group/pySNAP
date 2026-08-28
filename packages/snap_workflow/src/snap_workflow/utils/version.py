import os
import sys
import numpy as np
from snap_workflow.utils.constants import *
from snap_workflow.utils import io, path

__version__ = "1.0.0"


def load_version():
    return io.load_json(VERSION)["version"]


def save_version(version):
    v = {"version": version}
    return io.save_json(VERSION, v)


def make_version():
    return io.make_json(VERSION)


def is_older_version(A, B):
    if A is None:
        return True
    A = np.array(A.split('.')).astype(int)
    B = np.array(B.split('.')).astype(int)
    if np.all(A == B):
        return False
    for i in range(3):
        if A[i] > B[i]:
            return False
        if A[i] < B[i]:
            return True

    raise Exception("Version comparison failed")


def check_version():
    path.get_root()
    version = __version__
    try:
        last_version = load_version()
    except Exception:
        last_version = None

    if is_older_version(last_version, version):
        raise Exception("Running an updated version of workflow. " +
                        "Please run 'workflow update' to update")

    elif is_older_version(version, last_version):
        raise Exception("Current workflow version is older than the last used workflow version. " +
                        f"Please update to at least version {last_version} to operate in this workflow.")


def update(**kwargs):
    io.warn_unused_kwargs(kwargs)

    path.get_root()
    version = __version__
    try:
        last_version = load_version()
    except Exception:
        last_version = None

    if last_version is None:
        make_version()

    save_version(version)
