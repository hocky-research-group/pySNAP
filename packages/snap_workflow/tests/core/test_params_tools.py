import os
import json
import pytest
from unittest.mock import patch
from snap_workflow.core.params.tools import dict_defines, decode, get_options, recursive_print

def test_dict_defines():
    assert dict_defines({"a": 1}, "a") is True
    assert dict_defines({"a": None}, "a") is False
    assert dict_defines({"b": 1}, "a") is False

def test_decode_basic():
    assert decode("5", "int") == 5
    assert decode("3.14", "float") == 3.14
    assert decode("hello", "direct") == "hello"
    assert decode(5, "negative") == -5

def test_decode_list_and_tuple():
    # Test tuple conversion
    assert decode([1, 2], "tuple") == (1, 2)
    # Test element-wise list encoding
    assert decode(["5", "3.14"], ["int", "float"]) == [5, 3.14]

def test_decode_dict():
    val = {"a": "5", "b": "direct_val"}
    enc = {"a": "int"}
    assert decode(val, enc) == {"a": 5, "b": "direct_val"}

def test_decode_nested_encodings():
    # Test list of encodings on single value (int -> negative)
    assert decode("5", ["int", "negative"]) == -5

def test_decode_json_file(sandbox):
    json_path = "test.json"
    with open(json_path, "w") as f:
        json.dump({"x": 10}, f)
    
    assert decode(json_path, "json") == {"x": 10}

def test_decode_invalid():
    with pytest.raises(ValueError, match="Can't decode encoding type"):
        decode(5, "unsupported_encoding")

def test_get_options():
    # Test default empty options
    assert get_options({}) == {}
    
    # Test decoding options
    info = {
        "options": {"val": "10"},
        "options_encoding": {"val": "int"}
    }
    assert get_options(info) == {"val": 10}

def test_recursive_print():
    data = {
        "stage1": {
            "substage": {
                "leaf": 1
            }
        }
    }
    with patch('sys.stdout') as mock_stdout:
        recursive_print(data)
        assert mock_stdout.write.called
