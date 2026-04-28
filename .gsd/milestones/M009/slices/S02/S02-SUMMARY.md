---
slice: S02
milestone: M009
status: complete
---

# S02 Summary: PII Gate & Negative-Permissions Middleware

## What was built

`PIIGate` class in `gateway/validation.py` with four regex pattern categories:
- Email addresses
- API key signatures (`sk-...` prefixes, Bearer tokens)
- JWT-shaped strings (header.payload.signature)
- Private IP addresses (RFC 1918: 10.x, 172.16-31.x, 192.168.x)

`PIIGate.scrub(args, allow_list)` raises `PIIViolation` (a `ValueError` subclass) on the first offending field not in the allow-list. The `MCP_ALLOWED_FIELDS` env var (comma-separated field names) provides a runtime override without code changes.

`InternalServiceLayer.handle()` calls `self._pii_gate.scrub(args)` before any tool dispatch, so all tools/call paths are protected uniformly.

## Verification

- 21 unit + integration + gateway tests — all pass
- Full suite: 293 passed, 11 skipped (0 regressions)
- Risk retired: `MCP_ALLOWED_FIELDS` defaults verified via env var monkeypatching

## Files changed

- `src/mcp_agent_factory/gateway/validation.py` — added `PIIGate`, `PIIViolation`, regex patterns
- `src/mcp_agent_factory/gateway/service_layer.py` — wired `PIIGate` into `handle()`
- `tests/test_m009_s02.py` — 21 tests across 3 layers
