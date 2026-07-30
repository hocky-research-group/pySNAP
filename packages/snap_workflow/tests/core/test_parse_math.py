import pytest
import numpy as np
from snap_workflow.core.params.parse_math import parse_math, parse_tokens, evaluate, is_unary

def test_parse_math_operations():
    variables = {"x": 10, "y": 3.0}
    
    # Basic operators
    assert parse_math("1 + 2", variables) == 3
    assert parse_math("5 - 2", variables) == 3
    assert parse_math("2 * 3", variables) == 6
    assert parse_math("6 / 3", variables) == 2
    assert parse_math("5 % 3", variables) == 2
    
    # Float conversion checks
    assert isinstance(parse_math("5 / 2", variables), float)
    assert parse_math("5 / 2", variables) == 2.5
    
    # Exponentiation
    assert parse_math("2 ** 3", variables) == 8
    assert parse_math("2 ^ 3", variables) == 8
    
    # Variable substitution
    assert parse_math("x * y", variables) == 30
    assert parse_math("x + 5", variables) == 15
    
    # Unary negation
    assert parse_math("-5", variables) == -5
    assert parse_math("-x", variables) == -10
    assert parse_math("2 * -3", variables) == -6
    assert parse_math("2 * -(3 + 1)", variables) == -8
    
    # Parentheses priorities
    assert parse_math("2 * (3 + 4)", variables) == 14
    assert parse_math("(2 * 3) + 4", variables) == 10
    assert parse_math("2 * ((3 + 4) * 2)", variables) == 28
    
    # Complex expression from script tests() function
    assert parse_math("-1+2*(4**(-1/2) + 1)", {}) == 2
    assert parse_math("-1+2*(4**(-0.5) + 1)", {}) == 2
    assert parse_math("-1+2*4**(-0.5) + 2", {}) == 2
    assert parse_math("2*4**(-0.5) + 1", {}) == 2
    assert parse_math("2^(1/6)", {}) == 2**(1/6)

def test_parse_math_errors():
    # Right paren missing matching left paren
    with pytest.raises(SyntaxError, match="missing a paired"):
        parse_math("1 + 2)", {})
        
    # Left paren missing matching right paren
    with pytest.raises(SyntaxError, match="missing a paired"):
        parse_math("(1 + 2", {})
        
    with pytest.raises(SyntaxError, match="missing a paired"):
        parse_math("((1 + 2)", {})

def test_is_unary():
    # Not "-" operator
    assert is_unary("+", []) is False
    # Empty stack
    assert is_unary("-", []) is True
    # Stack ends in operator
    assert is_unary("-", [1, "+"]) is True
    # Standard numbers (not unary)
    assert is_unary("-", [1]) is False


def test_math_functions_trig():
    assert parse_math("sin(0)") == 0
    assert pytest.approx(parse_math("sin(pi/2)")) == 1.0
    assert pytest.approx(parse_math("cos(0)")) == 1.0
    assert pytest.approx(parse_math("cos(pi)")) == -1.0
    assert pytest.approx(parse_math("tan(0)")) == 0.0
    assert pytest.approx(parse_math("asin(1)")) == np.pi / 2
    assert pytest.approx(parse_math("arcsin(1)")) == np.pi / 2
    assert pytest.approx(parse_math("acos(1)")) == 0.0
    assert pytest.approx(parse_math("arccos(1)")) == 0.0
    assert pytest.approx(parse_math("atan(0)")) == 0.0
    assert pytest.approx(parse_math("arctan(0)")) == 0.0
    assert pytest.approx(parse_math("sinh(0)")) == 0.0
    assert pytest.approx(parse_math("cosh(0)")) == 1.0
    assert pytest.approx(parse_math("tanh(0)")) == 0.0


def test_math_functions_log_exp():
    assert pytest.approx(parse_math("ln(e)")) == 1.0
    assert pytest.approx(parse_math("log(e)")) == 1.0
    assert pytest.approx(parse_math("log10(100)")) == 2.0
    assert pytest.approx(parse_math("log2(8)")) == 3.0
    assert pytest.approx(parse_math("exp(0)")) == 1.0
    assert pytest.approx(parse_math("exp(1)")) == np.e
    assert pytest.approx(parse_math("exp2(3)")) == 8.0


def test_math_functions_roots_and_abs():
    assert parse_math("sqrt(16)") == 4
    assert parse_math("cbrt(27)") == 3
    assert parse_math("abs(-5)") == 5
    assert parse_math("fabs(-5.5)") == 5.5


def test_math_functions_rounding():
    assert parse_math("floor(3.7)") == 3
    assert parse_math("ceil(3.2)") == 4
    assert parse_math("round(3.5)") == 4
    assert parse_math("sign(-42)") == -1


def test_default_constants():
    assert pytest.approx(parse_math("pi")) == np.pi
    assert pytest.approx(parse_math("e")) == np.e
    # User-defined variables override defaults
    assert parse_math("pi", {"pi": 3.14}) == 3.14


def test_nested_math_functions():
    assert pytest.approx(parse_math("sin(cos(0))")) == np.sin(1.0)
    assert parse_math("sqrt(abs(-16))") == 4
    assert pytest.approx(parse_math("ln(exp(2))")) == 2.0


def test_variable_and_function_name_collision():
    vars_dict = {"sin": 0.5, "log": 10}
    # When followed by '(', sin is evaluated as function np.sin
    assert pytest.approx(parse_math("sin(pi/2)", vars_dict)) == 1.0
    # When NOT followed by '(', sin is evaluated as variable 0.5
    assert parse_math("sin * 2", vars_dict) == 1.0
    assert parse_math("log + 5", vars_dict) == 15


def test_uncalled_function_error():
    with pytest.raises(SyntaxError, match="missing a paired"):
        parse_math("sin", {})


def test_parse_math_internal_tests():
    from snap_workflow.core.params.parse_math import tests as run_internal_tests

    run_internal_tests()

