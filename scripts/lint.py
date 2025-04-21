#!/usr/bin/env python
"""
Lint script for TensorTours project.
Runs black and flake8 checks separately from tests.
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd, description):
    """Run a command and print its output."""
    print(f"\n=== Running {description} ===")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.stdout:
        print(result.stdout)

    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if result.returncode != 0:
        print(f"{description} failed with exit code {result.returncode}")
        return False

    print(f"{description} passed!")
    return True


def main():
    """Run linting checks."""
    # Get the project root directory
    project_root = Path(__file__).parent.parent

    # Define source directories to check
    src_dirs = [
        project_root / "src" / "tensortours",
        project_root / "tests",
        project_root / "scripts",
    ]

    src_paths = [str(path) for path in src_dirs if path.exists()]

    # Run black
    black_result = run_command(["black", "--check"] + src_paths, "black code formatting check")

    # Run flake8
    flake8_result = run_command(["flake8"] + src_paths, "flake8 linting check")

    # Run pytest with only actual tests (no linting)
    print("\n=== Running tests ===")
    test_result = subprocess.run(["pytest"], cwd=project_root)

    # Return overall success/failure
    return black_result and flake8_result and test_result.returncode == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
