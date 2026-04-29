FROM python:3.11-slim

WORKDIR /app

# wget is used by service healthchecks (Jaeger, Prometheus, Grafana)
RUN apt-get update && apt-get install -y --no-install-recommends wget \
    && rm -rf /var/lib/apt/lists/*

# Copy project metadata first so the dep-install layer is cached
COPY pyproject.toml README.md ./
COPY src ./src

# Install core + streaming infra deps; skip ML extras (sentence-transformers / torch)
# because the embedder uses a lazy import — health checks and most tools work without it.
# Add ML extras to the image with: docker build --build-arg EXTRAS=infra,ml
ARG EXTRAS=infra,otel
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

EXPOSE 8000 8001

CMD ["python", "-m", "uvicorn", "mcp_agent_factory.gateway.app:gateway_app", \
     "--host", "0.0.0.0", "--port", "8000"]
