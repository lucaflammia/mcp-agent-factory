# S02: PKCE Hardening + 401 on Missing/Invalid Token — UAT

**Milestone:** M004
**Written:** 2026-03-30T06:50:00.795Z

## UAT: PKCE Hardening\n\n`pytest tests/test_m004_auth_pkce.py -v` → 10 passed\n\nKey cases confirmed:\n- PKCE S256 full round-trip issues valid JWT\n- Wrong code_verifier → 400\n- Plain method → 400\n- One-time code → second use returns 400\n- Gateway: no token → 401, expired → 401, wrong aud → 401, malformed → 401, valid → 200, insufficient scope → 403"
