"""Parse and interpret a small arithmetic language for derived metrics."""

import ast
from math import isfinite
from operator import add, mul, neg, pos, sub, truediv


_BINARY_OPERATORS = {ast.Add: add, ast.Sub: sub, ast.Mult: mul, ast.Div: truediv}
_UNARY_OPERATORS = {ast.UAdd: pos, ast.USub: neg}


def parse_formula(formula: str) -> tuple[ast.expr, tuple[str, ...]]:
    """Return a checked expression and its distinct metric names."""
    if not isinstance(formula, str) or not formula.strip() or len(formula) > 1024:
        raise ValueError("Formula must be a nonempty string of at most 1024 characters.")
    try:
        expression = ast.parse(formula.strip(), mode="eval").body
    except SyntaxError as error:
        raise ValueError("Invalid formula syntax. Use an arithmetic expression.") from error

    dependencies = {}
    for node in ast.walk(expression):
        match node:
            case ast.Name(id=name):
                dependencies[name] = None
            case ast.BinOp(op=op) if type(op) in _BINARY_OPERATORS:
                pass
            case ast.UnaryOp(op=op) if type(op) in _UNARY_OPERATORS:
                pass
            case ast.Constant(value=value) if type(value) is int and value.bit_length() <= 1023:
                pass
            case ast.Constant(value=value) if type(value) is float and isfinite(value):
                pass
            case ast.Load() | ast.Add() | ast.Sub() | ast.Mult() | ast.Div() | ast.UAdd() | ast.USub():
                pass
            case _:
                raise ValueError("Unsupported formula. Use metric names, numbers, and +, -, *, /.")

    if not dependencies:
        raise ValueError("Formula must reference at least one metric.")
    return expression, tuple(dependencies)


def evaluate_formula(expression, resolve):
    """Interpret a checked expression, propagating undefined results as None."""
    match expression:
        case ast.Name(id=name):
            return resolve(name)
        case ast.Constant(value=value):
            return value
        case ast.UnaryOp(op=op, operand=operand):
            value = evaluate_formula(operand, resolve)
            return None if value is None else _UNARY_OPERATORS[type(op)](value)
        case ast.BinOp(left=left, op=op, right=right):
            left_value = evaluate_formula(left, resolve)
            right_value = evaluate_formula(right, resolve)
            if left_value is None or right_value is None:
                return None
            if isinstance(op, ast.Div) and right_value == 0:
                return None
            return _BINARY_OPERATORS[type(op)](left_value, right_value)
