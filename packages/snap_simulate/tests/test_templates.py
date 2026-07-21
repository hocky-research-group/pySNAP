import pytest
import numpy as np
from snap_simulate.system.system import create_molecules_from_template

@pytest.fixture
def particle_specs():
    return {
        "diameters": {
            0: 2.0,  # Colloid type
            1: 1.0,  # Arm type / Patch type / Backbone type
            2: 1.2,  # End type / custom type
        }
    }

def test_linear_polymer(particle_specs):
    molecules = {
        "lin": {
            "molecule_type": "linear_polymer",
            "beads": 5,
            "bead_types": [1, 1, 2, 2, 1],
            "bond_type": 0
        }
    }
    res = create_molecules_from_template(molecules, particle_specs)
    lin = res["lin"]
    
    # 5 beads
    assert len(lin["particle_typeid"]) == 5
    assert lin["particle_typeid"] == [1, 1, 2, 2, 1]
    
    # Check coordinates:
    # diameters: 1: 1.0, 2: 1.2
    # positions along x:
    # i=0: x=0.0
    # i=1: x=0.0 + r_0 + r_1 = 0.5 + 0.5 = 1.0
    # i=2: x=1.0 + r_1 + r_2 = 1.0 + 0.5 + 0.6 = 2.1
    # i=3: x=2.1 + r_2 + r_3 = 2.1 + 0.6 + 0.6 = 3.3
    # i=4: x=3.3 + r_3 + r_4 = 3.3 + 0.6 + 0.5 = 4.4
    positions = np.array(lin["particle_positions"])
    assert np.allclose(positions[:, 1], 0.0)
    assert np.allclose(positions[:, 2], 0.0)
    assert np.allclose(positions[:, 0], [0.0, 1.0, 2.1, 3.3, 4.4])
    
    # 4 bonds
    assert len(lin["bond_groups"]) == 4
    assert lin["bond_groups"] == [[0, 1], [1, 2], [2, 3], [3, 4]]
    assert lin["bond_typeid"] == [0, 0, 0, 0]

def test_linear_polymer_single_bead_type(particle_specs):
    molecules = {
        "lin": {
            "molecule_type": "linear_polymer",
            "beads": 3,
            "bead_types": 1,
            "bond_type": 0
        }
    }
    res = create_molecules_from_template(molecules, particle_specs)
    lin = res["lin"]
    assert lin["particle_typeid"] == [1, 1, 1]
    positions = np.array(lin["particle_positions"])
    assert np.allclose(positions[:, 0], [0.0, 1.0, 2.0])

def test_ring_polymer(particle_specs):
    molecules = {
        "ring": {
            "molecule_type": "ring_polymer",
            "beads": 6,
            "bead_type": 1,
            "bond_type": 0
        }
    }
    res = create_molecules_from_template(molecules, particle_specs)
    ring = res["ring"]
    
    assert len(ring["particle_typeid"]) == 6
    assert ring["particle_typeid"] == [1] * 6
    
    # Radius = 6 * 1.0 / (2 * pi) = 0.9549
    # Coordinates in xy plane, z = 0
    positions = np.array(ring["particle_positions"])
    R = 6 * 1.0 / (2 * np.pi)
    for i in range(6):
        theta = 2.0 * np.pi * i / 6
        expected = np.array([R * np.cos(theta), R * np.sin(theta), 0.0])
        assert np.allclose(positions[i], expected)
        
    # Bonds: 6 bonds including closure
    assert len(ring["bond_groups"]) == 6
    assert ring["bond_groups"] == [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 0]]

def test_comb_polymer(particle_specs):
    molecules = {
        "comb": {
            "molecule_type": "comb_polymer",
            "backbone_beads": 5,
            "backbone_type": 1,   # diameter = 1.0
            "arm_beads": 2,
            "arm_type": 2,        # diameter = 1.2
            "graft_spacing": 2,   # grafts at 0, 2, 4
            "bond_type": 0
        }
    }
    # Graft sites at i=0, 2, 4. 3 grafts total.
    # Total beads = 5 backbone + 3 grafts * 2 beads/arm = 11 beads.
    res = create_molecules_from_template(molecules, particle_specs)
    comb = res["comb"]
    
    assert len(comb["particle_typeid"]) == 11
    # First 5 are backbone (type 1)
    assert comb["particle_typeid"][:5] == [1, 1, 1, 1, 1]
    # Rest are arm beads (type 2)
    assert comb["particle_typeid"][5:] == [2] * 6
    
    # Check bonds:
    # backbone: [0,1], [1,2], [2,3], [3,4] (4 bonds)
    # graft 1: [0, 5], [5, 6] (2 bonds)
    # graft 2: [2, 7], [7, 8] (2 bonds)
    # graft 3: [4, 9], [9, 10] (2 bonds)
    # Total 10 bonds
    assert len(comb["bond_groups"]) == 10
    expected_bonds = [
        [0, 1], [1, 2], [2, 3], [3, 4],
        [0, 5], [5, 6],
        [2, 7], [7, 8],
        [4, 9], [9, 10]
    ]
    assert comb["bond_groups"] == expected_bonds

