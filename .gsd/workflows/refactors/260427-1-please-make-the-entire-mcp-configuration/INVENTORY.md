# Inventory — MCP Configuration Path Refactor

## Problem
`.mcp.json` contains two hardcoded absolute paths that differ between laptops:
- `cwd`: `/home/luca/Documents/Misc/PersonalProjects/mcp-agent-factory`
- `env.GSD_WORKFLOW_PROJECT_ROOT`: same

## Files Requiring Changes

| File | Change |
|------|--------|
| `.mcp.json` | Remove from git tracking; add to `.gitignore` |
| `.mcp.json.template` | New file — `.mcp.json` with `__PROJECT_ROOT__` placeholder |
| `setup-mcp.sh` | New script — generates `.mcp.json` from template using `$(pwd)` |
| `.gitignore` | Add `.mcp.json` entry |
| `README.md` | Add setup step for `./setup-mcp.sh` |

## Files NOT Requiring Changes
- `mcp.json` — only localhost URLs, fully portable
- All `.gsd/` artifacts — generated, not committed

## Dependency Order
1. Create template + script
2. Update `.gitignore`
3. `git rm --cached .mcp.json`
4. Update README
5. Commit
