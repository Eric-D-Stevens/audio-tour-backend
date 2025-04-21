#!/bin/bash
# Run linting and tests
# First runs flake8, and if it passes, runs pytest

# Function to run a command and check its exit code
run_check() {
    echo "$1"
    $2
    exit_code=$?
    if [ $exit_code -ne 0 ]; then
        echo "$3"
        return 1
    fi
    return 0
}

# Parse command line arguments
run_linting=true
run_tests=true

while [[ $# -gt 0 ]]; do
    case $1 in
        --no-lint)
            run_linting=false
            shift
            ;;
        --no-test)
            run_tests=false
            shift
            ;;
        --lint-only)
            run_tests=false
            shift
            ;;
        --test-only)
            run_linting=false
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: ./check.sh [--no-lint] [--no-test] [--lint-only] [--test-only]"
            exit 1
            ;;
    esac
done

# Run linting checks if requested
if [ "$run_linting" = true ]; then
    run_check "Running flake8 to check code quality..." \
             "flake8 src tests integration_tests scripts" \
             "Flake8 checks failed. Please fix the issues before running tests." || exit 1

    run_check "Running black to check code formatting..." \
             "black --check src tests integration_tests scripts" \
             "Black formatting checks failed. Please run 'black src tests integration_tests scripts' to fix formatting." || exit 1
             
    run_check "Running mypy for type checking..." \
             "mypy src tests integration_tests scripts" \
             "Mypy type checks failed. Please fix the type issues." || exit 1
fi

# Run tests if requested
if [ "$run_tests" = true ]; then
    echo "Running unit tests..."
    # Run pytest without the flake8 and black plugins
    pytest -k "not black and not flake8" tests/
fi
