# AutoMarket — Agentic Car Dealer Platform

A web application for an online car marketplace — customers list cars to sell, other
customers buy them — backed by Postgres, with a multi-agent system (RAG + MCP + LangGraph)
that both runs the business logic and keeps the platform itself healthy.

## Why this exists

Most "agentic AI" demos are a single chatbot in front of an API. This project is closer to
what a real platform team would build: a normal web app with a normal database, plus a
tool-using multi-agent layer that (a) handles the tasks that genuinely benefit from language
understanding — matching a buyer's vague request to the right car, extracting structured data
from a seller's messy description, pricing a car from comparables — and (b) keeps the
*infrastructure itself* running, self-checking health and self-healing rather than paging a
human for everything.

The web app works completely standalone (plain CRUD + a semantic search box) — the agents are
an additional layer on top of the same database, not a requirement to use the site.

## Architecture

```
                     ┌─────────────────────┐
   Customers ──────▶ │   Web App (FastAPI)  │──────┐
                     │   + Jinja2 templates │      │
                     └─────────────────────┘      │
                                                     ▼
┌──────────────────────────────────────────────────────────┐
│                    Postgres + pgvector                    │
│      users · car_listings (+ embedding) · transactions    │
└──────────────────────────────────────────────────────────┘
          ▲                                    ▲
          │ tools                              │ tools
┌───────────────────┐                ┌───────────────────┐
│   postgres-mcp     │                │      ops-mcp       │
│ search / create /   │                │ health / logs /    │
│ price comparables   │                │ restart / migrate   │
└───────────────────┘                └───────────────────┘
          ▲                                    ▲
          │                                    │
┌──────────────────────────────────────────────────────────┐
│                  LangGraph Orchestrator                    │
│                                                              │
│   request ──▶ [router] ──▶ buyer_assistant  (RAG search)    │
│                        ├──▶ listing_intake   (extract+create)│
│                        ├──▶ pricing          (comparables)   │
│                        └──▶ maintenance      (self-healing)  │
└──────────────────────────────────────────────────────────┘
```

**Two MCP servers, two different jobs:**
- `postgres-mcp` — business-data tools: semantic (RAG) and filtered listing search, comparable
  listings for pricing, creating/updating listings. Used by the buyer assistant, listing
  intake, and pricing agents.
- `ops-mcp` — infrastructure tools: health checks, container status, logs, restarting a
  service, running schema migrations. Used only by the maintenance agent.

Business agents cannot touch infrastructure and the maintenance agent cannot touch listing
data — they're given disjoint tool sets at construction time, not just told not to cross the
line in a prompt.

**Four agents, one router:**
| Agent | Tools | What it does |
|---|---|---|
| `buyer_assistant` | postgres-mcp | Natural-language car search via RAG (pgvector cosine similarity over listing embeddings) plus structured filtering |
| `listing_intake` | postgres-mcp | Extracts structured fields from a seller's free-text description, moderates content, creates the listing — or asks a clarifying question if required info is missing |
| `pricing` | postgres-mcp | Pulls comparable listings and reasons about a fair price range, rather than inventing a number |
| `maintenance` | ops-mcp | Checks system health, investigates logs before acting, restarts a service only when justified, runs idempotent migrations — the "build and maintain" half of this project |

A LangGraph `StateGraph` routes each incoming request to the right agent via a small
classifier node, and a separate always-on loop (`agents/watch.py`) runs the maintenance agent
on a timer with no human input at all — genuine autonomous self-healing, not just a chat tool.

## RAG design

