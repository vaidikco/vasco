import io
import sys
import logging
import traceback
import ast
from typing import Tuple, List

logger = logging.getLogger("ScriptExecutor")

class SafetyVisitor(ast.NodeVisitor):
    def __init__(self):
        self.allowed_modules = {'math', 'datetime', 'json', 'random', 'os'}
        self.module_whitelists = {
            'os': {'startfile', 'getcwd'}
        }
        self.allowed_builtins = {
            'print', 'len', 'range', 'int', 'str', 'float', 'list',
            'dict', 'set', 'tuple', 'enumerate', 'zip', 'sum',
            'min', 'max', 'abs', 'round', 'bool', 'complex', 'sorted', 'reversed'
        }
        self.forbidden_builtins = {
            'exec', 'eval', 'compile', 'breakpoint', 'open',
            'read', 'write', 'getattr', '__import__', 'globals', 'locals'
        }
        self.module_aliases = {}  # name -> module_name
        self.imported_funcs = {}  # name -> (module_name, func_name)
        self.error = None

    def visit_Import(self, node):
        for alias in node.names:
            if alias.name not in self.allowed_modules:
                self.error = f"Import of module '{alias.name}' is blocked"
                return
            name = alias.asname or alias.name
            self.module_aliases[name] = alias.name
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        module = node.module
        if module not in self.allowed_modules:
            self.error = f"Import from module '{module}' is blocked"
            return
        for alias in node.names:
            name = alias.asname or alias.name
            self.imported_funcs[name] = (module, alias.name)
        self.generic_visit(node)

    def visit_Call(self, node):
        if self.error:
            return

        func = node.func

        # Handle Attribute calls: os.startfile() or o.startfile()
        if isinstance(func, ast.Attribute):
            obj = func.value
            attr = func.attr

            mod_name = None
            if isinstance(obj, ast.Name):
                mod_name = self.module_aliases.get(obj.id)

            if mod_name:
                if mod_name in self.module_whitelists:
                    if attr not in self.module_whitelists[mod_name]:
                        self.error = f"Function '{mod_name}.{attr}' is blocked"
                        return
                elif mod_name not in self.allowed_modules:
                    self.error = f"Module '{mod_name}' is not allowed"
                    return
            else:
                # Object is not a known safe module alias
                self.error = f"Call to attribute '{attr}' on unknown/unsafe object is blocked"
                return

        # Handle direct calls: print(), math.sqrt(), or imported sqrt()
        elif isinstance(func, ast.Name):
            func_id = func.id

            # 1. Check forbidden builtins first
            if func_id in self.forbidden_builtins:
                self.error = f"Forbidden builtin function '{func_id}'"
                return

            # 2. Check if it's an imported function
            if func_id in self.imported_funcs:
                mod_name, attr_name = self.imported_funcs[func_id]
                if mod_name in self.module_whitelists:
                    if attr_name not in self.module_whitelists[mod_name]:
                        self.error = f"Imported function '{mod_name}.{attr_name}' is blocked"
                        return
                elif mod_name not in self.allowed_modules:
                    self.error = f"Imported module '{mod_name}' is not allowed"
                    return
            # 3. Check if it's an allowed builtin
            elif func_id in self.allowed_builtins:
                pass
            else:
                self.error = f"Function call '{func_id}' is not whitelisted"
                return

        else:
            # any other call (e.g. call to a result of another call)
            self.error = "Complex function calls are blocked for security"
            return

        self.generic_visit(node)

class SafetyValidator:
    """
    Scans Python code for dangerous patterns using a strict WHITELIST AST analysis.
    Assume all code is malicious unless proven otherwise.
    """
    def __init__(self, allow_subprocess_startfile=True):
        # Parameter kept for compatibility but not used in strict whitelist
        pass

    def validate(self, code: str) -> Tuple[bool, str]:
        """
        Validates the provided code using a strict whitelist AST analysis.
        Returns (is_safe, error_message).
        """
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"Syntax error in code: {e}"

        visitor = SafetyVisitor()
        visitor.visit(tree)

        if visitor.error:
            return False, visitor.error

        return True, ""

class ScriptExecutor:
    """
    Executes validated Python code in a controlled environment and captures output.
    """
    def __init__(self, validator: SafetyValidator = None):
        self.validator = validator or SafetyValidator()

    def execute_script(self, code: str) -> Tuple[bool, str]:
        """
        Validates and executes the provided Python code.
        Returns (success, output).
        """
        # 1. Validate
        is_safe, error_msg = self.validator.validate(code)
        if not is_safe:
            logger.warning(f"Safety validation failed: {error_msg}")
            return False, f"Safety Error: {error_msg}"

        # 2. Execute
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        # Save original stdout/stderr
        old_stdout = sys.stdout
        old_stderr = sys.stderr

        try:
            sys.stdout = stdout_capture
            sys.stderr = stderr_capture

            # Use a local dictionary for exec to avoid polluting global namespace
            local_vars = {}
            exec(code, {"__name__": "__main__"}, local_vars)

            success = True
        except Exception:
            success = False
            # Capture the traceback
            sys.stderr.write(traceback.format_exc())
        finally:
            # Restore stdout/stderr
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        output = stdout_capture.getvalue()
        errors = stderr_capture.getvalue()

        if not success:
            return False, f"Execution Error:\n{errors}"

        return True, output if output else "Script executed successfully with no output."


