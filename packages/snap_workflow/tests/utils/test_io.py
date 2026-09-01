import os
import json
import pytest
from unittest.mock import patch, MagicMock
from snap_workflow.core.workflow import initialize
from snap_workflow.utils import io

def test_extract():
    # Normal extraction
    kwargs = {"a": 1, "b": 2}
    k, v = io.extract(kwargs, ["a"])
    assert k == "a"
    assert v == 1
    assert "a" not in kwargs
    
    # Conflict/Multiple arguments exception
    kwargs_err = {"a": 1, "b": 2}
    with pytest.raises(Exception, match="Extracted multiple arguments"):
        io.extract(kwargs_err, ["a", "b"])

def test_input_collector_setters_and_delimiters():
    ic = io.InputCollector(
        prompt="Enter:",
        help_string="Some help",
        is_list=True,
        default="abc",
        valid_options=["abc", "def"],
        exclusions=["xyz"],
        used_exclusions=["lmn"],
        char_exclusions=["!"],
        add_checks=[lambda x: len(x) > 1],
        add_errors=["Too short"],
        conversions=[str.lower],
        keys=["input_key"],
        delimiters=[";", "|"]
    )
    assert ic.prompt == "Enter:"
    assert ic.help_string == "Some help"
    assert ic.is_list is True
    assert ic.default == "abc"
    assert ic.valid_options == ["abc", "def"]
    assert ic.exclusions == ["xyz"]
    assert ic.used_exclusions == ["lmn"]
    assert ic.char_exclusions == ["!"]
    assert ic.add_checks == [ic.add_checks[0]]
    assert ic.add_errors == ["Too short"]
    assert ic.conversions == [str.lower]
    assert ic.keys == ["input_key"]
    assert ic.delimiters == [";", "|"]

def test_input_collector_conversions():
    ic_none = io.InputCollector("prompt")
    assert ic_none.convert("Hello") == "Hello"
    
    ic_single = io.InputCollector("prompt", conversions=str.upper)
    assert ic_single.convert("hello") == "HELLO"
    
    ic_multi = io.InputCollector("prompt", conversions=[str.strip, str.upper])
    assert ic_multi.convert("  hello  ") == "HELLO"

def test_input_collector_validation(capsys):
    ic = io.InputCollector("prompt", help_string="My help instructions")
    assert ic.is_valid("help") is None
    captured = capsys.readouterr()
    assert "My help instructions" in captured.out
    
    ic_no_default = io.InputCollector("prompt")
    assert ic_no_default.is_valid("None") is None
    captured = capsys.readouterr()
    assert "Must supply a value" in captured.out
    
    ic_with_default = io.InputCollector("prompt", default="my_default")
    assert ic_with_default.is_valid("") == "my_default"
    
    ic_opts = io.InputCollector("prompt", valid_options=["opt1", "opt2"])
    assert ic_opts.is_valid("opt3") is None
    captured = capsys.readouterr()
    assert "is not a valid option" in captured.out
    
    ic_used = io.InputCollector("prompt", used_exclusions=["ex1", "ex2"])
    assert ic_used.is_valid("ex1") is None
    captured = capsys.readouterr()
    assert "is already in use" in captured.out
    
    ic_ex = io.InputCollector("prompt", exclusions=["bad1"])
    assert ic_ex.is_valid("bad1") is None
    captured = capsys.readouterr()
    assert "is not allowed due to potential ambiguity" in captured.out
    
    ic_chars = io.InputCollector("prompt", char_exclusions=["@", "#"])
    assert ic_chars.is_valid("user@domain") is None
    captured = capsys.readouterr()
    assert "has invalid characters" in captured.out
    
    ic_checks = io.InputCollector("prompt", add_checks=lambda x: x.startswith("a"), add_errors="Must start with a")
    assert ic_checks.is_valid("bad") is None
    captured = capsys.readouterr()
    assert "does not pass check" in captured.out
    assert "Must start with a" in captured.out
    
    assert ic_checks.is_valid("abc") == "abc"

