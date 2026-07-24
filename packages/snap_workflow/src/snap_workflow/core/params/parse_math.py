import numpy as np

operators = {")": 0, "(": 0, "+": 1, "-": 1, "*": 2, "/": 2, "%": 2, "^": 3, "**": 3, "--": 4}
left_paren = "("
right_paren = ")"
matching_paren = {")": "("}
PAREN = "paren"
PRIORITY = "priority"

DEFAULT_VARIABLES = {
    "pi": np.pi,
    "e": np.e,
}

FUNCTIONS = {
    # Exponential & Logarithmic
    "ln": np.log,
    "log": np.log,
    "log10": np.log10,
    "log2": np.log2,
    "exp": np.exp,
    "exp2": np.exp2,
    # Trigonometric
    "sin": np.sin,
    "cos": np.cos,
    "tan": np.tan,
    "asin": np.arcsin,
    "arcsin": np.arcsin,
    "acos": np.arccos,
    "arccos": np.arccos,
    "atan": np.arctan,
    "arctan": np.arctan,
    # Hyperbolic
    "sinh": np.sinh,
    "cosh": np.cosh,
    "tanh": np.tanh,
    # Roots & Power & Absolute
    "sqrt": np.sqrt,
    "cbrt": np.cbrt,
    "abs": np.abs,
    "fabs": np.abs,
    # Rounding & Sign
    "floor": np.floor,
    "ceil": np.ceil,
    "round": np.round,
    "sign": np.sign,
    # Angle conversion
    "radians": np.radians,
    "degrees": np.degrees,
    "rad2deg": np.rad2deg,
    "deg2rad": np.deg2rad,
}


def parse_math(expression, variables=None):  # {{{
    if variables is None:
        variables = {}
    combined_vars = {**DEFAULT_VARIABLES, **variables}
    tokens = parse_tokens(expression)

    stack = []
    priority_stack = []
    top_priority = 0

    i = 0
    while i < len(tokens):
        token = tokens[i]

        if token == left_paren:
            stack.append(token)
            priority_stack.append(top_priority)
            top_priority = 0

        elif token == right_paren:
            stack = evaluate(stack, to_priority=matching_paren[right_paren])
            if len(stack) >= 2 and isinstance(stack[-2], str) and stack[-2] in FUNCTIONS:
                val = stack.pop()
                fn_name = stack.pop()
                res = FUNCTIONS[fn_name](val)
                if hasattr(res, "item"):
                    res = res.item()
                if isinstance(res, float) and res.is_integer():
                    res = int(res)
                stack.append(res)
            top_priority = priority_stack.pop()

        elif token in operators:
            if is_unary(token, stack):
                token = "--"

            priority = operators[token]
            if priority < top_priority:
                stack = evaluate(stack, to_priority=priority)
            else:
                top_priority = priority
            stack.append(token)

        elif token in FUNCTIONS and (i + 1 < len(tokens) and tokens[i + 1] == left_paren):
            stack.append(token)

        elif token in combined_vars:
            stack.append(combined_vars[token])

        elif token in FUNCTIONS:
            stack.append(token)

        else:
            val = float(token)
            if val.is_integer():
                val = int(val)
            stack.append(val)
        i += 1

    stack = evaluate(stack, to_priority=0)
    if len(stack) != 1:
        if left_paren in stack:
            raise SyntaxError(f"'{left_paren}' missing a paired '{right_paren}'")
    if len(stack) == 1 and isinstance(stack[0], str) and stack[0] in FUNCTIONS:
        raise SyntaxError(f"Function '{stack[0]}' missing a paired '{left_paren}'")
    return stack[0]
    # }}}


def parse_tokens(value):  # {{{
    value = "".join(value.split())

    tokens = []
    left = 0
    right = 0
    while right < len(value):
        if value[right] in operators:
            if right != 0 and left != right:
                tokens.append(value[left:right])
            if value[right] == "*" and right + 1 != len(value) and value[right + 1] == "*":
                tokens.append(value[right : right + 2])
                right += 1
            else:
                tokens.append(value[right])
            right += 1
            left = right
        else:
            right += 1
    if value[-1] not in operators:
        tokens.append(value[left:right])
    return tokens  # }}}


def evaluate(stack, to_priority):  # {{{
    if to_priority == left_paren:
        condition = PAREN
        check = lambda: stack[-2] != to_priority
    else:
        condition = PRIORITY
        check = lambda: operators[stack[-2]] > to_priority

    while len(stack) > 1 and check():
        right = stack.pop()
        op = stack.pop()

        if op == "--":
            stack.append(-right)
            continue

        left = stack.pop()
        if op == "**":
            stack.append(left**right)
        elif op == "^":
            stack.append(left**right)
        elif op == "%":
            stack.append(left % right)
        elif op == "*":
            stack.append(left * right)
        elif op == "/":
            stack.append(left / right)
        elif op == "+":
            stack.append(left + right)
        elif op == "-":
            stack.append(left - right)

    if condition == PAREN:
        if len(stack) < 2:
            raise SyntaxError(f"'{right_paren}' missing a paired '{left_paren}'")
        stack[-2] = stack[-1]
        stack.pop()
    return stack
    # }}}


def is_unary(operator, stack):  # {{{
    if operator != "-":
        return False
    if len(stack) == 0:
        return True
    if stack[-1] in operators:
        return True
    return False
    # }}}


def tests():  # {{{
    print(parse_math("-1+2*(4**(-1/2) + 1)"))
    print(parse_math("-1+2*(4**(-0.5) + 1)"))
    print(parse_math("-1+2*4**(-0.5) + 2"))
    print(parse_math("2*4**(-0.5) + 1"))
    print(parse_math("pi/6", {"pi": 3.14159}))
    print(parse_math("1*(36**-0.5)"))
    print(parse_math("2^(1/6)"))
    print(parse_math("sin(pi/2)"))
    print(parse_math("log(e)"))
    print(parse_math("ln(e)"))
    print(parse_math("sqrt(16)"))
    # }}}

