import io
import sys
import logging
import traceback
import ast
from typing import Tuple, List

logger = logging.getLogger("ScriptExecutor")

class SafetyVisitor(ast.NodeVisitor):
    def __init__(self, forbidden_funcs):
        self.forbidden_funcs = forbidden_funcs
        self.module_aliases = {}  # name -> module_name
        self.imported_funcs = {}  # name -> (module_name, func_name)
        self.error = None

    def visit_Import(self, node):
        for alias in node.names:
            name = alias.asname or alias.name
            if alias.name in self.forbidden_funcs:
                self.module_aliases[name] = alias.name
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        module = node.module
        if module in self.forbidden_funcs:
            for alias in node.names:
                name = alias.asname or alias.name
                self.imported_funcs[name] = (module, alias.name)
        self.generic_visit(node)

    def visit_Call(self, node):
        if self.error:
            return

        # 1. Handle getattr(os, 'remove')
        if isinstance(node.func, ast.Name) and node.func.id == 'getattr':
            if len(node.args) >= 2:
                attr_arg = node.args[1]
                attr_val = None
                if isinstance(attr_arg, ast.Constant) and isinstance(attr_arg.value, str):
                    attr_val = attr_arg.value
                elif isinstance(attr_arg, ast.Str):
                    attr_val = attr_arg.s

                if attr_val:
                    for mod, funcs in self.forbidden_funcs.items():
                        if attr_val in funcs:
                            self.error = f"Forbidden function access via getattr: {attr_val}"
                            return

        # 2. Handle Attribute calls: os.remove() or o.remove()
        if isinstance(node.func, ast.Attribute):
            obj = node.func.value
            attr = node.func.attr

            mod_name = None
            if isinstance(obj, ast.Name):
                mod_name = self.module_aliases.get(obj.id)
            elif isinstance(obj, ast.Call) and isinstance(obj.func, ast.Name) and obj.func.id == '__import__':
                if len(obj.args) > 0:
                    arg = obj.args[0]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        mod_name = arg.value
                    elif isinstance(arg, ast.Str):
                        mod_name = arg.s

            if mod_name in self.forbidden_funcs:
                if attr in self.forbidden_funcs[mod_name]:
                    if mod_name == 'subprocess':
                        if self._is_shell_true(node):
                            self.error = f"Forbidden subprocess call with shell=True: {attr}"
                            return
                    else:
                        self.error = f"Forbidden function call: {mod_name}.{attr}"
                        return

        # 3. Handle direct calls: from os import remove; remove()
        elif isinstance(node.func, ast.Name):
            func_id = node.func.id
            if func_id in self.imported_funcs:
                mod_name, attr_name = self.imported_funcs[func_id]
                if mod_name == 'subprocess':
                    if self._is_shell_true(node):
                        self.error = f"Forbidden subprocess call with shell=True: {attr_name}"
                        return
                else:
                    self.error = f"Forbidden function call: {mod_name}.{attr_name}"
                    return

        self.generic_visit(node)

    def _is_shell_true(self, node):
        for keyword in node.keywords:
            if keyword.arg == 'shell':
                val = keyword.value
                if isinstance(val, ast.Constant) and val.value is True:
                    return True
                elif isinstance(val, ast.NameConstant) and val.value is True:
                    return True
        return False

class SafetyValidator:
    """
    Scans Python code for forbidden functions and dangerous patterns using AST analysis
    to prevent system damage.
    """
    FORBIDDEN_FUNCS = {
        'os': {'remove', 'rmdir', 'system', 'popen'},
        'shutil': {'rmtree', 'rmdir'},
        'subprocess': {'run', 'Popen', 'call', 'check_call', 'check_output'},
    }

    def __init__(self, allow_subprocess_startfile=True):
        self.allow_subprocess_startfile = allow_subprocess_startfile

    def validate(self, code: str) -> Tuple[bool, str]:
        """
        Validates the provided code using AST analysis.
        Returns (is_safe, error_message).
        """
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"Syntax error in code: {e}"

        visitor = SafetyVisitor(self.FORBIDDEN_FUNCS)
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
