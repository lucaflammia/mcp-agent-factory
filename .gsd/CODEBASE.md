# Codebase Map

Generated: 2026-04-20T10:28:35Z | Files: 98 | Described: 0/98
<!-- gsd:codebase-meta {"generatedAt":"2026-04-20T10:28:35Z","fingerprint":"ef50d2931af471bb512c23fe75a970e064934d06","fileCount":98,"truncated":false} -->

### (root)/
- `.gitignore`
- `.mcp.json`
- `docker-compose.yml`
- `mcp.json`
- `pyproject.toml`
- `README.md`

### docs/
- `docs/security_audit.md`

### src/
- `src/.gitignore`

### src/mcp_agent_factory/
- `src/mcp_agent_factory/__init__.py`
- `src/mcp_agent_factory/adapters.py`
- `src/mcp_agent_factory/models.py`
- `src/mcp_agent_factory/orchestrator.py`
- `src/mcp_agent_factory/react_loop.py`
- `src/mcp_agent_factory/scheduler.py`
- `src/mcp_agent_factory/server_http_secured.py`
- `src/mcp_agent_factory/server_http.py`
- `src/mcp_agent_factory/server.py`

### src/mcp_agent_factory.egg-info/
- `src/mcp_agent_factory.egg-info/dependency_links.txt`
- `src/mcp_agent_factory.egg-info/entry_points.txt`
- `src/mcp_agent_factory.egg-info/PKG-INFO`
- `src/mcp_agent_factory.egg-info/requires.txt`
- `src/mcp_agent_factory.egg-info/SOURCES.txt`
- `src/mcp_agent_factory.egg-info/top_level.txt`

### src/mcp_agent_factory/agents/
- `src/mcp_agent_factory/agents/__init__.py`
- `src/mcp_agent_factory/agents/analyst.py`
- `src/mcp_agent_factory/agents/librarian.py`
- `src/mcp_agent_factory/agents/models.py`
- `src/mcp_agent_factory/agents/pipeline_orchestrator.py`
- `src/mcp_agent_factory/agents/writer.py`

### src/mcp_agent_factory/auth/
- `src/mcp_agent_factory/auth/__init__.py`
- `src/mcp_agent_factory/auth/resource.py`
- `src/mcp_agent_factory/auth/server.py`
- `src/mcp_agent_factory/auth/session.py`

### src/mcp_agent_factory/bridge/
- `src/mcp_agent_factory/bridge/__init__.py`
- `src/mcp_agent_factory/bridge/__main__.py`
- `src/mcp_agent_factory/bridge/gateway_client.py`
- `src/mcp_agent_factory/bridge/oauth_middleware.py`

### src/mcp_agent_factory/config/
- `src/mcp_agent_factory/config/__init__.py`
- `src/mcp_agent_factory/config/privacy.py`

### src/mcp_agent_factory/economics/
- `src/mcp_agent_factory/economics/__init__.py`
- `src/mcp_agent_factory/economics/auction.py`
- `src/mcp_agent_factory/economics/utility.py`

### src/mcp_agent_factory/gateway/
- `src/mcp_agent_factory/gateway/__init__.py`
- `src/mcp_agent_factory/gateway/app.py`
- `src/mcp_agent_factory/gateway/run.py`
- `src/mcp_agent_factory/gateway/sampling.py`
- `src/mcp_agent_factory/gateway/service_layer.py`
- `src/mcp_agent_factory/gateway/validation.py`

### src/mcp_agent_factory/knowledge/
- `src/mcp_agent_factory/knowledge/__init__.py`
- `src/mcp_agent_factory/knowledge/embedder.py`
- `src/mcp_agent_factory/knowledge/ingest.py`
- `src/mcp_agent_factory/knowledge/tools.py`
- `src/mcp_agent_factory/knowledge/vector_store.py`

### src/mcp_agent_factory/messaging/
- `src/mcp_agent_factory/messaging/__init__.py`
- `src/mcp_agent_factory/messaging/bus.py`
- `src/mcp_agent_factory/messaging/sse_router.py`
- `src/mcp_agent_factory/messaging/sse_v1_router.py`

### src/mcp_agent_factory/session/
- `src/mcp_agent_factory/session/__init__.py`
- `src/mcp_agent_factory/session/manager.py`

### src/mcp_agent_factory/streams/
- `src/mcp_agent_factory/streams/__init__.py`
- `src/mcp_agent_factory/streams/circuit_breaker.py`
- `src/mcp_agent_factory/streams/eventlog.py`
- `src/mcp_agent_factory/streams/idempotency.py`
- `src/mcp_agent_factory/streams/kafka_adapter.py`
- `src/mcp_agent_factory/streams/redlock.py`
- `src/mcp_agent_factory/streams/worker.py`

### tests/
- *(32 files: 32 .py)*
