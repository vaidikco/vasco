"""Sandboxed execution of LLM-generated Python snippets.

Two layers of defense:

1. Whitelist AST validation (SafetyValidator) — assume all code is malicious
   unless every import, call, and attribute access is explicitly allowed.
   Attribute *access* is validated, not just calls, so `print(os.environ)`
   or `os.environ["ANTHROPIC_API_KEY"]` cannot leak secrets, and any
   dunder/underscore attribute (`"".__class__`, `obj._private`) is blocked.

2. Process isolation — validated code runs in a spawned child process with a
   restricted `__builtins__` and a hard timeout, so `while True: pass` cannot
   freeze Vasco and a crash cannot take down the core.
"""

import ast
import io
import logging
import multiprocessing
from typing import Tuple

logger = logging.getLogger("ScriptExecutor")

# Modules importable in full (their public attributes are considered safe).
ALLOWED_MODULES = {"math", "datetime", "json", "random", "platform", "time"}

# Modules importable only for specific attributes.
MODULE_WHITELISTS = {"os": {"getcwd"}}

ALLOWED_BUILTINS = {
    "print", "len", "range", "int", "str", "float", "list", "dict", "set",
    "tuple", "enumerate", "zip", "sum", "min", "max", "abs", "round", "bool",
    "complex", "sorted", "reversed", "divmod", "pow", "repr", "format",
    "isinstance", "all", "any", "iter", "next", "map", "filter", "ord", "chr",
    "hash", "frozenset", "bytes", "slice",
}

FORBIDDEN_BUILTINS = {
    "exec", "eval", "compile", "breakpoint", "open", "input", "__import__",
    "getattr", "setattr", "delattr", "globals", "locals", "vars", "dir",
    "type", "super", "memoryview", "object", "help", "exit", "quit",
}

# Exception types scripts may reference in except clauses.
_SAFE_EXCEPTIONS = {
    "BaseException", "Exception", "ArithmeticError", "AttributeError",
    "IndexError", "KeyError", "LookupError", "NameError", "OSError",
    "OverflowError", "RuntimeError", "StopIteration", "TypeError",
    "ValueError", "ZeroDivisionError",
}


