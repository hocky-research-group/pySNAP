import pySNAP
import snap_simulate
import snap_workflow
import snap_analyze

def test_pysnap_namespace_exports():
    # Verify imports from snap_simulate
    assert pySNAP.gen_mixture is snap_simulate.system.gen_mixture
    assert pySNAP.build_simulation is snap_simulate.hoomd.build_simulation
    assert pySNAP.shrink_box is snap_simulate.hoomd.shrink_box

    # Verify imports from snap_workflow
    assert pySNAP.Data_Manager is snap_workflow.Data_Manager
    assert pySNAP.SPoint_Manager is snap_workflow.SPoint_Manager
    assert pySNAP.System_Params is snap_workflow.core.params.system_params.System_Params

    # Verify imports from snap_analyze
    assert pySNAP.analyze is snap_analyze

    # Verify __all__ contains the expected attributes
    expected_exports = {
        "workflow",
        "simulate",
        "analyze",
        "gen_mixture",
        "build_simulation",
        "shrink_box",
        "Data_Manager",
        "SPoint_Manager",
        "System_Params",
    }
    assert set(pySNAP.__all__) == expected_exports
