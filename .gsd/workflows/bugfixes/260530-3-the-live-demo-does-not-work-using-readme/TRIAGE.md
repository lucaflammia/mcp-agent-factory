# Triage: Live Demo Does Not Work Using README

## Root Causes

### 1. README missing `MCP_DEV_MODE=1` in Live Demo command (primary)
`scripts/demo.sh` checks that the gateway container was started with `MCP_DEV_MODE=1`
(auth bypass). Without it the script exits with an auth error before any demo phase runs.
The README's Live Demo section shows `docker compose --profile full up -d` — missing the
required `MCP_DEV_MODE=1` prefix.

### 2. Docker Compose v2 requirement not documented
The user has `docker-compose` v1.29.2 (legacy Python binary). The README uses
`docker compose` (v2, plugin, space-separated) which v1 treats as an unknown flag.
Furthermore, docker-compose v1.29.2 crashes with `KeyError: 'ContainerConfig'` against
modern Docker Engine — a known upstream incompatibility. The README must state that
Docker Compose **v2** is required.

### 3. `demo.sh` error message points to wrong command
When the gateway health check times out, `demo.sh` prints:
```
ERROR: Gateway not ready after 30s. Run: docker compose up -d
```
The suggested command is missing `--profile full` and `MCP_DEV_MODE=1`.

## Reproduction Steps
1. Clone repo, follow README Live Demo section verbatim.
2. Run `docker compose --profile full up -d` (v1 systems: use `docker-compose`).
3. Gateway container fails due to `ContainerConfig` crash (v1) or starts without auth bypass.
4. Run `./scripts/demo.sh` → gateway health check times out.

## Affected Files
- `README.md` — Live Demo section (line 178), Full Stack Quickstart (line 202)
- `scripts/demo.sh` — gateway-not-ready error message (line ~42)

## Proposed Fix
1. Prefix both README demo commands with `MCP_DEV_MODE=1`.
2. Add a prerequisite note: "Docker Compose v2 is required (`docker compose version` should show v2.x)."
3. Fix `demo.sh` error message to include `MCP_DEV_MODE=1 docker compose --profile full up -d`.
