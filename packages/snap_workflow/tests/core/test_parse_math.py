import pytest
import numpy as np
from snap_workflow.core.params.parse_math import parse_math, parse_tokens, tests

def test_parse_tokens():
    assert parse_tokens("1 + 2 * (3 - 4)") == ["1", "+", "2", "*", "(", "3", "-", "4", ")"]
    assert parse_tokens("4**-0.5") == ["4", "**", "-", "0.5"]

def test_basic_arithmetic():
    assert parse_math("1 + 2") == 3
    assert parse_math("10 - 4") == 6
    assert parse_math("3 * 4") == 12
    assert parse_math("12 / 4") == 3
    assert parse_math("10 % 3") == 1
    assert parse_math("2 ** 3") == 8
    assert parse_math("2 ^ 3") == 8

def test_unary_minus():
    assert parse_math("-5") == -5
    assert parse_math("-5 + -3") == -8
    assert parse_math("2 * -4") == -8

def test_parentheses_and_precedence():
    assert parse_math("2 + 3 * 4") == 14
    assert parse_math("(2 + 3) * 4") == 20
    assert parse_math("-1+2*(4**(-1/2) + 1)") == 2

def test_variables():
    assert parse_math("pi", {}) == pytest.approx(np.pi)
    assert parse_math("e", {}) == pytest.approx(np.e)
    assert parse_math("x + y", {"x": 10, "y": 20}) == 30
    assert parse_math("2 * var_a ^ 2", {"var_a": 3}) == 18

def test_functions():
    assert parse_math("sin(pi/2)") == 1
    assert parse_math("cos(0)") == 1
    assert parse_math("tan(0)") == 0
    assert parse_math("ln(e)") == 1
    assert parse_math("log(e)") == 1
    assert parse_math("log10(100)") == 2
    assert parse_math("log2(8)") == 3
    assert parse_math("exp(0)") == 1
    assert parse_math("exp2(3)") == 8
    assert parse_math("sqrt(16)") == 4
    assert parse_math("cbrt(27)") == 3
    assert parse_math("abs(-5)") == 5
    assert parse_math("fabs(-5.5)") == 5.5
    assert parse_math("floor(3.7)") == 3
    assert parse_math("ceil(3.2)") == 4
    assert parse_math("round(3.6)") == 4
    assert parse_math("sign(-10)") == -1
    assert parse_math("radians(180)") == pytest.approx(np.pi)
    assert parse_math("degrees(pi)") == pytest.approx(180)
    assert parse_math("rad2deg(pi)") == pytest.approx(180)
    assert parse_math("deg2rad(180)") == pytest.approx(np.pi)
    assert parse_math("asin(1)") == pytest.approx(np.pi / 2)
    assert parse_math("acos(1)") == 0
    assert parse_math("atan(0)") == 0
    assert parse_math("sinh(0)") == 0
    assert parse_math("cosh(0)") == 1
    assert parse_math("tanh(0)") == 0

def test_syntax_errors():
    with pytest.raises(SyntaxError) as exc:
        parse_math("(1 + 2")
    assert "(" in str(exc.value)

    with pytest.raises(SyntaxError) as exc:
        parse_math("1 + 2)")
    assert ")" in str(exc.value)

    with pytest.raises(SyntaxError) as exc:
        parse_math("sin")
    assert "Function" in str(exc.value)

def test_embedded_tests_func(capsys):
    tests()
    captured = capsys.readouterr()
    assert "2" in captured.out
