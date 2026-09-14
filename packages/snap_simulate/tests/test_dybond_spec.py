"""A dynamic-bond spec must say whether a molecule may bond to itself, and must not set r0.

DyBond-v2 has no default for self-avoidance and takes each reaction's rest length from the
bond potential the reaction names, so a spec that omits the one or sets the other would
build a reaction other than the one it appears to describe.
"""
import pytest

from snap_simulate.hoomd.simulation import _check_dybond_spec


def spec(**overrides):
    """Return a complete spec, with keys added, replaced, or (value None) removed."""
    base = {"pair": ["A", "B"], "bond": "Harmonic", "kon": 10.0, "koff": 1.0,
            "rmin": 0.8, "rmax": 1.2, "self_avoid_chain": False}
    base.update(overrides)
    return {key: value for key, value in base.items() if value is not None}


@pytest.mark.parametrize("flag", [True, False])
def test_complete_spec_is_accepted_with_either_self_avoidance(flag):
    _check_dybond_spec("a_b", spec(self_avoid_chain=flag))


def test_missing_self_avoid_chain_is_refused_naming_the_spec():
    with pytest.raises(ValueError, match=r"a_b.*self_avoid_chain"):
        _check_dybond_spec("a_b", spec(self_avoid_chain=None))


def test_r0_is_refused_because_the_bond_potential_sets_it():
    with pytest.raises(ValueError, match=r"a_b.*r0.*bond"):
        _check_dybond_spec("a_b", spec(r0=1.0))
