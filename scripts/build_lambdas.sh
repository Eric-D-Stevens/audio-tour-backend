#!/bin/bash
# Build script for TensorTours Lambda deployment

# Make the script exit on any error
set -e

VERSION=$(date +%s)
BUILD_DIR="build"
DIST_DIR="dist"
PACKAGE_DIR="tensortours"

echo "Building TensorTours Lambda functions (version: $VERSION)"

# Create build and dist directories
mkdir -p $BUILD_DIR $DIST_DIR

# Install the package in development mode
pip install -e .

# Create Lambda layer with dependencies
echo "Creating Lambda layer with dependencies..."
mkdir -p "$BUILD_DIR/lambda-layer/python"
pip install -r requirements.txt -t "$BUILD_DIR/lambda-layer/python/"
cd "$BUILD_DIR/lambda-layer" && zip -r "../../$DIST_DIR/lambda-layer-$VERSION.zip" . && cd ../..

# Function to build a Lambda deployment package
build_lambda() {
  local function_name="$1"
  local handler_module="$2"
  local handler_function="${3:-handler}"
  
  echo "Building Lambda package for $function_name..."
  mkdir -p "$BUILD_DIR/$function_name"
  
  # Create a simple Lambda entry point that imports from the package
  cat > "$BUILD_DIR/$function_name/index.py" << EOF
# Lambda handler for $function_name
# Automatically generated from tensortours package
from tensortours.lambda_handlers.$handler_module import $handler_function

# Export the handler function
lambda_handler = $handler_function
EOF
  
  # Package the Lambda function
  cd "$BUILD_DIR/$function_name" && zip -r "../../$DIST_DIR/$function_name-$VERSION.zip" . && cd ../..
  
  echo "Created $DIST_DIR/$function_name-$VERSION.zip"
}

# Build each Lambda function
build_lambda "geolocation" "geolocation"
build_lambda "audio-generation" "audio_generation"
build_lambda "tour-pre-generation" "tour_pre_generation"
build_lambda "tour-preview" "tour_preview"
build_lambda "tour-generation" "tour_generation"

# Create a version info file
echo "{\"version\": \"$VERSION\"}" > "$DIST_DIR/version.json"

echo "Build complete! Lambda packages are in the $DIST_DIR directory."
