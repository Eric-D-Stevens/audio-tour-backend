#!/usr/bin/env python3
"""
Generate TypeScript types from Pydantic models for the TensorTours frontend.
This script leverages pydantic-to-typescript to automatically generate TypeScript
interfaces that match the backend API models.

Usage:
    python scripts/generate_typescript_types.py
"""

import sys
import os
import argparse
from pathlib import Path

# Determine the backend directory and add it to the Python path
script_dir = Path(__file__).resolve().parent
backend_dir = script_dir.parent
sys.path.insert(0, str(backend_dir))

def find_frontend_dir():
    """Attempt to find the frontend directory from the current context."""
    # Try looking for common frontend directory patterns
    possible_frontend_dirs = [
        # Common frontend directory names relative to the backend
        backend_dir.parent / "audio-tour-frontend",
    ]
    
    # Return the first directory that exists
    for dir_path in possible_frontend_dirs:
        if dir_path.exists() and dir_path.is_dir():
            return dir_path
    
    # If no frontend directory is found, return None
    return None

# Import the function
from pydantic2ts import generate_typescript_defs

def main():
    """Generate TypeScript definitions from Pydantic models."""
    parser = argparse.ArgumentParser(description="Generate TypeScript types from Pydantic models")
    parser.add_argument("--output", "-o", help="Output file path")
    parser.add_argument("--module", "-m", default="src.tensortours.models.api", 
                      help="Python module containing Pydantic models (default: src.tensortours.models.api)")
    args = parser.parse_args()
    
    # Determine output file path
    if args.output:
        # Use provided output path
        output_file = Path(args.output)
        output_dir = output_file.parent
    else:
        # Try to auto-detect frontend directory
        frontend_dir = find_frontend_dir()
        
        if frontend_dir:
            # If frontend directory is found, use standard types directory
            output_dir = frontend_dir / "src" / "types"
            output_file = output_dir / "api-types.ts"
            print(f"Frontend directory detected: {frontend_dir}")
        else:
            # Otherwise use current working directory
            output_dir = Path.cwd()
            output_file = output_dir / "api-types.ts"
            print("Frontend directory not found. Using current directory.")
    
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        # Generate TypeScript definitions for API models
        print(f"Generating TypeScript types from module: {args.module}")
        print(f"Output file: {output_file}")
        
        generate_typescript_defs(
            args.module,
            str(output_file),
            json2ts_cmd="json2ts"
        )
        
        print(f"TypeScript definitions generated successfully at {output_file}")
        print("Note: Multiple TourType definitions were generated. Use only the first one in your code.")
    except Exception as e:
        print(f"Error generating TypeScript definitions: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
