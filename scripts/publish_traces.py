#!/usr/bin/env python3
"""
Publish sample MCP execution traces to Kafka for the PromptOptimizer to consume.

Usage:
    python scripts/publish_traces.py --bootstrap kafka:9092 --topic mcp-traces --count 20
"""
import argparse
import asyncio
import json
import logging
import time
from dataclasses import asdict

from mcp_agent_factory.optimizer import TraceRecord

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def publish_traces(
  bootstrap_servers: str,
  topic: str,
  count: int = 20,
) -> None:
  """Publish synthetic trace records to Kafka."""
  try:
    from aiokafka import AIOKafkaProducer  # type: ignore[import]
  except ImportError:
    logger.error("aiokafka not installed — install with: pip install aiokafka")
    return

  producer = AIOKafkaProducer(
    bootstrap_servers=bootstrap_servers,
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
  )

  try:
    await producer.start()
    logger.info("Connected to Kafka at %s", bootstrap_servers)

    # Generate and publish sample traces
    phases = ["plan", "execute", "evaluate"]
    roles = ["actor", "critic"]

    for i in range(count):
      phase = phases[i % len(phases)]
      role = roles[i % len(roles)]

      # Vary scores: ~30% failures for realistic optimization opportunities
      score = 0.4 if i % 3 == 0 else 0.9

      trace = TraceRecord(
        trace_id=f"trace-{int(time.time())}-{i:04d}",
        task=f"Sample task {i}: {phase} phase execution",
        phase=phase,
        prompt_template=(
          f"You are the {role} agent handling {phase}. "
          "Complete the task accurately and thoroughly."
        ),
        actor_output=f"Output for task {i}: plan completed with {3 + i} steps",
        evaluation_score=score,
        evaluation_findings=[
          "Output too brief",
          "Missing context field",
        ] if score < 0.6 else [],
        timestamp=time.time(),
        metadata={
          "role": role,
          "source": "publish_traces.py",
          "env": "dev",
        },
      )

      # Publish to Kafka
      await producer.send_and_wait(
        topic,
        value=trace.model_dump(),
      )
      logger.info(
        "Published trace %d/%d: %s/%s score=%.2f",
        i + 1, count, role, phase, score,
      )

    logger.info("All %d traces published to topic %r", count, topic)

  except Exception as exc:
    logger.error("Failed to publish traces: %s", exc)
    raise
  finally:
    await producer.stop()


async def main() -> None:
  parser = argparse.ArgumentParser(
    description="Publish sample MCP execution traces to Kafka"
  )
  parser.add_argument(
    "--bootstrap",
    default="kafka:9092",
    help="Kafka bootstrap servers (default: kafka:9092)",
  )
  parser.add_argument(
    "--topic",
    default="mcp-traces",
    help="Kafka topic name (default: mcp-traces)",
  )
  parser.add_argument(
    "--count",
    type=int,
    default=20,
    help="Number of traces to publish (default: 20)",
  )
  args = parser.parse_args()

  await publish_traces(
    bootstrap_servers=args.bootstrap,
    topic=args.topic,
    count=args.count,
  )


if __name__ == "__main__":
    asyncio.run(main())
