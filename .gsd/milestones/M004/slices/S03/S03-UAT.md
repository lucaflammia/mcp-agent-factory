# S03: Client Bridge \u2014 PKCE + Token Cache + SSE Consumption — UAT

**Milestone:** M004
**Written:** 2026-03-30T06:52:54.779Z

## UAT: Client Bridge\n\n`pytest tests/test_m004_client_bridge.py -v` \u2192 18 passed\n\n```bash\n# CLI demo (requires running gateway on :8000)\nexport GATEWAY_TOKEN=$(python -c \"...issue token...\")\npython -m mcp_agent_factory.bridge\n```"
