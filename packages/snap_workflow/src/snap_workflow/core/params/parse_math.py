operators = {")":0,"(":0,"+":1,"-":1,"*":2,"/":2,"%":2,"^":3,"**":3,"--":4}
left_paren = "("
right_paren = ")"
matching_paren = {")":"("}
PAREN = "paren"
PRIORITY = "priority"

def parse_math(expression,variables=None):# {{{
    if variables is None:
        variables = {}
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
            stack = evaluate(stack,to_priority=matching_paren[right_paren])
            top_priority = priority_stack.pop()

        elif token in operators:
            if is_unary(token,stack):
                token = "--"

            priority = operators[token]
            if priority < top_priority:
                stack = evaluate(stack,to_priority=priority)
            else:
                top_priority = priority
            stack.append(token)

        elif token in variables:
            stack.append(variables[token])
        else:
            val = float(token)
            if val.is_integer():
                val = int(val)
            stack.append(val)
        i += 1
    stack = evaluate(stack,to_priority=0)
    if len(stack) != 1:
        if left_paren in stack:
            raise SyntaxError(f"'{left_paren}' missing a paired '{right_paren}'")
    return stack[0]
    # }}}
def parse_tokens(value):# {{{
    value = "".join(value.split())

    tokens = []
    left = 0
    right = 0
    while right < len(value):
        if value[right] in operators:
            if right != 0 and left!=right:
                tokens.append(value[left:right])
            if value[right] == "*" and right+1 != len(value) and value[right+1] == "*":
                tokens.append(value[right:right+2])
                right += 1
            else:
                tokens.append(value[right])
            right += 1
            left = right
        else:
            right += 1
    if value[-1] not in operators:
        tokens.append(value[left:right])
    return tokens# }}}
def evaluate(stack,to_priority):# {{{
    if to_priority == left_paren:
        condition = PAREN
        check = lambda : stack[-2] != to_priority
    else:
        condition = PRIORITY
        check = lambda : operators[stack[-2]] > to_priority

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
            stack.append(left%right)
        elif op == "*":
            stack.append(left*right)
        elif op == "/":
            stack.append(left/right)
        elif op == "+":
            stack.append(left+right)
        elif op == "-":
            stack.append(left-right)

    if condition == PAREN:
        if len(stack) < 2:
            raise SyntaxError(f"'{right_paren}' missing a paired '{left_paren}'")
        stack[-2] = stack[-1]
        stack.pop()
    return stack
    # }}}
def is_unary(operator,stack):# {{{
    if operator != "-":
        return False
    if len(stack) == 0:
        return True
    if stack[-1] in operators:
        return True
    return False
    # }}}

def tests():# {{{
    print(parse_math("-1+2*(4**(-1/2) + 1)"))
    print(parse_math("-1+2*(4**(-0.5) + 1)"))
    print(parse_math("-1+2*4**(-0.5) + 2"))
    print(parse_math("2*4**(-0.5) + 1"))
    print(parse_math("pi/6", {"pi": 3.14159}))
    print(parse_math("1*(36**-0.5)"))
    print(parse_math("2^(1/6)"))
    # }}}
