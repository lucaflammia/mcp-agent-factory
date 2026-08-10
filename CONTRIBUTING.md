# Contributing to MCP Agent Factory

Thank you for your interest in contributing! This document explains how to get
started.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/lucaflammia/mcp-agent-factory.git
cd mcp-agent-factory

# Install core dependencies
pip install -e .

# Install optional extras
pip install -e ".[ml]"         # sentence-transformers for RAG
pip install -e ".[crew]"       # CrewAI multi-agent orchestration
pip install -e ".[optimizer]"  # DSPy + GEPA offline optimization
pip install -e ".[infra]"      # aiokafka for Kafka integration tests
```

## Running Tests

```bash
# Unit tests (no external services required)
pytest tests/ -v

# Integration tests (requires Docker Compose v2)
MCP_DEV_MODE=1 docker compose --profile full up -d
REDIS_URL=redis://localhost:6379 pytest -m integration -v
```

All unit tests use in-memory fakes (`fakeredis`, `InProcessEventLog`) and require
no Docker or external services.

## Coding Conventions

- **Type hints** on all public functions and method signatures.
- **Pydantic models** for data contracts — no raw dicts crossing module boundaries.
- **`async`/`await`** for I/O-bound code; the gateway and all agents are async.
- Keep imports sorted: stdlib, third-party, local (enforced by your editor or `isort`).
- No `print()` in library code — use structured logging or return values.

## Opening an Issue

- Check existing issues first to avoid duplicates.
- For bugs: include Python version, OS, steps to reproduce, and the full traceback.
- For features: describe the use case and how it fits the existing architecture.

## Pull Requests

1. Fork the repository and create a feature branch from `main`.
2. Make your changes — keep commits focused and atomic.
3. Ensure the test suite passes: `pytest tests/ -v`.
4. Open a PR against `main` with a clear description of what changed and why.

## Security Vulnerabilities

Please report security issues **privately** — see [SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contributions will be licensed under the
[Apache License 2.0](LICENSE).
