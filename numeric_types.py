"""Recognize numeric metadata returned by Stata and the MCP data inspector."""
import re


def is_numeric_type(value):
    if not isinstance(value, str):
        return False
    return bool(re.match(r'^(?:byte|int|long|float|double)\b', value) or
                re.fullmatch(r'(?:u?int(?:8|16|32|64)|float(?:16|32|64))', value))
