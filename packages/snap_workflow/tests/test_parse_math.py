import pytest
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

def test_parse_math_internal_tests():
    from snap_workflow.core.params.parse_math import tests as run_internal_tests
    run_internal_tests()
