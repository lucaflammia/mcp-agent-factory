---
estimated_steps: 1
estimated_files: 2
skills_used: []
---

# T01: Demo script and integration proof

Write scripts/demo_analyst.py: three-phase terminal output with live provider switch. Add data/samples/finance_q3_2024.pdf sample.

## Inputs

- `src/mcp_agent_factory/agents/analyst.py`

## Expected Output

- `scripts/demo_analyst.py`
- `data/samples/finance_q3_2024.pdf`

## Verification

python scripts/demo_analyst.py --dry-run 2>&1 | tail -3

## Observability Impact

Three-phase terminal output showing token reduction and provider footer