class SafetyVisitor(ast.NodeVisitor):
    def __init__(self):
        self.module_aliases: dict[str, str] = {}   # local name -> module name
        self.imported_funcs: dict[str, tuple] = {}  # local name -> (module, attr)
        self.error: str | None = None

    def _fail(self, message: str):
        if self.error is None:
            self.error = message

    # -- imports -----------------------------------------------------------

    def visit_Import(self, node):
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root not in ALLOWED_MODULES and root not in MODULE_WHITELISTS:
                return self._fail(f"Import of module '{alias.name}' is blocked")
            self.module_aliases[alias.asname or root] = root
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        module = (node.module or "").split(".")[0]
        if module not in ALLOWED_MODULES and module not in MODULE_WHITELISTS:
            return self._fail(f"Import from module '{node.module}' is blocked")
        for alias in node.names:
            if alias.name == "*":
                return self._fail("Wildcard imports are blocked")
            if module in MODULE_WHITELISTS and alias.name not in MODULE_WHITELISTS[module]:
                return self._fail(f"'{module}.{alias.name}' is blocked")
            if alias.name.startswith("_"):
                return self._fail(f"Import of private name '{alias.name}' is blocked")
            self.imported_funcs[alias.asname or alias.name] = (module, alias.name)
        self.generic_visit(node)

    # -- attribute access (reads AND calls) --------------------------------

    def visit_Attribute(self, node):
        if self.error:
            return
        if node.attr.startswith("_"):
            return self._fail(f"Access to private attribute '{node.attr}' is blocked")
        if isinstance(node.value, ast.Name):
            mod = self.module_aliases.get(node.value.id)
            if mod and mod in MODULE_WHITELISTS and node.attr not in MODULE_WHITELISTS[mod]:
                return self._fail(f"'{mod}.{node.attr}' is blocked")
        self.generic_visit(node)

    # -- calls ---------------------------------------------------------------

    def visit_Call(self, node):
        if self.error:
            return
        func = node.func
        if isinstance(func, ast.Name):
            name = func.id
            if name in FORBIDDEN_BUILTINS:
                return self._fail(f"Forbidden builtin '{name}'")
            known = (
                name in ALLOWED_BUILTINS
                or name in _SAFE_EXCEPTIONS
                or name in self.imported_funcs
                or name in self._local_defs
            )
            if not known:
                return self._fail(f"Function call '{name}' is not whitelisted")
        # Attribute calls are covered by visit_Attribute; anything more exotic
        # (calling the result of a call, subscripted callables) is blocked.
        elif not isinstance(func, ast.Attribute):
            return self._fail("Complex call expressions are blocked")
        self.generic_visit(node)

    # -- module scan ---------------------------------------------------------

    def validate_tree(self, tree: ast.AST) -> str | None:
        # Functions defined inside the script itself are callable.
        self._local_defs = {
            n.name for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.visit(tree)
        if self.error:
            return self.error

        # A module object may only appear as the base of an attribute access
        # (blocks smuggling: `x = os`, `[os][0].environ`, `f(os)`).
        parents: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent
        for n in ast.walk(tree):
            if (
                isinstance(n, ast.Name)
                and isinstance(n.ctx, ast.Load)
                and n.id in self.module_aliases
            ):
                p = parents.get(n)
                if not (isinstance(p, ast.Attribute) and p.value is n):
                    return f"Module '{n.id}' can only be used for attribute access"
        return None


class SafetyValidator:
    """Static whitelist analysis of untrusted Python code."""

    def validate(self, code: str) -> Tuple[bool, str]:
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"Syntax error in code: {e}"
        error = SafetyVisitor().validate_tree(tree)
        if error:
            return False, error
        return True, ""


def _build_restricted_builtins():
    import builtins as _builtins

    allowed = {}
    for name in ALLOWED_BUILTINS | _SAFE_EXCEPTIONS | {"__build_class__"}:
        if hasattr(_builtins, name):
            allowed[name] = getattr(_builtins, name)

    def _guarded_import(name, *args, **kwargs):
        root = name.split(".")[0]
        if root in ALLOWED_MODULES or root in MODULE_WHITELISTS:
            return __import__(name, *args, **kwargs)
        raise ImportError(f"Import of '{name}' is blocked by the sandbox")

    allowed["__import__"] = _guarded_import
    return allowed


def _sandbox_worker(code: str, queue):
    """Runs in a spawned child process. Executes validated code and reports back."""
    stdout, stderr = io.StringIO(), io.StringIO()
    import contextlib
    import traceback

    success = True
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            exec(  # noqa: S102 - validated + isolated on purpose
                code,
                {"__builtins__": _build_restricted_builtins(), "__name__": "__main__"},
            )
        except BaseException:
            success = False
            stderr.write(traceback.format_exc())
    queue.put((success, stdout.getvalue(), stderr.getvalue()))


class ScriptExecutor:
    """Validates and executes Python code in an isolated, time-limited process."""

    def __init__(self, validator: SafetyValidator | None = None, timeout: float = 5.0):
        self.validator = validator or SafetyValidator()
        self.timeout = timeout

    def execute_script(self, code: str, timeout: float | None = None) -> Tuple[bool, str]:
        is_safe, error_msg = self.validator.validate(code)
        if not is_safe:
            logger.warning("Safety validation failed: %s", error_msg)
            return False, f"Safety Error: {error_msg}"

        ctx = multiprocessing.get_context("spawn")
        queue = ctx.Queue()
        proc = ctx.Process(target=_sandbox_worker, args=(code, queue), daemon=True)
        proc.start()
        proc.join(timeout or self.timeout)

        if proc.is_alive():
            proc.terminate()
            proc.join(1)
            logger.warning("Script exceeded %ss and was killed", timeout or self.timeout)
            return False, f"Execution Error: script timed out after {timeout or self.timeout}s"

        try:
            success, out, err = queue.get_nowait()
        except Exception:
            return False, "Execution Error: script crashed without output"

        if not success:
            return False, f"Execution Error:\n{err}"
        return True, out if out else "Script executed successfully with no output."