def test_input_collector_collect_methods():
    ic_default = io.InputCollector("prompt", default="def")
    with patch("builtins.input", return_value=""):
        assert ic_default.collect() == "def"
        
    ic_single = io.InputCollector("prompt", valid_options=["val"])
    with patch("builtins.input", side_effect=["bad_val", "val"]):
        assert ic_single.collect() == "val"
        
    ic_list = io.InputCollector("prompt", is_list=True)
    with patch("builtins.input", side_effect=["None", "val1,val2"]):
        assert ic_list.collect() == ["val1", "val2"]

def test_list_input_handling(capsys):
    ic = io.InputCollector("prompt", is_list=True, valid_options=["a", "b"], conversions=str.lower)
    
    res = ic.check_list_input("a c")
    assert res is None
    captured = capsys.readouterr()
    assert "List contains the above errors" in captured.out
    
    with pytest.raises(Exception, match="is an invalid argument for key my_key"):
        ic.check_list_input("a c", key="my_key")
        
    ic_custom = io.InputCollector("prompt", is_list=True, list_conversion=lambda l: [x + "!" for x in l])
    assert ic_custom.check_list_input("a b") == ["a!", "b!"]

def test_parse_kwargs():
    ic_single = io.InputCollector("prompt", keys=["my_arg"], conversions=int)
    assert ic_single.parse_kwargs({}) is None
    assert ic_single.parse_kwargs({"my_arg": "42"}) == 42
    ic_err = io.InputCollector("prompt", keys=["my_arg"], valid_options=["yes"])
    with pytest.raises(Exception, match="is in invalid argument for key my_arg"):
        ic_err.parse_kwargs({"my_arg": "no"})
        
    ic_list = io.InputCollector("prompt", is_list=True, keys=["my_list"], conversions=int)
    assert ic_list.parse_kwargs({}) is None
    assert ic_list.parse_kwargs({"my_list": ["1", "2"]}) == [1, 2]
    assert ic_list.parse_kwargs({"my_list": "1,2"}) == [1, 2]

def test_yes_no_collectors():
    ic = io.make_yes_no_collector("Prompt:")
    assert ic.prompt == "Prompt:"
    assert ic.help_string == "Please enter yes or no"
    assert ic.valid_options == io.yes + io.no
    
    assert io.is_yes("yes") is True
    assert io.is_yes("no") is False
    assert io.is_no("no") is True
    assert io.is_no("yes") is False

def test_print_helpers(capsys):
    io.warn_unused_kwargs({})
    io.warn_unused_kwargs({"extra": 1})
    captured = capsys.readouterr()
    assert "WARNING" in captured.out
    assert "extra : 1" in captured.out
    
    dict_to_print = {"a": 1, "b": {"c": 2}}
    io.recursive_print(dict_to_print)
    captured2 = capsys.readouterr()
    assert "a : 1" in captured2.out
    assert "    c : 2" in captured2.out

def test_json_file_helpers(sandbox, env_dir):
    initialize(env_dir)
    
    data = {"hello": "world"}
    io.save_json("test.json", data)
    assert io.load_json("test.json") == data
    
    with pytest.raises(Exception, match="File does not exist"):
        io.load_json("nonexistent.json")
        
    obj = io.make_json("new.json")
    assert obj == {}
    assert io.load_json("new.json") == {}
    
    with pytest.raises(Exception, match="File already exists"):
        io.make_json("new.json")


def test_save_global_config(tmp_path):
    global_dir = str(tmp_path / "global_config")
    with patch("snap_workflow.utils.constants.GLOBAL_CONFIG_DIR", global_dir):
        cfg = {"setting": "val"}
        io.save_global_config(cfg)
        assert os.path.exists(os.path.join(global_dir, "config.json"))
