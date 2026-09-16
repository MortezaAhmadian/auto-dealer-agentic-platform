"""
The multi-agent orchestrator.

A router node classifies each incoming request, then hands it off to one of
four specialist agents, each built with langgraph's create_react_agent and
bound only to the MCP tools it actually needs:

  buyer_assistant  -> postgres-mcp tools (RAG semantic + filtered search)
  listing_intake   -> postgres-mcp tools (create_listing, etc.)
  pricing          -> postgres-mcp tools (get_comparable_listings)
  maintenance      -> ops-mcp tools (health checks, logs, restart, migrate)

Business agents and the maintenance agent are deliberately given disjoint
tool sets — the buyer assistant has no way to restart a container, and the
maintenance agent has no way to touch listing data. Least-privilege by
construction, not by prompt instruction alone.
"""
import os

from langchain_anthropic import ChatAnthropic
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import create_react_agent

from state import OrchestratorState, RequestType
from prompts import (
    ROUTER_PROMPT,
    BUYER_ASSISTANT_PROMPT,
    LISTING_INTAKE_PROMPT,
    PRICING_PROMPT,
    MAINTENANCE_PROMPT,
)

POSTGRES_MCP_URL = os.getenv("POSTGRES_MCP_URL", "http://postgres-mcp:8001/mcp")
OPS_MCP_URL = os.getenv("OPS_MCP_URL", "http://ops-mcp:8002/mcp")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5")

MCP_SERVERS = {
    "dealer_data": {"url": POSTGRES_MCP_URL, "transport": "streamable_http"},
    "dealer_ops": {"url": OPS_MCP_URL, "transport": "streamable_http"},
}

POSTGRES_TOOL_NAMES = {
    "search_listings_semantic",
    "search_listings_filtered",
    "get_listing",
    "get_comparable_listings",
    "create_listing",
    "update_listing_status",
    "get_user_listings",
}
OPS_TOOL_NAMES = {
    "check_service_health",
    "get_container_status",
    "get_recent_logs",
    "restart_service",
    "run_pending_migrations",
}


class DealerOrchestrator:
    """Owns the compiled LangGraph graph and the MCP client's lifetime."""

    def __init__(self, llm: ChatAnthropic, agents: dict):
        self._llm = llm
        self._agents = agents
        self._graph = self._build_graph()

    @classmethod
    async def create(cls) -> "DealerOrchestrator":
        client = MultiServerMCPClient(MCP_SERVERS)
        all_tools = await client.get_tools()

        postgres_tools = [t for t in all_tools if t.name in POSTGRES_TOOL_NAMES]
        ops_tools = [t for t in all_tools if t.name in OPS_TOOL_NAMES]

        if not postgres_tools:
            raise RuntimeError(
                "No postgres-mcp tools discovered — is the postgres-mcp service running "
                f"and reachable at {POSTGRES_MCP_URL}?"
            )
        if not ops_tools:
            raise RuntimeError(
                "No ops-mcp tools discovered — is the ops-mcp service running "
                f"and reachable at {OPS_MCP_URL}?"
            )

        llm = ChatAnthropic(model=CLAUDE_MODEL, temperature=0)

        agents = {
            "buy": create_react_agent(llm, postgres_tools, prompt=BUYER_ASSISTANT_PROMPT),
            "sell": create_react_agent(llm, postgres_tools, prompt=LISTING_INTAKE_PROMPT),
            "price": create_react_agent(llm, postgres_tools, prompt=PRICING_PROMPT),
            "maintain": create_react_agent(llm, ops_tools, prompt=MAINTENANCE_PROMPT),
        }
        return cls(llm, agents)

    def _build_graph(self):
        graph = StateGraph(OrchestratorState)
        graph.add_node("route", self._route_node)
        for key, agent in self._agents.items():
            graph.add_node(key, self._make_agent_node(key, agent))

        graph.set_entry_point("route")
        graph.add_conditional_edges(
            "route",
            lambda state: state["request_type"],
            {key: key for key in self._agents},
        )
        for key in self._agents:
            graph.add_edge(key, END)

        return graph.compile()

    async def _route_node(self, state: OrchestratorState) -> dict:
        result = await self._llm.ainvoke(
            [("system", ROUTER_PROMPT), ("human", state["request"])]
        )
        category = result.content.strip().lower()
        if category not in self._agents:
            category = "buy"
        return {"request_type": category}

    @staticmethod
    def _make_agent_node(key: str, agent):
        async def node(state: OrchestratorState) -> dict:
            result = await agent.ainvoke({"messages": [("user", state["request"])]})
            return {"response": result["messages"][-1].content}

        return node

    async def run(self, request: str) -> tuple[RequestType, str]:
        """Runs one request through the graph, returning (which agent handled it, its reply)."""
        final_state = await self._graph.ainvoke(
            {"request": request, "request_type": "buy", "response": ""}
        )
        return final_state["request_type"], final_state["response"]

    async def run_maintenance_check(self) -> str:
        """
        Invokes the maintenance agent directly, bypassing the router. Used by
        watch.py for the autonomous health-check loop, where the request is
        always the same fixed task rather than user-typed text.
        """
        agent = self._agents["maintain"]
        result = await agent.ainvoke(
            {"messages": [("user", "Check system health and take corrective action if needed.")]}
        )
        return result["messages"][-1].content
