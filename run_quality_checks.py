#!/usr/bin/env python
"""Run all tests and code quality checks."""
import subprocess
import sys


def run_command(command, description):
    """Run a command and print its output."""
    print(f"\n\n{'=' * 80}")
    print(f"Running {description}...")
    print(f"{'=' * 80}\n")
    
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    print(result.stdout)
    
    if result.stderr:
        print("Errors:")
        print(result.stderr)
    
    return result.returncode == 0


def main():
    """Run all tests and code quality checks."""
    success = True
    
    # Run black code formatter check (doesn't modify files)
    black_success = run_command(
        "black --check src tests integration_tests", 
        "black code style check"
    )
    success = success and black_success
    
    # Run flake8 linter
    flake8_success = run_command(
        "flake8 src tests integration_tests", 
        "flake8 code style check"
    )
    success = success and flake8_success
    
    # Run pytest tests
    pytest_success = run_command(
        "pytest", 
        "pytest tests"
    )
    success = success and pytest_success
    
    if not success:
        print("\n\nSome checks failed. Please fix the issues before committing.")
        sys.exit(1)
    else:
        print("\n\nAll checks passed!")


if __name__ == "__main__":
    main()
