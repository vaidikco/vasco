from executor import SafetyValidator

def test_validator():
    validator = SafetyValidator()

    payloads = [
        ("Safe script", "print('Hello')", True),
        ("Aliased import", "import os as o; o.remove('test.txt')", False),
        ("getattr bypass", "import os; getattr(os, 'remove')('test.txt')", False),
        ("__import__ bypass", "__import__('os').remove('test.txt')", False),
        ("subprocess shell=True", "import subprocess; subprocess.run(['ls'], shell=True)", False),
        ("subprocess shell=True space", "import subprocess; subprocess.run(['ls'], shell = True)", False),
        ("subprocess shell=False", "import subprocess; subprocess.run(['ls'], shell=False)", True),
        ("subprocess no shell", "import subprocess; subprocess.run(['ls'])", True),
    ]

    all_passed = True
    for name, code, expected in payloads:
        is_safe, msg = validator.validate(code)
        if is_safe == expected:
            print(f"PASS: {name}")
        else:
            print(f"FAIL: {name} (Safe={is_safe}, Expected={expected})")
            print(f"  Code: {code}")
            print(f"  Message: {msg}")
            all_passed = False

    return all_passed

if __name__ == "__main__":
    if test_validator():
        print("\nAll tests passed!")
        exit(0)
    else:
        print("\nSome tests failed.")
        exit(1)