def test_grafted_colloid(particle_specs):
    molecules = {
        "grafted": {
            "molecule_type": "grafted_colloid",
            "colloid_type": 0,    # diameter = 2.0 (radius = 1.0)
            "arm_beads": 3,
            "num_arms": 4,
            "arm_type": 1,        # diameter = 1.0 (radius = 0.5)
            "end_type": 2,        # diameter = 1.2 (radius = 0.6)
            "bond_type": 0
        }
    }
    # Total beads = 1 + 4 * 3 = 13
    # Total bonds = 4 * 3 = 12
    res = create_molecules_from_template(molecules, particle_specs)
    grafted = res["grafted"]
    
    assert len(grafted["particle_typeid"]) == 13
    assert grafted["particle_typeid"][0] == 0
    # For each arm: type 1, 1, 2
    for arm in range(4):
        offset = 1 + arm * 3
        assert grafted["particle_typeid"][offset : offset+3] == [1, 1, 2]
        
    positions = np.array(grafted["particle_positions"])
    # Center is at 0
    assert np.allclose(positions[0], 0.0)
    
    # Verify arm distances from center:
    # Bead 0 of arm (index 1): colloid_radius (1.0) + arm_radius (0.5) = 1.5
    # Bead 1 of arm (index 2): 1.5 + arm_diameter (1.0) = 2.5
    # Bead 2 of arm (index 3): 2.5 + (arm_radius 0.5 + end_radius 0.6) = 3.6
    for arm in range(4):
        offset = 1 + arm * 3
        dist0 = np.linalg.norm(positions[offset])
        dist1 = np.linalg.norm(positions[offset+1])
        dist2 = np.linalg.norm(positions[offset+2])
        assert np.isclose(dist0, 1.5)
        assert np.isclose(dist1, 2.5)
        assert np.isclose(dist2, 3.6)

def test_grafted_colloid_list_arm_type(particle_specs):
    molecules = {
        "grafted": {
            "molecule_type": "grafted_colloid",
            "colloid_type": 0,    # diameter = 2.0 (radius = 1.0)
            "arm_beads": 3,
            "num_arms": 2,
            "arm_type": [1, 2, 1], # list of types for sequential arm beads
            "end_type": 2,        # diameter = 1.2 (radius = 0.6)
            "bond_type": 0
        }
    }
    res = create_molecules_from_template(molecules, particle_specs)
    grafted = res["grafted"]
    
    assert len(grafted["particle_typeid"]) == 7
    assert grafted["particle_typeid"][0] == 0
    
    # Arm bead types:
    # bead 0: arm_type[0] = 1
    # bead 1: arm_type[1] = 2
    # bead 2: end_type = 2
    assert grafted["particle_typeid"][1:4] == [1, 2, 2]
    assert grafted["particle_typeid"][4:7] == [1, 2, 2]
    
    positions = np.array(grafted["particle_positions"])
    assert np.allclose(positions[0], 0.0)
    
    # Distances:
    # bead 0: R_colloid (1.0) + r_0 (0.5) = 1.5
    # bead 1: R_0 (1.5) + r_0 (0.5) + r_1 (0.6) = 2.6
    # bead 2: R_1 (2.6) + r_1 (0.6) + r_2 (0.6) = 3.8
    for arm in range(2):
        offset = 1 + arm * 3
        dist0 = np.linalg.norm(positions[offset])
        dist1 = np.linalg.norm(positions[offset+1])
        dist2 = np.linalg.norm(positions[offset+2])
        assert np.isclose(dist0, 1.5)
        assert np.isclose(dist1, 2.6)
        assert np.isclose(dist2, 3.8)

