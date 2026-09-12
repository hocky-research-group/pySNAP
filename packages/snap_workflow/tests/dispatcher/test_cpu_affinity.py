"""CPU pinning must use cores this process is actually allowed to run on.

Under a batch scheduler the job's cgroup exposes an arbitrary subset of the node's
cores — cores 56-63 of a 64-core node, say — while the pool numbers its cores from
zero. Pinning to core 0 then fails, and with it the SPoint that was about to run.
"""

import os
import shutil

import pytest

from snap_workflow.dispatcher.resource_allocator import ResourcePool
from snap_workflow.dispatcher.runner import taskset_prefix


@pytest.fixture
def cgroup_cores(monkeypatch):
    """Pretend the scheduler gave this process cores 56-59 of a larger node."""
    cores = {56, 57, 58, 59}
    # raising=False: macOS has no sched_getaffinity, and these cases are about what
    # happens where it exists.
    monkeypatch.setattr(os, "sched_getaffinity", lambda pid: set(cores), raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/" + name)
    return sorted(cores)


class TestPoolCores:
    def test_pool_hands_out_cores_the_process_may_use(self, cgroup_cores):
        pool = ResourcePool(cpus_total=2, gpus_total=0)
        assert pool.all_cpus == [56, 57]

    def test_a_request_larger_than_the_allowance_stays_within_it(self, cgroup_cores):
        pool = ResourcePool(cpus_total=8, gpus_total=0)
        assert set(pool.all_cpus) <= set(cgroup_cores)

    def test_acquired_cores_are_usable(self, cgroup_cores):
        pool = ResourcePool(cpus_total=4, gpus_total=0)
        cpus, _ = pool.acquire(req_cpus=2, req_gpus=0)
        assert set(cpus) <= set(cgroup_cores)

    def test_numbering_from_zero_is_unchanged_where_that_is_allowed(self, monkeypatch):
        monkeypatch.setattr(os, "sched_getaffinity", lambda pid: {0, 1, 2, 3},
                            raising=False)
        pool = ResourcePool(cpus_total=2, gpus_total=0)
        assert pool.all_cpus == [0, 1]


class TestTasksetPrefix:
    def test_allowed_cores_are_pinned(self, cgroup_cores):
        assert taskset_prefix([56, 57]) == ["taskset", "-c", "56-57"]

    def test_disjoint_cores_are_listed_individually(self, cgroup_cores):
        assert taskset_prefix([56, 58]) == ["taskset", "-c", "56,58"]

    def test_cores_outside_the_allowance_are_not_pinned(self, cgroup_cores):
        """Better to run unpinned than to fail: taskset would refuse these."""
        assert taskset_prefix([0, 1]) == []

    def test_partially_allowed_cores_pin_only_what_is_allowed(self, cgroup_cores):
        assert taskset_prefix([57, 999]) == ["taskset", "-c", "57"]

    def test_no_cores_means_no_pinning(self, cgroup_cores):
        assert taskset_prefix([]) == []
