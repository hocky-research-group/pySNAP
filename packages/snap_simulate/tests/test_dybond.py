import os
import tempfile
import pytest
import hoomd

try:
    import hoomd.dybond
except ImportError:
    pytest.skip("hoomd.dybond is not importable/broken", allow_module_level=True)

from snap_workflow.core.params.system_params import System_Params
from snap_simulate.system import gen_mixture
from snap_simulate.hoomd import build_simulation

def _setup_params_and_gsd(tmpdir):
    particles_content = """
types: ["A", "B"]
diameters: [1.0, 1.0]
mass: [1.0, 1.0]
"""
    bonds_content = """
types: ["harmonic", "A-B"]
specs:
  Harmonic:
    default_params:
      k: 100.0
      r0: 1.0
    params: {}
"""
    box_content = """
dimensions: 3
box_length: [10.0, 10.0, 10.0]
placement_style: "random"
"""
    molecules_content = """
polymer:
  molecule_type: "linear_polymer"
  beads: 4
  bead_types: [0, 1, 1, 0]
  bond_type: 0
  num_molecules: 2
"""
    with open(os.path.join(tmpdir, "particles.yml"), "w") as f:
        f.write(particles_content)
    with open(os.path.join(tmpdir, "bonds.yml"), "w") as f:
        f.write(bonds_content)
    with open(os.path.join(tmpdir, "box.yml"), "w") as f:
        f.write(box_content)
    with open(os.path.join(tmpdir, "molecules.yml"), "w") as f:
        f.write(molecules_content)

    params = System_Params(tmpdir)
    init_file = os.path.join(tmpdir, "init.gsd")
    gen_mixture(params, init_file)

    params["simulation"] = {
        "device": "CPU",
        "seed": 42,
        "init_file": init_file,
        "has_rigid_bodies": False
    }
    params["filters"] = {
        "all": {
            "class": "All",
            "composite": False
        }
    }
    params["integrator"] = {
        "dt": 0.001,
        "method": {
            "class": "Langevin",
            "filter": "all",
            "options": {
                "kT": 1.0
            }
        }
    }
    params["nlist"] = {
        "cell": {
            "class": "Cell",
            "options": {
                "buffer": 0.4
            }
        }
    }
    params["computes"] = {
        "thermo": {
            "class": "ThermodynamicQuantities",
            "filter": "all"
        }
    }
    return params

def test_dybond_simulation():
    with tempfile.TemporaryDirectory() as tmpdir:
        params = _setup_params_and_gsd(tmpdir)
        params["dybond"] = {
            "nlist": "cell",
            "thermo": "thermo",
            "check_steps": 10,
            "specs": {
                "a_b_bond": {
                    "pair": ["A", "B"],
                    "bond": "Harmonic",
                    "kon": 10.0,
                    "koff": 1.0,
                    "rmin": 0.5,
                    "rmax": 1.5,
                    "r0": 1.0,
                    "metropolis": True,
                    "self_avoid_chain": False
                }
            }
        }

        sim, hoomd_objs = build_simulation(params)
        assert "dybond" in hoomd_objs
        updater = hoomd_objs["dybond"]
        
        from hoomd.dybond import DyBondUpdater
        assert isinstance(updater, DyBondUpdater)
        assert updater in sim.operations.updaters
        
        # Verify default naming: pair is ["A", "B"], so the DyBond name should be "A-B"
        dybond_spec = updater[("A", "B")]
        assert dybond_spec.name == "A-B"
        
        sim.run(1)

def test_dybond_bond_typename():
    with tempfile.TemporaryDirectory() as tmpdir:
        params = _setup_params_and_gsd(tmpdir)
        params["dybond"] = {
            "nlist": "cell",
            "thermo": "thermo",
            "check_steps": 10,
            "specs": {
                "a_b_bond": {
                    "pair": ["A", "B"],
                    "bond": "Harmonic",
                    "bond_typename": "A-B",
                    "kon": 10.0,
                    "koff": 1.0,
                    "rmin": 0.5,
                    "rmax": 1.5,
                    "r0": 1.0,
                    "metropolis": True,
                    "self_avoid_chain": False
                }
            }
        }

        sim, hoomd_objs = build_simulation(params)
        updater = hoomd_objs["dybond"]
        dybond_spec = updater[("A", "B")]
        assert dybond_spec.name == "A-B"
        sim.run(1)

def test_dybond_bond_typeid():
    with tempfile.TemporaryDirectory() as tmpdir:
        params = _setup_params_and_gsd(tmpdir)
        params["dybond"] = {
            "nlist": "cell",
            "thermo": "thermo",
            "check_steps": 10,
            "specs": {
                "a_b_bond": {
                    "pair": ["A", "B"],
                    "bond": "Harmonic",
                    "bond_typeid": 1,  # Index 1 is "A-B"
                    "kon": 10.0,
                    "koff": 1.0,
                    "rmin": 0.5,
                    "rmax": 1.5,
                    "r0": 1.0,
                    "metropolis": True,
                    "self_avoid_chain": False
                }
            }
        }

        sim, hoomd_objs = build_simulation(params)
        updater = hoomd_objs["dybond"]
        dybond_spec = updater[("A", "B")]
        
        sim.run(1)
        # Verify it resolves to "A-B" since typeid 1 corresponds to "A-B"
        assert dybond_spec.name == "A-B"

def test_dybond_mutual_exclusion():
    with tempfile.TemporaryDirectory() as tmpdir:
        params = _setup_params_and_gsd(tmpdir)
        params["dybond"] = {
            "nlist": "cell",
            "thermo": "thermo",
            "check_steps": 10,
            "specs": {
                "a_b_bond": {
                    "pair": ["A", "B"],
                    "bond": "Harmonic",
                    "bond_typename": "A-B",
                    "bond_typeid": 1,
                    "kon": 10.0,
                    "koff": 1.0,
                    "rmin": 0.5,
                    "rmax": 1.5,
                    "r0": 1.0,
                    "metropolis": True,
                    "self_avoid_chain": False
                }
            }
        }

        with pytest.raises(ValueError, match="Only one of 'bond_typename' or 'bond_typeid' can be specified"):
            build_simulation(params)
