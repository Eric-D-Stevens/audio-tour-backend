#!/usr/bin/env python
"""Test runner for TensorTours backend using pytest."""
import subprocess
import sys


def run_all_tests():
    """Run all tests in the tests directory using pytest."""
    result = subprocess.run(['pytest', '-v', 'tests'], capture_output=False)
    return result.returncode == 0


def run_model_tests():
    """Run only model tests using pytest."""
    result = subprocess.run(['pytest', '-v', 'tests/models'], capture_output=False)
    return result.returncode == 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == 'models':
        success = run_model_tests()
    else:
        success = run_all_tests()
    
    sys.exit(0 if success else 1)
