"""Sandbox security and execution tests — including the holes the old code had."""

import pytest

from vasco.executor import SafetyValidator, ScriptExecutor


@pytest.fixture(scope="module")
def executor():
    return ScriptExecutor(timeout=10.0)


validator = SafetyValidator()


def assert_blocked(code, fragment=""):
    ok, msg = validator.validate(code)
    assert not ok, f"expected block, but validated fine: {code!r}"
    if fragment:
        assert fragment.lower() in msg.lower(), msg


def assert_allowed(code):
    ok, msg = validator.validate(code)
    assert ok, f"expected allow, but blocked: {msg} for {code!r}"


# -- things that must run -----------------------------------------------------

def test_safe_print(executor):
    ok, out = executor.execute_script("print('Hello from the sandbox!')")
    assert ok and "Hello from the sandbox!" in out


def test_math(executor):
    ok, out = executor.execute_script("import math\nprint(math.sqrt(16))")
    assert ok and "4.0" in out


def test_local_function_defs(executor):
    code = "def double(x):\n    return x * 2\nprint(double(21))"
    ok, out = executor.execute_script(code)
    assert ok and "42" in out


def test_runtime_error_reported(executor):
    ok, out = executor.execute_script("print('about to crash')\n1 / 0")
    assert not ok and "ZeroDivisionError" in out


# -- classic escapes ------------------------------------------------------------

def test_blocks_exec_eval():
    assert_blocked("exec(\"import os\")", "exec")
    assert_blocked("eval('1+1')", "eval")


def test_blocks_dangerous_imports():
    assert_blocked("import subprocess", "blocked")
    assert_blocked("import shutil\nshutil.rmtree('x')", "blocked")
    assert_blocked("import pathlib; pathlib.Path('x').unlink()", "blocked")
    assert_blocked("import socket", "blocked")


def test_blocks_os_beyond_whitelist():
    assert_blocked("import os\nos.remove('x')", "blocked")
    assert_blocked("import os\nos.system('ls')", "blocked")
    assert_allowed("import os\nprint(os.getcwd())")


def test_blocks_getattr_smuggling():
    # Blocked twice over: getattr is forbidden AND calling a call result is too.
    assert_blocked("import os\ngetattr(os, 'rem' + 'ove')('x')")
    assert_blocked("import os\nf = getattr(os, 'remove')", "getattr")


def test_blocks_dunder_import():
    assert_blocked("__import__('os').remove('x')")


# -- the NEW holes this rewrite closes ------------------------------------------

def test_blocks_env_var_leak_via_print():
    """The old validator allowed print(os.environ) — leaking API keys."""
    assert_blocked("import os\nprint(os.environ)", "blocked")


def test_blocks_env_var_subscript():
    assert_blocked("import os\nprint(os.environ['ANTHROPIC_API_KEY'])", "blocked")


def test_blocks_dunder_attribute_escape():
    assert_blocked("print(''.__class__)", "private")
    assert_blocked("x = 5\nprint(x.__class__.__mro__)", "private")


def test_blocks_module_smuggling():
    assert_blocked("import os\nx = os\nprint(x.environ)", "attribute access")
    assert_blocked("import os\nmods = [os]", "attribute access")
    assert_blocked("import os\nprint(os)", "attribute access")


def test_blocks_wildcard_import():
    assert_blocked("from os import *", "wildcard")


def test_blocks_from_import_beyond_whitelist():
    assert_blocked("from os import remove", "blocked")
    assert_allowed("from os import getcwd\nprint(getcwd())")
    assert_allowed("from math import sqrt\nprint(sqrt(9))")


def test_infinite_loop_times_out():
    fast = ScriptExecutor(timeout=3.0)
    ok, out = fast.execute_script("while True:\n    x = 1")
    assert not ok and "timed out" in out.lower()
