# S02: PKCE Hardening + 401 on Missing/Invalid Token

**Goal:** Write tests/test_m004_auth_pkce.py covering: PKCE S256 round-trip token issuance, gateway 401 on missing Bearer, 401 on expired token, 401 on wrong audience.
**Demo:** After this: pytest tests/test_m004_auth_pkce.py -v shows PKCE round-trip issuing a token; 401 tests all pass.

## Tasks
- [x] **T01: 10 PKCE hardening tests written and passing** — Write tests/test_m004_auth_pkce.py with: (1) PKCE code_verifier→challenge S256 round-trip using auth/server.py register+authorize+token endpoints to issue a real JWT; (2) gateway rejects missing Bearer (401); (3) gateway rejects expired JWT (401); (4) gateway rejects wrong audience JWT (401); (5) gateway accepts valid token (200).
  - Estimate: 30m
  - Files: tests/test_m004_auth_pkce.py
  - Verify: pytest tests/test_m004_auth_pkce.py -v
