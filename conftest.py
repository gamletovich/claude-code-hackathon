"""
Root conftest.py — makes pytest work from any working directory.

Adds both source trees to sys.path so that test files can import
order_processor (legacy) and order_validator (modern) without relying
on the test file's own sys.path manipulation.
"""
import os
import sys

_ROOT = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_ROOT, "legacy", "src"))
sys.path.insert(0, os.path.join(_ROOT, "modern", "src"))
