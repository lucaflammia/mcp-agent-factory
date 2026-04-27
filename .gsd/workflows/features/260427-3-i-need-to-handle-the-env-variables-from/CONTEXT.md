# Feature: Auto-load .env variables

## Description

The project reads env vars (`JWT_SECRET`, `REDIS_URL`, `KAFKA_BOOTSTRAP_SERVERS`, etc.) via
`os.getenv()` throughout the codebase. Currently `.env` is never loaded automatically, so
users must export vars manually before each new terminal session when running the auth server
(`python -m mcp_agent_factory.auth serve`) or the MCP gateway (`python -m mcp_agent_factory.gateway.run`).

## Solution

1. **`python-dotenv`** — add as a dev/runtime dependency and call `load_dotenv()` at the two
   entry points (`auth/__main__.py` and `gateway/run.py`) so `.env` is loaded automatically
   whenever either server is started.

2. **`.env.example`** — create a documented template listing every env var the project uses,
   so the user (and future contributors) know exactly what needs to be set.

## Key decisions

| Question | Decision |
|---|---|
| Where to call `load_dotenv()`? | Top of `main()` in `auth/__main__.py` and top of `run()` in `gateway/run.py` — keeps load as late as possible, after imports |
| Override system env vars? | No — `load_dotenv(override=False)` so real exports win over file values |
| Add to `dependencies` or `optional-dependencies`? | `dependencies` — both servers need it unconditionally |
| Shell-level sourcing? | Out of scope — python-dotenv at entry points is sufficient; no `.bashrc` changes needed |

## Scope

**In scope:**
- `python-dotenv` dependency in `pyproject.toml`
- `load_dotenv()` call in auth server entry point
- `load_dotenv()` call in gateway entry point
- `.env.example` with all known vars documented

**Out of scope:**
- Shell profile integration (`.bashrc` / `.zshrc`)
- `docker-compose.yml` changes
- Loading `.env` inside library modules (only entry points)
