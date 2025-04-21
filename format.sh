#!/bin/bash
# Format all code in the project
# Run in order: autoflake -> isort -> black

echo "Running autoflake to remove unused imports and variables..."
autoflake --in-place --recursive --remove-all-unused-imports --remove-unused-variables src tests integration_tests scripts

echo "Running isort to sort imports..."
isort src tests integration_tests scripts

echo "Running black to format code..."
black src tests integration_tests scripts

echo "All formatting complete! ✨"
