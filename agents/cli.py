"""
Interactive entrypoint for the agent layer.

    docker-compose run --rm agents python cli.py

Type requests like:
    find me a reliable family SUV under 30k miles
    I want to sell my 2018 Honda Civic, 60k miles, good condition, email me@x.com name Me
    what's a fair price for a 2019 Ford F-150 with 70k miles in good condition?
    is the site healthy?

Type 'exit' to quit.
"""
import asyncio

from orchestrator import DealerOrchestrator


async def main():
    print("Connecting to MCP servers and building agents...")
    orchestrator = await DealerOrchestrator.create()
    print("Ready. Type a request (or 'exit').\n")

    while True:
        try:
            request = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not request:
            continue
        if request.lower() in {"exit", "quit"}:
            break

        agent_used, response = await orchestrator.run(request)
        print(f"\n[routed to: {agent_used}]\n{response}\n")


if __name__ == "__main__":
    asyncio.run(main())
