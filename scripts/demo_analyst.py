"""
demo_analyst.py — Production Analyst Demo (M010)

Demonstrates the full AnalystAgent document pipeline:
  1. Local PDF extraction (file_context_extractor, no cloud egress)
  2. Context pruning (ContextPruner, cosine similarity)
  3. PII scrubbing (PIIGate)
  4. LLM routing (UnifiedRouter via provider_factory)

Then switches LLM_PROVIDER and re-runs the same query.

Usage:
  # Use default provider (anthropic):
  python -m scripts.demo_analyst

  # Start with Gemini then switch to Ollama:
  LLM_PROVIDER=gemini python -m scripts.demo_analyst

  # Offline test with Ollama only:
  LLM_PROVIDER=ollama python -m scripts.demo_analyst
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

# Make sure the src tree is importable when run as a script
_repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_repo_root / "src"))

from mcp_agent_factory.agents.analyst import AnalystAgent, DocumentAnalysisTask
from mcp_agent_factory.agents.models import MCPContext

# ---------------------------------------------------------------------------
# Terminal colour helpers (no deps)
# ---------------------------------------------------------------------------

_BOLD = "\033[1m"
_DIM = "\033[2m"
_CYAN = "\033[96m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_RED = "\033[91m"
_RESET = "\033[0m"
_BLUE = "\033[94m"
_MAGENTA = "\033[95m"


def _h(text: str, colour: str = _CYAN) -> str:
    return f"{colour}{_BOLD}{text}{_RESET}"


def _dim(text: str) -> str:
    return f"{_DIM}{text}{_RESET}"


def _sep(char: str = "─", width: int = 72) -> str:
    return char * width


# ---------------------------------------------------------------------------
# Demo runner
# ---------------------------------------------------------------------------

_PDF_PATH = str(_repo_root / "data" / "samples" / "finance_q3_2024.pdf")
_QUERY = "Identify key KPIs and risk areas from the Q3 2024 financial report"


async def run_analysis(provider: str) -> None:
    os.environ["LLM_PROVIDER"] = provider
    print()
    print(_sep("═"))
    print(_h(f"  AnalystAgent Demo — Provider: {provider.upper()}", _MAGENTA))
    print(_sep("═"))

    ctx = MCPContext(tool_name="demo_analyst")
    agent = AnalystAgent()
    task = DocumentAnalysisTask(pdf_path=_PDF_PATH, query=_QUERY)

    # Phase 1: Local extraction
    print()
    print(_h("Phase 1: Local Extraction", _CYAN))
    print(_dim(f"  PDF: {_PDF_PATH}"))
    print(_dim(f"  Query: {_QUERY}"))
    print()

    t0 = time.perf_counter()
    try:
        result = await agent.analyze_document(task, ctx=ctx)
    except Exception as exc:  # noqa: BLE001
        print(f"{_RED}  ERROR: {exc}{_RESET}")
        print()
        print(_dim("  Tip: Ensure LLM provider credentials are set:"))
        print(_dim("    Anthropic → ANTHROPIC_API_KEY"))
        print(_dim("    Gemini    → GEMINI_API_KEY"))
        print(_dim("    Ollama    → start 'ollama serve' (no key needed)"))
        return

    elapsed = time.perf_counter() - t0

    # Print Phase 1 logs from context trace
    for line in ctx.trace:
        if "PDF" in line or "extracted" in line or "pruning" in line or "→" in line:
            print(f"  {_DIM}→{_RESET} {line}")

    # Token reduction stats
    chunks_before = result.chunks_before_pruning
    chunks_after = result.chunks_after_pruning
    print()
    print(f"  ContextPruner: {_YELLOW}{chunks_before} chunks{_RESET} → "
          f"{_GREEN}{chunks_after} relevant chunks{_RESET}")
    print(f"  Pages read: {result.pages_read}/{result.total_pages}")

    # Phase 2: Analysis output
    print()
    print(_h("Phase 2: Analysis", _CYAN))
    print()
    # Print LLM summary with light formatting
    for line in result.summary.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("#", "**", "##")):
            print(f"  {_BOLD}{stripped}{_RESET}")
        elif stripped.startswith(("*", "-", "•")):
            print(f"  {_GREEN}{stripped}{_RESET}")
        elif stripped[0].isdigit() and "." in stripped[:3]:
            print(f"  {_YELLOW}{stripped}{_RESET}")
        else:
            print(f"  {stripped}")

    # Phase 3: Metadata footer
    print()
    print(_h("Phase 3: Run Metadata", _CYAN))
    print()
    cost_str = f"${result.cost_usd:.4f}" if result.cost_usd else "n/a"
    print(f"  {_BOLD}[Provider]{_RESET}: {result.provider}")
    print(f"  {_BOLD}[Tokens]{_RESET}:   {result.input_tokens} in / {result.output_tokens} out")
    print(f"  {_BOLD}[Cost]{_RESET}:     {cost_str}")
    print(f"  {_BOLD}[Status]{_RESET}:   {_GREEN}Success{_RESET}")
    print(f"  {_BOLD}[Time]{_RESET}:     {elapsed:.2f}s")
    print()


async def main() -> None:
    initial_provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()

    # Map provider to a switch target
    switch_map = {
        "anthropic": "gemini",
        "gemini": "anthropic",
        "openai": "gemini",
        "ollama": "anthropic",
    }
    switch_to = switch_map.get(initial_provider, "gemini")

    print()
    print(_sep("═"))
    print(_h("  MCP Agent Factory — Production Analyst Demo", _BLUE))
    print(_sep("═"))
    print()
    print(f"  Document: {_dim(_PDF_PATH)}")
    print(f"  Initial provider:  {_YELLOW}{initial_provider.upper()}{_RESET}")
    print(f"  Switching to:      {_YELLOW}{switch_to.upper()}{_RESET}")

    # Run 1: initial provider
    await run_analysis(initial_provider)

    # Switch
    print(_sep())
    print(_h(f"  Switching LLM_PROVIDER: {initial_provider.upper()} → {switch_to.upper()}", _YELLOW))
    print(_sep())

    # Run 2: switched provider
    await run_analysis(switch_to)

    print(_sep("═"))
    print(_h("  Demo complete.", _GREEN))
    print(_sep("═"))
    print()


if __name__ == "__main__":
    asyncio.run(main())
