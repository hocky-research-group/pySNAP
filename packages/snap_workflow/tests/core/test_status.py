import os
import pytest
from unittest.mock import patch
from snap_workflow.core.workflow import initialize
from snap_workflow.core.domain.stages import add_stage
from snap_workflow.core.domain.variables import add_variable
from snap_workflow.core.domain.sweeps import add_sweep
from snap_workflow.core.domain import status

def test_status_checks(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_variable("x", ["int"], add_to_stages=["stage1"], default_val=5)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    
    # 1. Test set_status value validations
    with pytest.raises(ValueError, match="Can only set status"):
        status.set_status("invalid_status")
        
    with pytest.raises(ValueError, match="Existing status can only be"):
        status.set_status("initialized", old_status="invalid_old")
        
    # 2. Test print_status output
    spoint_path = os.path.join("stage1", "spoints", "x_5")
    os.makedirs(os.path.join(spoint_path, ".spoint_info"), exist_ok=True)
    status.write_status("complete", spoint_path)
    
    with patch('sys.stdout') as mock_stdout:
        status.print_status()
        assert mock_stdout.write.called
