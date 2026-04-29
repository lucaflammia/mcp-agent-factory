# M011: Dockerized Observable Reference Architecture

**Vision:** Turn mcp-agent-factory from a working experiment into a runnable reference architecture: `docker compose up` brings the full stack live, OpenTelemetry traces every request end-to-end, and a Grafana dashboard shows the system's health in real time.

## Success Criteria

- docker compose --profile full up starts all services healthy
- End-to-end OTEL trace visible in Jaeger for a real request
- Grafana dashboard shows live request rate, latency, and auction metrics
- Smoke test script exits 0 against live stack
- All 348 existing tests still pass

## Slices

- [x] **S01: S01** `risk:medium` `depends:[]`
  > After this: docker compose --profile full up; docker compose ps shows all services healthy

- [x] **S02: S02** `risk:medium` `depends:[]`
  > After this: Send one query_knowledge_base request; Jaeger UI at localhost:16686 shows a complete trace with child spans

- [x] **S03: S03** `risk:low` `depends:[]`
  > After this: Open Grafana at localhost:3000; dashboard shows live request rate, latency percentiles, and auction bid count

- [x] **S04: S04** `risk:low` `depends:[]`
  > After this: bash scripts/smoke_test.sh exits 0 against a running stack; README quickstart accurate

## Boundary Map

Not provided.
