---
estimated_steps: 1
estimated_files: 2
skills_used: []
---

# T01: Implement AnalystAgent document pipeline

Add analyze_document() to AnalystAgent: extract → prune → scrub → route pipeline using file_context_extractor, ContextPruner, and UnifiedRouter.

## Inputs

- `src/mcp_agent_factory/agents/analyst.py`
- `src/mcp_agent_factory/knowledge/pdf_tool.py`

## Expected Output

- `AnalystAgent.analyze_document()`
- `DocumentAnalysisTask`
- `DocumentAnalysisResult`

## Verification

pytest tests/ -q --tb=no -k "analyst" 2>&1 | tail -3

## Observability Impact

Pipeline phase logging via EventLog
