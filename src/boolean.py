"""Independent WPL boolean oracle: character lexer and shunting-yard parser.

No compiler parser, AST, interpreter, lowering or SKI imports.
"""
import re


class BooleanSyntax(ValueError):
    pass


def program(source, names):
    if not isinstance(source, str) or len(source.encode('utf-8')) > 8192:
        raise BooleanSyntax('expected WPL text of at most 8192 bytes')
    tokens = []
    i = 0
    while i < len(source):
        c = source[i]
        if c.isspace():
            i += 1
        elif c == '#':
            end = source.find('\n', i)
            i = len(source) if end < 0 else end + 1
        elif source[i:i+2] in ('&&', '||'):
            tokens.append(source[i:i+2]); i += 2
        elif c in '!():':
            tokens.append(c); i += 1
        elif c.isascii() and (c.isalpha() or c == '_'):
            j = i + 1
            while j < len(source) and source[j].isascii() and (source[j].isalnum() or source[j] in '_.'):
                j += 1
            word = source[i:j]
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*', word):
                raise BooleanSyntax('invalid name')
            tokens.append(word); i = j
        else:
            raise BooleanSyntax('invalid character')
    if len(tokens) > 256:
        raise BooleanSyntax('too many tokens')
    declared, i = [], 0
    while i < len(tokens) and tokens[i] == 'fact':
        part = tokens[i:i+4]
        if (len(part) != 4 or part[2:] != [':', 'bool'] or
                not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*', part[1]) or
                part[1] in ('fact', 'check', 'bool', 'true', 'false') or part[1] in declared):
            raise BooleanSyntax('invalid declaration')
        declared.append(part[1]); i += 4
    if set(declared) != set(names) or tokens[i:i+1] != ['check']:
        raise BooleanSyntax('declarations must match world inputs')
    output, operators, used = [], [], set()
    precedence = {'!': 3, '&&': 2, '||': 1}
    operand = True
    for token in tokens[i+1:]:
        if operand:
            if token in ('!', '('):
                operators.append(token)
            elif token in declared or token in ('true', 'false'):
                output.append(token)
                if token in declared:
                    used.add(token)
                operand = False
            else:
                raise BooleanSyntax('expected operand')
        elif token == ')':
            while operators and operators[-1] != '(':
                output.append(operators.pop())
            if not operators:
                raise BooleanSyntax('unmatched close parenthesis')
            operators.pop()
        elif token in ('&&', '||'):
            while operators and operators[-1] != '(' and precedence[operators[-1]] >= precedence[token]:
                output.append(operators.pop())
            operators.append(token); operand = True
        else:
            raise BooleanSyntax('expected operator')
    if operand or '(' in operators or used != set(names):
        raise BooleanSyntax('incomplete expression or unused input')
    output.extend(reversed(operators))
    return tuple(output)


def evaluate(code, facts):
    stack = []
    for token in code:
        if token == '!':
            stack.append(not stack.pop())
        elif token in ('&&', '||'):
            right, left = stack.pop(), stack.pop()
            stack.append((left and right) if token == '&&' else (left or right))
        else:
            stack.append(token == 'true' if token in ('true', 'false') else facts[token])
    if len(stack) != 1:
        raise BooleanSyntax('invalid postfix expression')
    return stack[0]
