# Triage: MethodNotFound — agents/analyze

**Date:** 2026-05-01
**Branch:** gsd/bugfix/methodnotfound-error-agents-analyze-i-go

## Root Cause

The gateway Docker image was built before commit `4a0a2a0` (which added the
`agents/analyze` handler). Running `docker compose --profile full up -d` without
`--build` used the stale cached image, so every `agents/analyze` call fell
through to the MCP catch-all and returned `-32601 Method not found`.

The source code is correct. No logic change is needed.

## Secondary Issue

`demo.sh` requires `MCP_DEV_MODE=1` to be set before starting the stack
(to bypass auth). The error surfaced before that could be confirmed, but users
who hit `-32601` have almost certainly also missed `MCP_DEV_MODE=1`.

## Reproduction

    docker compose --profile full up -d     # no --build
    ./scripts/demo.sh
    # ERROR: Method not found: agents/analyze

## Affected Files

- scripts/demo.sh — Phase 1 error handler
- docker-compose.yml — gateway service comment

## Fix

1. demo.sh: detect -32601 specifically and print a clear rebuild instruction.
2. docker-compose.yml: add comment on gateway build line reminding users to
   pass --build after code updates.
