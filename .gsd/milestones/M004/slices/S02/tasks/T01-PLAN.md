---
estimated_steps: 1
estimated_files: 1
skills_used: []
---

# T01: Write tests/test_m004_auth_pkce.py

Write tests/test_m004_auth_pkce.py with: (1) PKCE code_verifier→challenge S256 round-trip using auth/server.py register+authorize+token endpoints to issue a real JWT; (2) gateway rejects missing Bearer (401); (3) gateway rejects expired JWT (401); (4) gateway rejects wrong audience JWT (401); (5) gateway accepts valid token (200).

## Inputs

- `src/mcp_agent_factory/auth/server.py`
- `src/mcp_agent_factory/auth/resource.py`
- `src/mcp_agent_factory/gateway/app.py`
- `tests/test_auth.py`

## Expected Output

- `tests/test_m004_auth_pkce.py`

## Verification

pytest tests/test_m004_auth_pkce.py -v
