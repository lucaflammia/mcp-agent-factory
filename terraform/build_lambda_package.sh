#!/usr/bin/env bash
set -euo pipefail

# Build a proper Lambda deployment package with dependencies

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BUILD_DIR="$SCRIPT_DIR/.terraform/lambda_build"
ZIP_PATH="$SCRIPT_DIR/.terraform/sfn_worker.zip"
SRC_DIR="$SCRIPT_DIR/../src/mcp_agent_factory/streams"

# Clean
rm -rf "$BUILD_DIR" "$ZIP_PATH"
mkdir -p "$BUILD_DIR"

# Install dependencies into the build directory
pip install \
  -q \
  --target "$BUILD_DIR" \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 311 \
  --only-binary=:all: \
  --upgrade \
  httpx \
  pyjwt

# Copy source code
cp "$SRC_DIR/sfn_worker.py" "$BUILD_DIR/"

# Create zip
cd "$BUILD_DIR"
zip -r -q "../$(basename "$ZIP_PATH")" .
cd - > /dev/null

echo "✓ Lambda package created: $ZIP_PATH"
