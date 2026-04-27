#!/usr/bin/env bash
# Generates .mcp.json from .mcp.json.template using the current directory as the project root.
# Run this once after cloning or moving the repo to a new path.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE="$PROJECT_ROOT/.mcp.json.template"
OUTPUT="$PROJECT_ROOT/.mcp.json"

sed "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" "$TEMPLATE" > "$OUTPUT"
echo "Generated $OUTPUT (project root: $PROJECT_ROOT)"
