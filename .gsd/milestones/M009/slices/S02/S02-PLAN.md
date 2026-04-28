# S02: PII Gate & Negative-Permissions Middleware

**Milestone:** M009
**Status:** complete
**Risk:** medium
**Depends:** S01

## Goal

Block fields containing sensitive data (email, API keys, private IPs, JWT-shaped strings) before they reach the router or any external provider. Fields explicitly allow-listed via `MCP_ALLOWED_FIELDS` bypass the gate.

## Tasks

- [x] **T01: Implement PIIGate in validation.py** `est:1h`
- [x] **T02: Wire PIIGate into InternalServiceLayer** `est:30m`
- [x] **T03: Write tests/test_m009_s02.py** `est:1h`

## Verification

- `pytest tests/test_m009_s02.py` — 21 tests all pass
- Full suite: 293 passed, 11 skipped
