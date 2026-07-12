import io
import sys
import logging
import traceback
from typing import Tuple, List

logger = logging.getLogger("ScriptExecutor")

class SafetyValidator:
    """
    Scans Python code for forbidden keywords and dangerous patterns to prevent
    accidental system damage.
    """
    FORBIDDEN_KEYWORDS = [
        "os.remove",
        "os.rmdir",
        "shutil.rmtree",
        "shutil.rmdir",
        "os.system",
        "subprocess.Popen",
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "subprocess.run",
    ]

    def __init__(self, allow_subprocess_startfile=True):
        self.allow_subprocess_startfile = allow_subprocess_startfile

    def validate(self, code: str) -> Tuple[bool, str]:
        """
        Validates the provided code against forbidden keywords.
        Returns (is_safe, error_message).
        """
        # Simple keyword check
        for keyword in self.FORBIDDEN_KEYWORDS:
            if keyword in code:
                # Special case for os.startfile or subprocess.run with specific safe args
                # But to be safe, we'll block most of them unless we have a more robust parser.
                # For this task, we'll be strict.

                # If it's subprocess.run, we check if it's used with shell=True
                if keyword == "subprocess.run" and "shell=True" not in code:
                    # We might allow subprocess.run if it's NOT using shell=True?
                    # Actually, the brief says "subprocess.run with dangerous shells".
                    # For now, let's just block the keyword to be safe,
                    # and we'll use os.startfile for the "Open Notepad" case.
                    pass

                return False, f"Forbidden keyword detected: {keyword}"

        # Check for shell=True in any subprocess call
        if "shell=True" in code:
            return False, "Dangerous shell execution (shell=True) is forbidden."

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
