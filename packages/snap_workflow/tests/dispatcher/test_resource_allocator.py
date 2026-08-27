import os
import pytest
from unittest.mock import patch
from snap_workflow.dispatcher.resource_allocator import ResourcePool


def test_resource_pool_init_defaults(monkeypatch):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    pool = ResourcePool(cpus_total=4, gpus_total=2)
    assert len(pool.all_cpus) == 4
    assert len(pool.all_gpus) <= 2
    assert pool.avail_cpus == set(pool.all_cpus)
    assert pool.avail_gpus == set(pool.all_gpus)


def test_resource_pool_acquire_and_release(monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0,1,2")
    pool = ResourcePool(cpus_total=4, gpus_total=3)
    
    cpus, gpus = pool.acquire(req_cpus=2, req_gpus=1)
    assert len(cpus) == 2
    assert len(gpus) == 1
    assert cpus == [0, 1]
    assert gpus == [0]
    assert len(pool.avail_cpus) == 2
    assert len(pool.avail_gpus) == 2

    pool.release(cpus, gpus)
    assert len(pool.avail_cpus) == 4
    assert len(pool.avail_gpus) == 3


def test_resource_pool_insufficient_cpus():
    pool = ResourcePool(cpus_total=2, gpus_total=0)
    with pytest.raises(ValueError, match="Insufficient CPUs available"):
        pool.acquire(req_cpus=4, req_gpus=0)


def test_resource_pool_insufficient_gpus(monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    pool = ResourcePool(cpus_total=4, gpus_total=1)
    with pytest.raises(ValueError, match="Insufficient GPUs available"):
        pool.acquire(req_cpus=1, req_gpus=2)


def test_resource_pool_explicit_device_pinning(monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "2,3")
    pool = ResourcePool(cpus_total=8, gpus_total=2)
    assert pool.all_gpus == [2, 3]

    cpus1, gpus1 = pool.acquire(req_cpus=4, req_gpus=1)
    assert gpus1 == [2]

    cpus2, gpus2 = pool.acquire(req_cpus=4, req_gpus=1)
    assert gpus2 == [3]

    pool.release(cpus1, gpus1)
    assert 2 in pool.avail_gpus
    assert 3 not in pool.avail_gpus


def test_resource_pool_cuda_none(monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "none")
    pool = ResourcePool(cpus_total=4, gpus_total=2)
    assert pool.all_gpus == []
    assert pool.avail_gpus == set()


def test_resource_pool_detect_gpus_fallback(monkeypatch):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    with patch("snap_workflow.dispatcher.runner.detect_system_resources", return_value=(8, 4, 32.0)):
        pool = ResourcePool(cpus_total=8, gpus_total=4)
        assert len(pool.all_gpus) == 4
        assert pool.all_gpus == [0, 1, 2, 3]


def test_resource_pool_sched_getaffinity_fallback():
    with patch("os.sched_getaffinity", side_effect=Exception("not supported")), \
         patch("os.cpu_count", return_value=6):
        pool = ResourcePool()
        assert len(pool.all_cpus) == 6
