# S03: Schema Validation and Privacy-First Config — UAT

**Milestone:** M001
**Written:** 2026-03-26T16:35:40.081Z

## UAT Type

- UAT mode: artifact-driven
- Why this mode is sufficient: All behaviour is fully covered by the automated pytest suite; schema rejection and privacy defaults are deterministic and do not require runtime or human-experience testing.

## Preconditions

- Python virtualenv active with pydantic v2 and project installed (`pip install -e .`)
- Working directory: `/home/luca/Documents/Misc/mcp-agent-factory`

## Smoke Test

```
python -m pytest tests/test_schema_validation.py -v
```
Expected: 8 passed, no failures.

## Test Cases

### 1. Echo — missing message field rejected

1. Call the echo tool with arguments `{}`
2. **Expected:** response has `isError: True`

### 2. Echo — valid message passes through

1. Call the echo tool with arguments `{"message": "hi"}`
2. **Expected:** `isError` is absent or False; content text equals `"hi"`

### 3. Add — missing field rejected

1. Call the add tool with arguments `{"a": 1}` (b missing)
2. **Expected:** response has `isError: True`

### 4. Add — wrong type rejected

1. Call the add tool with arguments `{"a": "notanumber", "b": 2}`
2. **Expected:** response has `isError: True`

### 5. Add — valid arguments pass through

1. Call the add tool with arguments `{"a": 3, "b": 4}`
2. **Expected:** `isError` absent; content text equals `"7"`

### 6. PrivacyConfig defaults

1. Instantiate `PrivacyConfig()`
2. **Expected:** `local_only is True`, `allow_egress is False`

### 7. assert_no_egress passes on default config

1. Call `PrivacyConfig().assert_no_egress()`
2. **Expected:** No exception raised

### 8. assert_no_egress raises when egress enabled

1. Call `PrivacyConfig(allow_egress=True).assert_no_egress()`
2. **Expected:** `RuntimeError('Egress is disabled by PrivacyConfig')` raised

## Edge Cases

### Full suite regression

1. Run `python -m pytest tests/ -v`
2. **Expected:** All 31 tests pass — prior lifecycle and ReAct tests must not regress

## Failure Signals

- Any `isError` absent on invalid input — schema validation not wired
- `assert_no_egress` not raising on `allow_egress=True` — guard not implemented
- Test count below 31 — regression in prior slices

## Not Proven By This UAT

- Wire-compatibility with official MCP clients (Content-Length framing not implemented)
- Schema validation for tools added in future slices
- Runtime egress blocking at the network layer (PrivacyConfig is a guard, not an enforcer)

## Notes for Tester

All 8 test cases map directly to test functions in `tests/test_schema_validation.py`. Run the full suite to confirm no regression in prior S01/S02 tests.