Listing embeddings are generated with a **local** `sentence-transformers` model
(`all-MiniLM-L6-v2`, 384-dim) stored directly in Postgres via `pgvector`, rather than a hosted
embedding API. This was a deliberate tradeoff: it keeps the entire search/RAG path free and
runnable offline, while the agents that need actual language *reasoning* (understanding a
seller's description, deciding on a price) still call Claude. Search quality is good enough
for this dataset size; at real scale you'd likely swap in a hosted embedding model and an ANN
index (pgvector `ivfflat`/`hnsw`) instead of exact cosine search.

## Tech stack

`FastAPI` · `Postgres` + `pgvector` · `SQLAlchemy` · `sentence-transformers` (local RAG
embeddings) · `LangGraph` · `LangChain` (Anthropic) · `Model Context Protocol` (`mcp`,
`langchain-mcp-adapters`) · `Docker` / `Docker Compose`

## Project structure

```
.
├── docker-compose.yml
├── shared/                    # DB models + embedding helper, shared by the web app and MCP servers
│   ├── database.py
│   ├── models.py
│   └── embeddings.py
├── backend/                   # The web application
│   ├── app/
│   │   ├── main.py            # Routes: home, listing detail, sell form, semantic search
│   │   ├── schemas.py
│   │   ├── templates/
│   │   └── static/
│   └── scripts/init_db.py     # Schema creation + demo data seed
├── mcp-servers/
│   ├── postgres_mcp/server.py # Business-data tools (search, create, price comparables)
│   └── ops_mcp/server.py      # Infra tools (health, logs, restart, migrate)
└── agents/
    ├── orchestrator.py        # LangGraph StateGraph: router + 4 agents
    ├── prompts.py              # Each agent's system prompt / policy
    ├── cli.py                  # Interactive REPL to try buyer/seller/pricing requests
    └── watch.py                 # Autonomous maintenance loop (no human in the loop)
```

## Quick start

Requires Docker, Docker Compose, and an Anthropic API key.

```bash
git clone <this-repo-url>
cd auto-dealer-agentic-platform
cp .env.example .env        # fill in ANTHROPIC_API_KEY

docker-compose up -d postgres backend postgres-mcp ops-mcp
```

Browse the app at `http://localhost:8000` — it comes pre-seeded with 10 demo listings, so
semantic search works immediately (try "reliable family SUV under 30k miles").

Talk to the agents interactively:
```bash
docker-compose run --rm agents python cli.py
> find me a cheap first car for a teenager
> I want to sell my 2019 Subaru Outback, 33k miles, excellent condition, no accidents. email me@x.com name Jane
> what's a fair price for a 2018 Ford F-150 with 65k miles in good condition?
```

Run the autonomous self-healing loop:
```bash
docker-compose run --rm agents python watch.py --interval 30
# in another terminal, break something on purpose:
docker stop dealer-backend
# watch the maintenance agent notice, investigate, and restart it
```

Inspect the database directly: `http://localhost:8081` (Adminer — system Postgres, server
`postgres`, user/pass `dealer`/`dealer`, database `car_dealer`).

## Testing notes

This is a scaffold, not a finished product — I built out the full architecture and verified
the plumbing (the MCP servers actually connect, the LangGraph graph actually routes and
returns through real agent nodes, the DB models are shared rather than duplicated) but the
individual agent *prompts* haven't been tuned against real edge cases yet. I'd treat the
prompts in `agents/prompts.py` as a first draft to iterate on with real usage, not a finished
policy.

## Security notes

`ops-mcp` mounts the host's Docker socket so the maintenance agent can inspect and restart
sibling containers — that's effectively root-equivalent access to the Docker daemon. Two
things mitigate this for a demo: `restart_service` only accepts service names from an explicit
allow-list (`MANAGED_SERVICES` in `mcp-servers/ops_mcp/server.py`), and the database container
is deliberately excluded from that allow-list so the agent can never restart it. This is an
acceptable tradeoff for a local portfolio project; I would not expose `ops-mcp` outside
localhost or hand an agent this level of access in a real deployment without a much narrower,
purpose-built API instead of raw Docker control.

## What I'd improve with more time

- Real database migrations (Alembic) instead of `create_all` — fine for a demo, not for schema evolution in production
- An `ivfflat`/`hnsw` index on the embedding column, and a hosted embedding model, if the listing volume grew past a few thousand rows
- Automated tests for the agents (e.g. golden-set evals for the router's classification and the listing intake agent's extraction accuracy)
- A transactions/checkout flow — buying a car is currently modeled in the schema but not wired into the UI or agents yet
- Rate limiting and auth (the web app currently has no login — anyone can list or "buy" as any email)
- Swap `docker.sock` access in `ops-mcp` for a narrower purpose-built control API before this pattern went anywhere near production

## Related projects

See also [`sales_agent`](https://github.com/mortezaahmadian/sales_agent) for another
LangGraph + RAG multi-agent system, and
[`wordpress-multi-agent-manager`](https://github.com/mortezaahmadian/wordpress-multi-agent-manager)
for the self-healing infrastructure pattern `ops-mcp`/the maintenance agent here builds on.
 git add README.md git commit -m test commit git push



