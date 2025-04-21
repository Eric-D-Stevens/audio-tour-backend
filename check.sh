#!/bin/bash
# Run linting and tests
# First runs flake8, and if it passes, runs pytest

echo "Running flake8 to check code quality..."
if flake8 src tests integration_tests scripts; then
    echo "Flake8 checks passed! ✅"
    
    echo "Running unit tests..."
    pytest -k "not black and not flake8" tests/
else
    echo "Flake8 checks failed. Please fix the issues before running tests."
    exit 1
fi
