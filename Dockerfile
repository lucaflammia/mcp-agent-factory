FROM python:3.11-slim

WORKDIR /app

# wget is used by service healthchecks (Jaeger, Prometheus, Grafana)
RUN apt-get update && apt-get install -y --no-install-recommends wget \
    && rm -rf /var/lib/apt/lists/*

# Copy only project metadata first so the heavy dep-install layer is cached
# independently of source changes. This layer is invalidated only when
# pyproject.toml or README.md changes, not on every code edit.
ARG EXTRAS=infra,otel,pgvector
COPY pyproject.toml README.md ./
# Stub src so editable install resolves package metadata
RUN mkdir -p src/mcp_agent_factory && touch src/mcp_agent_factory/__init__.py
RUN pip install --no-cache-dir -e ".[${EXTRAS}]" && \
    pip install --no-cache-dir \
        fastapi \
        "uvicorn[standard]" \
        pydantic \
        pydantic-settings \
        authlib \
        sse-starlette \
        httpx \
        python-dotenv \
        anyio \
        numpy

# Copy actual source last — only this layer re-runs on code changes
COPY src ./src

EXPOSE 8000 8001

CMD ["python", "-m", "uvicorn", "mcp_agent_factory.gateway.app:gateway_app", \
     "--host", "0.0.0.0", "--port", "8000"]