def test_patchy_colloid(particle_specs):
    # Test tetrahedral (4 patches)
    molecules = {
        "patchy": {
            "molecule_type": "patchy_colloid",
            "colloid_type": 0,
            "patch_type": 1,
            "num_patches": 4,
            "patch_geometry": "tetrahedral",
            "bond_type": 0
        }
    }
    res = create_molecules_from_template(molecules, particle_specs)
    patchy = res["patchy"]
    assert len(patchy["particle_typeid"]) == 5
    assert patchy["particle_typeid"] == [0, 1, 1, 1, 1]
    assert len(patchy["bond_groups"]) == 4
    
    # Test octahedral (6 patches)
    molecules_oct = {
        "patchy": {
            "molecule_type": "patchy_colloid",
            "colloid_type": 0,
            "patch_type": 1,
            "num_patches": 6,
            "patch_geometry": "octahedral",
            "bond_type": 0
        }
    }
    res = create_molecules_from_template(molecules_oct, particle_specs)
    patchy = res["patchy"]
    assert len(patchy["particle_typeid"]) == 7
    assert len(patchy["bond_groups"]) == 6

def test_linear_polymer_angles(particle_specs):
    molecules = {
        "lin": {
            "molecule_type": "linear_polymer",
            "beads": 5,
            "bead_types": 1,
            "bond_type": 0,
            "angle_type": 2
        }
    }
    res = create_molecules_from_template(molecules, particle_specs)
    lin = res["lin"]
    
    # Beads = 5 -> expect (5 - 2) = 3 angle groups
    assert len(lin["angle_groups"]) == 3
    assert lin["angle_groups"] == [[0, 1, 2], [1, 2, 3], [2, 3, 4]]
    assert lin["angle_typeid"] == [2, 2, 2]

def test_patchy_colloid_angles(particle_specs):
    # Test tetrahedral (4 patches) -> expect 6 neighbor-pair angles
    molecules_tet = {
        "patchy": {
            "molecule_type": "patchy_colloid",
            "colloid_type": 0,
            "patch_type": 1,
            "num_patches": 4,
            "patch_geometry": "tetrahedral",
            "bond_type": 0,
            "angle_type": 1
        }
    }
    res = create_molecules_from_template(molecules_tet, particle_specs)
    patchy_tet = res["patchy"]
    assert len(patchy_tet["angle_groups"]) == 6
    assert all(a[1] == 0 for a in patchy_tet["angle_groups"])  # Central particle is always middle index
    assert patchy_tet["angle_typeid"] == [1] * 6

    # Test octahedral (6 patches) -> expect 12 neighbor-pair angles (excluding opposites)
    molecules_oct = {
        "patchy": {
            "molecule_type": "patchy_colloid",
            "colloid_type": 0,
            "patch_type": 1,
            "num_patches": 6,
            "patch_geometry": "octahedral",
            "bond_type": 0,
            "angle_type": 1
        }
    }
    res = create_molecules_from_template(molecules_oct, particle_specs)
    patchy_oct = res["patchy"]
    assert len(patchy_oct["angle_groups"]) == 12
    assert all(a[1] == 0 for a in patchy_oct["angle_groups"])
    assert patchy_oct["angle_typeid"] == [1] * 12

def test_unsupported_molecule_type(particle_specs):
    molecules = {
        "bad": {
            "molecule_type": "unknown_molecule_kind",
            "beads": 5
        }
    }
    with pytest.raises(Exception) as excinfo:
        create_molecules_from_template(molecules, particle_specs)
    assert "Unsupported molecule_type" in str(excinfo.value)


def test_gen_mixture_no_outfile(tmpdir):
    import os
    from snap_workflow.core.params.system_params import System_Params
    from snap_simulate.system import gen_mixture
    
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
    with open(os.path.join(str(tmpdir), "particles.yml"), "w") as f:
        f.write(particles_content)
    with open(os.path.join(str(tmpdir), "bonds.yml"), "w") as f:
        f.write(bonds_content)
    with open(os.path.join(str(tmpdir), "box.yml"), "w") as f:
        f.write(box_content)
    with open(os.path.join(str(tmpdir), "molecules.yml"), "w") as f:
        f.write(molecules_content)
        
    params = System_Params(str(tmpdir))
    frame = gen_mixture(params, outfile=None)
    
    assert frame is not None
    assert frame.particles.N == 8

