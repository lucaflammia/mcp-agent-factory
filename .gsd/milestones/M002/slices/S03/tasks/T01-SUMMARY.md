---
id: T01
parent: S03
milestone: M002
provides: []
requires: []
affects: []
key_files: ["src/mcp_agent_factory/auth/__init__.py", "src/mcp_agent_factory/auth/session.py", "src/mcp_agent_factory/auth/server.py"]
key_decisions: ["OctKey.generate_key(256) per test via shared_key fixture — injected into both auth server and resource server so tests don't share state", "One-time codes deleted immediately after exchange (del _codes[req.code]) before token issuance to prevent TOCTOU", "scope expansion at issuance: tools:all → {tools:list, tools:call} stored as sorted space-separated string in JWT"]
patterns_established: []
drill_down_paths: []
observability_surfaces: []
duration: ""
verification_result: "python -c imports ok. Tests pass in T03."
completed_at: 2026-03-27T08:09:07.256Z
blocker_discovered: false
---

# T01: OAuth 2.1 Auth Server with PKCE S256, client registration, one-time codes, and JWT issuance with audience binding and user-bound session IDs.

> OAuth 2.1 Auth Server with PKCE S256, client registration, one-time codes, and JWT issuance with audience binding and user-bound session IDs.

## What Happened
---
id: T01
parent: S03
milestone: M002
key_files:
  - src/mcp_agent_factory/auth/__init__.py
  - src/mcp_agent_factory/auth/session.py
  - src/mcp_agent_factory/auth/server.py
key_decisions:
  - OctKey.generate_key(256) per test via shared_key fixture — injected into both auth server and resource server so tests don't share state
  - One-time codes deleted immediately after exchange (del _codes[req.code]) before token issuance to prevent TOCTOU
  - scope expansion at issuance: tools:all → {tools:list, tools:call} stored as sorted space-separated string in JWT
duration: ""
verification_result: passed
completed_at: 2026-03-27T08:09:07.263Z
blocker_discovered: false
---

# T01: OAuth 2.1 Auth Server with PKCE S256, client registration, one-time codes, and JWT issuance with audience binding and user-bound session IDs.

**OAuth 2.1 Auth Server with PKCE S256, client registration, one-time codes, and JWT issuance with audience binding and user-bound session IDs.**

## What Happened

Created auth package with session.py (generate/parse/validate session IDs), and server.py (full OAuth 2.1 Auth Server with PKCE S256 enforcement, client registration, one-time codes, JWT issuance with aud=mcp-server and session_id claim). In-memory stores annotated as production replacement targets in security audit.

## Verification

python -c imports ok. Tests pass in T03.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `python -c "from mcp_agent_factory.auth.server import auth_app; from mcp_agent_factory.auth.session import generate_session_id; print('ok')"` | 0 | ✅ pass | 250ms |


## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `src/mcp_agent_factory/auth/__init__.py`
- `src/mcp_agent_factory/auth/session.py`
- `src/mcp_agent_factory/auth/server.py`


## Deviations
None.

## Known Issues
None.
