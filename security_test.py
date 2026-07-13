
import os
from executor import ScriptExecutor, SafetyValidator

def test_payload(payload, expected_safe):
    executor = ScriptExecutor(SafetyValidator())
    success, result = executor.execute_script(payload)

    # The execute_script returns (True, output) if safe and executed
    # and (False, "Safety Error: ...") if blocked.

    is_safe = not result.startswith("Safety Error")

    if is_safe == expected_safe:
        print(f"PASS: {'ALLOWED' if expected_safe else 'BLOCKED'} - Payload: {payload[:50]}...")
    else:
        print(f"FAIL: Expected {'ALLOWED' if expected_safe else 'BLOCKED'}, but got {'ALLOWED' if is_safe else 'BLOCKED'} - Payload: {payload[:50]}...")

if __name__ == "__main__":
    payloads = [
        ('exec("import os; os.remove(\'test.txt\')")', False),
        ('import pathlib; pathlib.Path(\'test.txt\').unlink()', False),
        ("open('evil.bat', 'w').write('...')", False),
        ("import os; getattr(os, 'rem' + 'ove')('test.txt')", False),
        ("__import__('os').remove('test.txt')", False),
        ("import subprocess; subprocess.run(['ls'], shell=True)", False),
        ("import math; print(math.sqrt(16))", True),
        ("import os; os.startfile('notepad.exe')", True),
    ]

    for payload, expected in payloads:
        test_payload(payload, expected)


