import math
import pytest
from snap_simulate.hoomd.simulation import _resolve_dybond_rates

def test_rate_resolution_kon_koff():
    kon, koff = _resolve_dybond_rates("spec1", {"kon": 10.0, "koff": 1.0}, dt_check=0.01)
    assert math.isclose(kon, 10.0)
    assert math.isclose(koff, 1.0)

def test_rate_resolution_kon_epsilon():
    # epsilon = 2.0 -> koff = kon * exp(-2.0) = 10 * exp(-2)
    kon, koff = _resolve_dybond_rates("spec1", {"kon": 10.0, "epsilon": 2.0}, dt_check=0.01)
    assert math.isclose(kon, 10.0)
    assert math.isclose(koff, 10.0 * math.exp(-2.0))

def test_rate_resolution_pon_epsilon():
    # Pon = 0.1, dt_check = 0.01 -> kon = 0.1 / 0.01 = 10.0
    # epsilon = 2.0 -> koff = 10.0 * exp(-2.0)
    kon, koff = _resolve_dybond_rates("spec1", {"Pon": 0.1, "epsilon": 2.0}, dt_check=0.01)
    assert math.isclose(kon, 10.0)
    assert math.isclose(koff, 10.0 * math.exp(-2.0))

def test_rate_resolution_pon_koff():
    # Pon = 0.2, dt_check = 0.005 -> kon = 0.2 / 0.005 = 40.0
    kon, koff = _resolve_dybond_rates("spec1", {"Pon": 0.2, "koff": 2.0}, dt_check=0.005)
    assert math.isclose(kon, 40.0)
    assert math.isclose(koff, 2.0)

def test_rate_resolution_koff_epsilon():
    # koff = 0.5, epsilon = 3.0 -> kon = 0.5 * exp(3.0)
    kon, koff = _resolve_dybond_rates("spec1", {"koff": 0.5, "epsilon": 3.0}, dt_check=0.01)
    assert math.isclose(koff, 0.5)
    assert math.isclose(kon, 0.5 * math.exp(3.0))

def test_rate_resolution_epsilon_defaults():
    # epsilon = 2.0, default kon = 1000.0
    kon, koff = _resolve_dybond_rates("spec1", {"epsilon": 2.0}, dt_check=0.01)
    assert math.isclose(kon, 1000.0)
    assert math.isclose(koff, 1000.0 * math.exp(-2.0))

def test_rate_resolution_aliases():
    # eps / P_on aliases
    kon, koff = _resolve_dybond_rates("spec1", {"P_on": 0.1, "eps": 1.5}, dt_check=0.01)
    assert math.isclose(kon, 10.0)
    assert math.isclose(koff, 10.0 * math.exp(-1.5))

def test_rate_resolution_consistent_overconstrained():
    # 4 parameters consistent: kon=10, koff=1, epsilon=ln(10), Pon=0.1 (dt_check=0.01)
    spec_info = {
        "kon": 10.0,
        "koff": 1.0,
        "epsilon": math.log(10.0),
        "Pon": 0.1
    }
    kon, koff = _resolve_dybond_rates("spec1", spec_info, dt_check=0.01)
    assert math.isclose(kon, 10.0)
    assert math.isclose(koff, 1.0)

def test_rate_resolution_inconsistent_pon_kon():
    # Pon = 0.1, dt_check = 0.01 implies kon = 10.0, but kon=20.0 is given
    spec_info = {"Pon": 0.1, "kon": 20.0}
    with pytest.raises(ValueError, match="does not match Pon"):
        _resolve_dybond_rates("spec1", spec_info, dt_check=0.01)

def test_rate_resolution_inconsistent_epsilon_rates():
    # kon = 10.0, koff = 1.0 implies epsilon = ln(10) ~ 2.3026, but epsilon = 5.0 is given
    spec_info = {"kon": 10.0, "koff": 1.0, "epsilon": 5.0}
    with pytest.raises(ValueError, match="does not match kon"):
        _resolve_dybond_rates("spec1", spec_info, dt_check=0.01)
