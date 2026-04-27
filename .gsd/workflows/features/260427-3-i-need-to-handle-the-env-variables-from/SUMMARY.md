# Summary: Env Variable Auto-Loading

## What was built

`python-dotenv` now loads `.env` automatically when starting the auth server or gateway. No manual `export` needed in new terminals.

## Files changed

| File | Change |
|---|---|
| `pyproject.toml` | Added `python-dotenv>=1.0` to `dependencies` |
| `src/mcp_agent_factory/auth/__main__.py` | `load_dotenv()` called at start of `main()` |
| `src/mcp_agent_factory/gateway/run.py` | `load_dotenv()` called at module level before `os.getenv()` reads |
| `.env` | Expanded with all known vars and commented defaults (gitignored) |
| `.env.example` | New committed template documenting every env var |

## How to use

1. Copy `.env.example` to `.env` (already done) and fill in real values
2. Start servers normally — env vars load automatically:
   ```
   python -m mcp_agent_factory.auth serve
   python -m mcp_agent_factory.gateway.run
   ```
3. System env vars always take precedence over `.env` values (`override=False`)

## Tests
66 tests pass. No regressions.
