# S03: Validation Gate + Internal Service Layer — UAT

**Milestone:** M006
**Written:** 2026-04-01T14:34:40.689Z

## UAT: S03 — Validation Gate + Internal Service Layer

### Preconditions
- Working directory: `/home/luca/Documents/Misc/mcp-agent-factory/.gsd/worktrees/M006`
- `MCP_DEV_MODE=1` environment variable set (bypasses JWT for new gateway tests)
- All M006/S01 and M006/S02 tests must already pass

---

### Test Cases

#### TC-01: Malformed add payload is blocked with isError response
**Command:** `MCP_DEV_MODE=1 pytest tests/test_m006_gateway.py::test_malformed_add_blocked -v`  
**Steps:**
1. POST `/mcp` with `{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"add","arguments":{"a":"not-a-number","b":2}}}`
2. Inspect response body

**Expected:** HTTP 200, `result.isError == True`, error text contains Pydantic validation message  
**Validates:** R007

---

#### TC-02: Valid add payload is dispatched and returns correct result
**Command:** `MCP_DEV_MODE=1 pytest tests/test_m006_gateway.py::test_valid_add_dispatched -v`  
**Steps:**
1. POST `/mcp` with `{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"add","arguments":{"a":3,"b":4}}}`
2. Inspect response body

**Expected:** HTTP 200, `result.content[0].text == "7"` (integer formatted, not "7.0")  
**Validates:** R006, R007

---

#### TC-03: Tools list smoke test
**Command:** `MCP_DEV_MODE=1 pytest tests/test_m006_gateway.py::test_tools_list_not_empty -v`  
**Steps:**
1. Import `TOOLS` from gateway app
2. Assert `len(TOOLS) > 0`

**Expected:** PASS  
**Validates:** R006 (gateway remains functional after refactor)

---

#### TC-04: Auth gate still rejects unauthenticated tools/call
**Command:** `MCP_DEV_MODE=1 pytest tests/test_gateway.py::test_mcp_no_auth_returns_401 -v`  
**Steps:**
1. POST `/mcp` with a tools/call request, no Authorization header
2. DEV_MODE is monkeypatched to False in this fixture

**Expected:** HTTP 200, body contains `error.code == -32001`  
**Validates:** Existing auth behavior unbroken

---

#### TC-05: Full suite regression (existing + new)
**Command:** `MCP_DEV_MODE=1 pytest tests/test_m006_gateway.py tests/test_gateway.py -v`  
**Expected:** 12/12 passed, 0 failures

