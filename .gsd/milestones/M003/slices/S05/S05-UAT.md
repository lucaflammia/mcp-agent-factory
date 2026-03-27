# S05: LangChain Bridge + OAuth Middleware — UAT

**Milestone:** M003
**Written:** 2026-03-27T11:28:56.254Z

## UAT: LangChain Bridge + OAuth Middleware

### Setup
```bash
pip install -e .
python -m pytest tests/test_langchain_bridge.py -v
```

### Test Cases

| # | Scenario | Expected | Result |
|---|----------|----------|--------|
| 1 | OAuthMiddleware.inject() adds Authorization header | Bearer token present | ✅ |
| 2 | MCPGatewayClient.list_tools() returns tools list | echo tool present | ✅ |
| 3 | MCPGatewayClient.call_tool('echo', {'text': 'hello bridge'}) | text returned | ✅ |
| 4 | Two consecutive list_tools() calls | factory called once (cache hit) | ✅ |

Full suite: 157 tests passed.

