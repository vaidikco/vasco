"""Small cross-platform helpers shared by actions, TTS, and the UI."""

import shutil
import subprocess
import sys

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

PLATFORM_NAME = "Windows" if IS_WINDOWS else "macOS" if IS_MACOS else "Linux"


def which(cmd: str) -> str | None:
    return shutil.which(cmd)


def run(cmd: list[str], timeout: float = 15) -> tuple[bool, str]:
    """Run a command quietly. Returns (ok, combined output)."""
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode == 0, output.strip()
    except FileNotFoundError:
        return False, f"Command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return False, f"Command timed out: {' '.join(cmd)}"
