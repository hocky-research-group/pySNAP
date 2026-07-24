import os
import json
import pytest
from snap_workflow.core.workflow import initialize
from snap_workflow.utils import version

def test_version_helpers(sandbox, env_dir):
    initialize(env_dir)
    
    # 1. Test load_version
    current_version = version.load_version()
    assert current_version == "1.0.0"
    
    # 2. Test is_older_version
    assert version.is_older_version("0.1.0", "1.0.0") is True
    assert version.is_older_version("1.0.0", "0.1.0") is False
    assert version.is_older_version("1.0.0", "1.0.0") is False
    assert version.is_older_version(None, "1.0.0") is True
    
    with pytest.raises(Exception):
        version.is_older_version("invalid", "1.0.0")

def test_check_version_safety(sandbox, env_dir):
    initialize(env_dir)
    
    # Matching version should pass without raise
    version.check_version()
    
    # If last version is older, check_version raises update required exception
    version.save_version("0.9.0")
    with pytest.raises(Exception, match="Running an updated version of workflow"):
        version.check_version()
        
    # If last version is newer, check_version raises downgrade exception
    version.save_version("2.0.0")
    with pytest.raises(Exception, match="Current workflow version is older"):
        version.check_version()

def test_update_routine(sandbox, env_dir):
    initialize(env_dir)
    
    # If last version is older, running update should bump it back to current
    version.save_version("0.9.0")
    version.update()
    assert version.load_version() == "1.0.0"
    
    # If version file is missing, update should recreate it
    os.remove(os.path.join(".workflow", "version.json"))
    version.update()
    assert version.load_version() == "1.0.0"
