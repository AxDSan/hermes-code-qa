"""Test file for code review pipeline validation."""
import os
import sys
import re

# Security issue: hardcoded secret
API_KEY = "sk-abc123def456ghi789jkl012mno345pqr678stu"

# Style issue: inconsistent naming, missing type hints
def doStuff(x, y):
    result = x+y
    return result

# Logic issue: potential division by zero
def calculate_ratio(a, b):
    return a / b

# Impact: unused import, bare except
try:
    something = os.environ.get("HOME")
except:
    pass

# Security: eval usage
def execute_user_input(user_string):
    return eval(user_string)
