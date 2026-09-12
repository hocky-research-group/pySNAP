"""A molecule may have a rigid core while the rest of it stays free.

Droplets with mobile binders are built this way: a core the binders tether to, held
rigidly, and binders that must diffuse over its surface. Marking the whole molecule
rigid would freeze them.
"""

import numpy as np
import pytest

from snap_simulate.system.rigid import build_rigid, check_rigid, rigid_constituents

#: Particle types: a heavy centre, two core beads on it, then two free binders.
MASSES = [1000.0, 1.0, 1.0]
DIAMETERS = [100.0, 1.0, 1.0]


def molecule(rigid):
    """Return a molecule with two core beads at the centre and two free binders.

    rigid: the value of the molecule's "rigid" field.
    """
    return {
        "particle_typeid": [0, 1, 1, 2, 2],
        "particle_positions": [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0],
                               [51.0, 0.0, 0.0], [-51.0, 0.0, 0.0]],
        "rigid": rigid,
    }


class TestConstituentCount:
    def test_a_count_names_that_many_constituents(self):
        assert rigid_constituents(molecule(2), 5) == 2

    def test_true_still_means_the_whole_molecule(self):
        assert rigid_constituents(molecule(True), 5) == 4

    def test_absent_or_false_means_no_body(self):
        assert rigid_constituents({"particle_typeid": [0]}, 1) == 0
        assert rigid_constituents(molecule(False), 5) == 0

    def test_a_count_past_the_molecule_is_refused(self):
        with pytest.raises(ValueError):
            rigid_constituents(molecule(9), 5)


class TestPartialBody:
    def test_only_the_core_joins_the_body(self):
        _, body, _, _ = build_rigid(molecule(2), MASSES, DIAMETERS)
        assert body == [0, 0, 0, -1, -1], "binders must stay free"

    def test_the_whole_molecule_still_works(self):
        _, body, _, _ = build_rigid(molecule(True), MASSES, DIAMETERS)
        assert body == [0] * 5

    def test_the_binders_keep_their_mass(self):
        """The centre carries the body's mass, not the free particles' too."""
        _, _, moment_inertia, _ = build_rigid(molecule(2), MASSES, DIAMETERS)
        # Two core beads of mass 1 sit on the centre, so the body is 1000 in all, and a
        # sphere of diameter 100 has I = 2/5 m R^2 = 2/5 * 998 * 50^2 from the centre
        # alone, the coincident beads adding nothing.
        assert np.allclose(moment_inertia[0], 2 / 5 * 998.0 * 50.0 ** 2)

    def test_free_particles_have_no_moment_of_inertia(self):
        _, _, moment_inertia, _ = build_rigid(molecule(2), MASSES, DIAMETERS)
        assert moment_inertia[3] == [0, 0, 0]
        assert moment_inertia[4] == [0, 0, 0]

    def test_a_molecule_with_a_core_counts_as_rigid(self):
        assert check_rigid({"droplet": molecule(2)}) is True

    def test_a_molecule_without_one_does_not(self):
        assert check_rigid({"droplet": molecule(False)}) is False


class TestManyInstances:
    """Each molecule instance is its own body, and free particles stay free."""

    def test_free_particles_keep_their_tag(self):
        from snap_simulate.system.rigid import offset_bodies

        _, body, _, _ = build_rigid(molecule(2), MASSES, DIAMETERS)
        assert offset_bodies(body, 0) == [0, 0, 0, -1, -1]
        assert offset_bodies(body, 1) == [1, 1, 1, -1, -1], \
            "offsetting -1 would put the second molecule's binders in the first's body"

    def test_a_wholly_rigid_molecule_is_unaffected(self):
        from snap_simulate.system.rigid import offset_bodies

        _, body, _, _ = build_rigid(molecule(True), MASSES, DIAMETERS)
        assert offset_bodies(body, 3) == [3] * 5

    def test_only_the_core_is_a_constituent(self):
        from snap_simulate.system.rigid import constituent_flags

        assert constituent_flags(molecule(2), 5) == [False, True, True, False, False]

    def test_a_wholly_rigid_molecule_is_constituent_but_for_its_centre(self):
        from snap_simulate.system.rigid import constituent_flags

        assert constituent_flags(molecule(True), 5) == [False] + [True] * 4


class TestRigidFilter:
    """A rigid body is integrated through a filter named in the parameter files."""

    def test_flags_given_as_a_list_are_accepted(self):
        """JSON has no tuples, and hoomd.filter.Rigid refuses a list."""
        import hoomd

        from snap_simulate.hoomd.simulation import build_filters

        filters = build_filters({
            "integrated": {"class": "Rigid", "composite": False,
                           "options": {"flags": ["center", "free"]}},
        })
        assert isinstance(filters["integrated"], hoomd.filter.Rigid)

    def test_a_plain_filter_still_builds(self):
        import hoomd

        from snap_simulate.hoomd.simulation import build_filters

        filters = build_filters({"all": {"class": "All", "composite": False,
                                         "options": {}}})
        assert isinstance(filters["all"], hoomd.filter.All)


class TestBodyNaming:
    """HOOMD names a body by its central particle's tag, after the reorder."""

    def test_a_body_takes_its_centre_s_index(self):
        from snap_simulate.system.generator import calc_reorder_idx
        from snap_simulate.system.rigid import renumber_bodies

        # Two molecules, each a centre, one constituent, then two free particles.
        body = [0, 0, -1, -1, 1, 1, -1, -1]
        constituent = [False, True, False, False, False, True, False, False]
        sort_flags, _ = calc_reorder_idx(constituent)
        sorted_body = np.asarray(body)[sort_flags]
        sorted_constituent = np.asarray(constituent)[sort_flags]

        renumbered = renumber_bodies(sorted_body, sorted_constituent)
        centres = [index for index, (tag, is_const)
                   in enumerate(zip(renumbered, sorted_constituent))
                   if tag >= 0 and not is_const]
        for index in centres:
            assert renumbered[index] == index, \
                "a central particle's body tag is its own index"
        # The bodies are named by those indices, whatever they turn out to be: the free
        # particles between the centres push the second one past 1.
        assert sorted(set(renumbered.tolist()) - {-1}) == centres
        assert len(centres) == 2

    def test_constituents_follow_their_centre(self):
        from snap_simulate.system.rigid import renumber_bodies

        # A centre at index 0 with one constituent at index 3, and a free particle.
        renumbered = renumber_bodies([0, -1, -1, 0], [False, False, False, True])
        assert renumbered.tolist() == [0, -1, -1, 0]

    def test_free_particles_stay_free(self):
        from snap_simulate.system.rigid import renumber_bodies

        renumbered = renumber_bodies([-1, -1], [False, False])
        assert renumbered.tolist() == [-1, -1]
