# S04: LibrarianAgent + Gateway Tool + SSE Events — UAT

**Milestone:** M005
**Written:** 2026-03-31T11:30:44.899Z

## S04 UAT: LibrarianAgent + Gateway Tool + SSE Events

### Setup
```bash
PYTHONPATH=src pytest tests/test_s04.py -v
```

### Checks

| # | Scenario | Expected | Result |
|---|----------|----------|--------|
| 1 | query_knowledge_base on populated store | returns list with text+score dicts | ✅ |
| 2 | query_knowledge_base on empty store | returns [] | ✅ |
| 3 | LibrarianAgent.run produces RetrievalResult | session_key=task.id, chunks>=1, 'Retrieved' in summary | ✅ |
| 4 | TOOLS list includes query_knowledge_base | name present | ✅ |
| 5 | Gateway dev-mode call returns chunks | non-empty text content | ✅ |
| 6 | Gateway call emits knowledge.retrieved on bus | message topic and owner_id correct | ✅ |
| 7 | Cross-tenant isolation | 'alice' chunks not returned for 'dev' owner | ✅ |

All 7 checks pass.

