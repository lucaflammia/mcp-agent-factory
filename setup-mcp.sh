#!/usr/bin/env bash
# Generates .mcp.json from .mcp.json.template using the current directory as the project root.
# Run this once after cloning or moving the repo to a new path.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE="$PROJECT_ROOT/.mcp.json.template"
OUTPUT="$PROJECT_ROOT/.mcp.json"

# Resolve GSD tooling paths from the environment or PATH
GSD_CLI_PATH="${GSD_CLI_PATH:-$(command -v gsd 2>/dev/null || echo "__GSD_CLI_PATH__")}"
GSD_MCP_SERVER_CLI="${GSD_MCP_SERVER_CLI:-$(node -e "console.log(require.resolve('gsd-pi/packages/mcp-server/dist/cli.js'))" 2>/dev/null || echo "__GSD_MCP_SERVER_CLI__")}"
GSD_EXTENSIONS="${GSD_EXTENSIONS:-${HOME}/.gsd/agent/extensions/gsd}"

sed \
  -e "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" \
  -e "s|__GSD_CLI_PATH__|$GSD_CLI_PATH|g" \
  -e "s|__GSD_MCP_SERVER_CLI__|$GSD_MCP_SERVER_CLI|g" \
  -e "s|__GSD_EXTENSIONS__|$GSD_EXTENSIONS|g" \
  "$TEMPLATE" > "$OUTPUT"
echo "Generated $OUTPUT (project root: $PROJECT_ROOT)"
