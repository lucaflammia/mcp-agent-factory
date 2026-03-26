# M001: Core Orchestrator and MCP Foundation

**Gathered:** 2026-03-26
**Status:** Ready for planning

## Project Description
An industrial-grade Multi-Agent Orchestrator using the Model Context Protocol (MCP) as its universal connection layer. Establishes a standardized "system nervous" that allows autonomous agents to perceive, reason, and act within a secure enterprise environment, integrating specific course materials as the foundational "Theory-to-Action" bridge.

## Why This Milestone
To build the core infrastructure that allows agents to communicate and act intelligently, directly leveraging the theoretical foundation of the Fargin Curriculum.

## User-Visible Outcome
### When this milestone is complete, the user can:
*   See a basic orchestrator route tasks between simulated agents via MCP.
*   Observe the initial implementation of the ReAct pattern.
*   Understand the architectural basis for security and privacy in agent interactions.

### Entry point / environment
- Entry point: Local development environment.
- Environment: Local development environment.
- Live dependencies involved: None initially, focusing on internal orchestration and simulated agents.

## Completion Class

- Contract complete means: Unit tests for MCP, ReAct loop, and curriculum mapping.
- Integration complete means: Basic end-to-end routing between simulated agents.
- Operational complete means: N/A.
- UAT / human verification: N/A for this foundational milestone.

## Final Integrated Acceptance

To call this milestone complete, we must prove:

- A basic orchestrator successfully routes a simple task from a simulated agent to another simulated agent via MCP, demonstrating the core communication flow.

## Risks and Unknowns

- **Complexity of MCP integration:** Ensuring seamless communication and error handling between diverse agents and the orchestrator could be complex. — *Why it matters:* Failure here blocks all multi-agent functionality.
- **Theory-to-Action Mapping:** Translating the Fargin Curriculum's abstract concepts into concrete, executable agent logic and MCP server configurations requires careful interpretation. — *Why it matters:* If the theory isn't accurately implemented, the core value proposition is lost.
- **Performance of local inference:** Evaluating and integrating local models for sensitive workloads while maintaining acceptable performance. — *Why it matters:* This is a core requirement for privacy and production-readiness.

## Existing Codebase / Prior Art

- This is a new project. The primary prior art is the Fargin Curriculum materials located in `/home/luca/Documents/Misc/Fargin/CorsoAgentiAI&ProtocolloMCP/Teoria`.

> See `.gsd/DECISIONS.md` for all architectural and pattern decisions — it is an append-only register; read it during planning, append to it during execution.

## Relevant Requirements

- R001 — Core Orchestration Engine
- R002 — MCP Communication Protocol
- R003 — ReAct Pattern Implementation
- R004 — Fargin Curriculum Integration
- R005 — Schema Validation for Security
- R006 — Privacy-First Design

## Scope

### In Scope

- Core orchestrator implementation.
- MCP client and server components.
- Basic ReAct loop demonstration.
- Integration of Fargin Curriculum principles.
- Design of security and privacy architecture.

### Out of Scope / Non-Goals

- Full agent implementations beyond basic simulations.
- Complex ReAct loop scenarios.
- Specific MCP server integrations (beyond basic simulation).
- Advanced local model optimization and benchmarking.

## Technical Constraints

- Adherence to JSON-RPC 2.0 for MCP communication.
- Mandatory schema validation for all tool arguments and messages.
- Prioritization of privacy-first execution, with considerations for on-device inference.

## Integration Points

- Fargin Curriculum materials located in `/home/luca/Documents/Misc/Fargin/CorsoAgentiAI&ProtocolloMCP/Teoria`.
- Potential for future MCP server integrations.

## Open Questions

- How to best represent the Fargin Curriculum's theoretical modules in a way that agents can directly consume and apply.
