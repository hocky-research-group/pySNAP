import sys
import os
import numpy as np
from .strings import *

def write_time(times, spoint_dir="."):
    with open(os.path.join(spoint_dir, SPOINT_INFO, TIME), 'w') as file:
        for t in times:
            file.write(str(t) + "\n")

def load_time(spoint_dir=".", sum=False, return_recent=False):
    times = []
    if not is_time(spoint_dir):
        write_time([], spoint_dir)
    with open(os.path.join(spoint_dir, SPOINT_INFO, TIME), 'r') as file:
        for line in file.readlines():
            line = line.strip()
            t = float(line)
            times.append(t)
    if sum:
        return np.sum(times)
    elif return_recent:
        if len(times) == 0:
            return np.nan
        return times[-1]
    else:
        return times

def is_time(spoint_dir="."):
    return os.path.isfile(os.path.join(spoint_dir, SPOINT_INFO, TIME))

