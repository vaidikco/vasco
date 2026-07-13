import logging
import os
from executor import ScriptExecutor, SafetyValidator

# Configure logging for the test
logging.basicConfig(level=logging.INFO)

def test_executor():
    executor = ScriptExecutor()

    tests = [
        {
            "name": "Safe Print",
            "code": "print('Hello from the executor!')",
            "expected_success": True,
        },
        {
            "name": "Safe App Launch",
            "code": "import os\nos.startfile('notepad.exe')",
            "expected_success": True,
        },
        {
            "name": "Dangerous File Remove",
            "code": "import os\nos.remove('test_file.txt')",
            "expected_success": False,
        },
        {
            "name": "Dangerous Directory Remove",
            "code": "import shutil\nshutil.rmtree('some_dir')",
            "expected_success": False,
        },
        {
            "name": "Dangerous Shell Execution",
            "code": "import subprocess\nsubprocess.run('echo hello', shell=True)",
            "expected_success": False,
        },
        {
            "name": "Runtime Error",
            "code": "print('About to crash...')\n1 / 0",
            "expected_success": False,
        },
    ]

    print("--- Starting Executor Tests ---")
    for t in tests:
        print(f"\nTesting: {t['name']}")
        print(f"Code:\n{t['code']}")
        success, output = executor.execute_script(t['code'])
        print(f"Success: {success}")
        print(f"Output: {output}")

        assert success == t['expected_success'], f"Test {t['name']} failed: expected {t['expected_success']}, got {success}"

    print("\n--- All Executor Tests Passed! ---")

if __name__ == "__main__":
    try:
        test_executor()
    except AssertionError as e:
        print(f"Assertion failed: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


