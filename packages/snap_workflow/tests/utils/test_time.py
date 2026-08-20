import os
import pytest
import numpy as np
from snap_workflow.utils import time
from snap_workflow.utils.constants import SPOINT_INFO, TIME


def test_write_and_load_time(tmp_path):
    spoint_dir = str(tmp_path)
    os.makedirs(os.path.join(spoint_dir, SPOINT_INFO), exist_ok=True)

    assert not time.is_time(spoint_dir)
    
    # load_time when no time file exists creates an empty file
    t_empty = time.load_time(spoint_dir)
    assert t_empty == []
    assert time.is_time(spoint_dir)

    # return_recent on empty list returns np.nan
    rec_empty = time.load_time(spoint_dir, return_recent=True)
    assert np.isnan(rec_empty)

    # Write times
    time.write_time([1.5, 2.5, 3.0], spoint_dir)

    loaded = time.load_time(spoint_dir)
    assert loaded == [1.5, 2.5, 3.0]

    sum_t = time.load_time(spoint_dir, sum=True)
    assert sum_t == 7.0

    recent_t = time.load_time(spoint_dir, return_recent=True)
    assert recent_t == 3.0
