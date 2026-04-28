# M011: Dockerized Observable Reference Architecture

**Vision:** Turn mcp-agent-factory from a working experiment into a runnable reference architecture: `docker compose up` brings the full stack live, OpenTelemetry traces every request end-to-end, and a Grafana dashboard shows the system's health in real time.

## Success Criteria

- docker compose --profile full up starts all services healthy
- End-to-end OTEL trace visible in Jaeger for a real request
- Grafana dashboard shows live request rate, latency, and auction metrics
- Smoke test script exits 0 against live stack
- All 348 existing tests still pass

## Slices

- [ ] **S01: Full-stack Compose profile** `risk:medium` `depends:[]`
  > After this: docker compose --profile full up; docker compose ps shows all services healthy

- [ ] **S02: OpenTelemetry instrumentation** `risk:medium` `depends:[S01]`
  > After this: Send one query_knowledge_base request; Jaeger UI at localhost:16686 shows a complete trace with child spans

- [ ] **S03: Prometheus metrics and Grafana dashboard** `risk:low` `depends:[S02]`
  > After this: Open Grafana at localhost:3000; dashboard shows live request rate, latency percentiles, and auction bid count

- [ ] **S04: Smoke test and README quickstart** `risk:low` `depends:[S03]`
  > After this: bash scripts/smoke_test.sh exits 0 against a running stack; README quickstart accurate

## Boundary Map

Not provided.
