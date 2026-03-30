# S01: SSE /v1 Endpoints + Connected Event — UAT

**Milestone:** M004
**Written:** 2026-03-30T06:47:28.552Z

## UAT: SSE /v1 Endpoints\n\n### Manual curl test\n```bash\ncurl -N http://localhost:8000/sse/v1/events?topic=agent.events\n# Expected: event: connected\\ndata: {\"topic\": \"agent.events\"}\\n\\n\n# Stays open — keepalive events every 30s\n```\n\n### Automated\n`pytest tests/test_m004_sse.py -v` → 9 passed"
