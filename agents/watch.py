"""
Autonomous "build and maintain" loop: runs the maintenance agent on a fixed
schedule with no human in the loop, so the platform can self-heal without
anyone watching it.

    docker-compose run --rm agents python watch.py
    docker-compose run --rm agents python watch.py --interval 30

Each cycle: check health -> if something's wrong, investigate logs -> fix if
safe (restart a non-database service, or run a migration) -> report. See
prompts.MAINTENANCE_PROMPT for the exact policy the agent follows, and
mcp-servers/ops_mcp/server.py's MANAGED_SERVICES allow-list for what it's
permitted to touch.
"""
import argparse
import asyncio
from datetime import datetime, timezone

from orchestrator import DealerOrchestrator


async def main(interval_seconds: int):
    print("Connecting to MCP servers and building the maintenance agent...")
    orchestrator = await DealerOrchestrator.create()
    print(f"Watching. Checking every {interval_seconds}s. Ctrl+C to stop.\n")

    while True:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            report = await orchestrator.run_maintenance_check()
        except Exception as e:
            report = f"Maintenance check itself failed: {e}"
        print(f"[{timestamp}] {report}\n{'-' * 60}")
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=int, default=60, help="Seconds between health checks")
    args = parser.parse_args()
    asyncio.run(main(args.interval))
