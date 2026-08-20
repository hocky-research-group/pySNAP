import os
import pytest
from snap_workflow.worker.resource_allocator import ResourcePool


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


def test_resource_pool_insufficient_resources(monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    pool = ResourcePool(cpus_total=2, gpus_total=1)
    
    with pytest.raises(ValueError, match="Insufficient CPUs available"):
        pool.acquire(req_cpus=3, req_gpus=0)

    with pytest.raises(ValueError, match="Insufficient GPUs available"):
        pool.acquire(req_cpus=1, req_gpus=2)


def test_resource_pool_cuda_visible_devices_parsing(monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "2,5")
    pool = ResourcePool(cpus_total=4)
    assert pool.all_gpus == [2, 5]

    cpus, gpus = pool.acquire(req_cpus=1, req_gpus=2)
    assert gpus == [2, 5]
    assert len(pool.avail_gpus) == 0


def test_resource_pool_gpus_total_zero(monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0,1")
    pool = ResourcePool(cpus_total=2, gpus_total=0)
    assert pool.all_gpus == []
