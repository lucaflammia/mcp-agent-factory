# Decisions Register

<!-- Append-only. Never edit or remove existing rows.
     To reverse a decision, add a new row that supersedes it.
     Read this file at the start of any planning or research phase. -->

| # | When | Scope | Decision | Choice | Rationale | Revisable? | Made By |
|---|------|-------|----------|--------|-----------|------------|---------|
| D001 |  | implementation | GSD Framework for prototyping | Use GSD for rapid MVP development | Maximizes efficiency and speed. | Yes | agent |
| D002 |  | architecture | Slice ordering for M001 | S01 (MCP lifecycle) → S02 (ReAct loop) → S03 (schema + privacy); S02 and S03 both depend on S01 but are independent of each other | S01 is the highest-risk slice because a broken STDIO transport or missed capability negotiation silently breaks all downstream work. Proving the full MCP lifecycle first gives S02 and S03 a stable, tested channel to build on. S03 is structural hardening on top of existing handlers so it carries the least risk and can run in parallel with S02 if needed. | Yes | agent |
| D003 |  | implementation | MCPOrchestrator connect() design | connect() performs the initialize handshake internally; _rpc() uses single-outstanding-request pattern | Callers get a ready client immediately after connect() with no extra ceremony. Single-outstanding-request simplifies the implementation at the cost of concurrency — acceptable for the current synchronous test harness. | Yes | agent |
