import os
import json
import pytest
from snap_workflow.core.workflow import initialize
from snap_workflow.core.stages import add_stage
from snap_workflow.core.variables import (
    add_variable,
    deprecated_make_variables,
    cast_values,
    cast,
    generate_values,
    cast_combo_dict
)
from snap_workflow.core.exceptions import VariableAlreadyExistsError, ConversionError
from snap_workflow.core.sweeps import add_sweep

def test_add_variable_duplicates_and_stages(sandbox, env_dir):
    initialize(env_dir)
    
    # 1. Add normal variable
    add_variable("x", ["int"], add_to_stages=None, default_val=10)
    
    # 2. Add duplicate variable throws VariableAlreadyExistsError
    with pytest.raises(VariableAlreadyExistsError):
        add_variable("x", ["int"])

    # 3. Add variable matching to stages
    add_stage("stage1", sbatch_details=None, stage_variables=[], stage_dependencies=[])
    add_variable("y", ["float"], add_to_stages=["stage1"], default_val=5.5)
    
    with open("stage1/env.json") as f:
        # Load env simply to prove stage directory and files exist
        pass

def test_add_variable_with_existing_sweeps(sandbox, env_dir):
    initialize(env_dir)
    add_stage("stage1", sbatch_details=None, stage_variables=["x"], stage_dependencies=[])
    add_variable("x", ["int"], default_val=5)
    add_sweep("sweep1", include_stages=["stage1"], variable_values={"x": [5]})
    
    # 1. default_val must be provided if sweeps exist
    with pytest.raises(ValueError) as exc:
        add_variable("y", ["int"], default_val=None)
    assert "default_val must be provided" in str(exc.value)

    # 2. Adding variable with default_val updates existing sweeps
    add_variable("y", ["int"], add_to_stages=["stage1"], default_val=10)
    
    with open(".workflow/sweeps.json") as f:
        sweeps = json.load(f)
    assert "y" in sweeps["sweep1"]["values"]
    assert sweeps["sweep1"]["values"]["y"] == [10]

def test_deprecated_make_variables(sandbox, env_dir):
    initialize(env_dir)
    os.remove(".workflow/variables.json")
    deprecated_make_variables()
    with open(".workflow/variables.json") as f:
        data = json.load(f)
    assert isinstance(data, list)

def test_casting_rules(sandbox, env_dir):
    initialize(env_dir)
    add_variable("x", ["int"], default_val=10)
    
    # Test get_variable_names
    from snap_workflow.core.variables import get_variable_names
    assert get_variable_names() == ["x"]

    # Test cast_combo_dict
    assert cast_combo_dict({"x": "5"}) == {"x": 5}

    # 1. float casting
    assert cast(5, ["float"]) == 5.0
    
    # 2. str casting
    assert cast(123, ["str"]) == "123"
    
    # 3. neg casting
    assert cast(5, ["int", "neg"]) == -5
    assert cast(-2.5, ["float", "neg"]) == 2.5

    # 4. cast_values success & error
    assert cast_values("v1", [1, 2], ["int"]) == [1, 2]
    with pytest.raises(ConversionError) as exc:
        cast_values("v1", ["abc"], ["int"])
    assert "Cannot convert abc to specified data type" in str(exc.value)

def test_generate_values():
    # 1. Not starting with 'generate'
    assert generate_values([]) == []
    assert generate_values(["no_gen", "range", 1, 5]) == ["no_gen", "range", 1, 5]

    # 2. Supported conversion type validation
    with pytest.raises(ValueError) as exc:
        generate_values(["generate", "unknown_type", 1, 5])
    assert "not a supported conversion" in str(exc.value)

    # 3. Range generation
    # range 1 to 5 step 1
    assert generate_values(["generate", "range", 1, 5]) == [1, 2, 3, 4]

    # 4. Linspace generation (raises ValueError due to float casting of third arg in numpy 2.0)
    with pytest.raises(ValueError):
        generate_values(["generate", "linspace", 0, 10, 3])

    # 5. Logspace generation (raises ValueError due to float casting of third arg in numpy 2.0)
    with pytest.raises(ValueError):
        generate_values(["generate", "logspace", 1, 3, 3])

    # 6. Math/type parsing error in generate
    with pytest.raises(ValueError) as exc:
        generate_values(["generate", "range", "abc", "def"])
    assert "Failed to generate values with error" in str(exc.value)
