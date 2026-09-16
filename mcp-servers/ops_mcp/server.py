"""
MCP server exposing infrastructure tools for the maintenance agent: the
"build and maintain the web application" half of this project, as opposed
to postgres_mcp which is the business-data half.

Talks to the Docker daemon (via the mounted socket, see docker-compose.yml)
to inspect and restart sibling containers, and pings the backend's /health
endpoint. This mirrors the self-healing pattern used in the
wordpress-multi-agent-manager project, applied to this stack.

SECURITY NOTE: mounting /var/run/docker.sock gives this container
effectively root-equivalent control over the host's Docker daemon. That's
an acceptable, common tradeoff for a local self-healing demo, but it is
not something to expose beyond localhost or give an untrusted agent access
to in a real deployment — restart_service is scoped to an explicit
allow-list of this project's own container names for that reason.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import docker
import httpx
from mcp.server.fastmcp import FastMCP
from sqlalchemy import text

from shared.database import engine
from shared import models  # noqa: F401 — import registers tables on Base.metadata

mcp = FastMCP("ops-tools", host="0.0.0.0", port=8002)

BACKEND_HEALTH_URL = os.getenv("BACKEND_HEALTH_URL", "http://backend:8000/health")

# Only these containers may be restarted by the agent — never expand this
# to arbitrary container names supplied by the model at runtime.
MANAGED_SERVICES = {
    "backend": "dealer-backend",
    "postgres": "dealer-postgres",
    "postgres-mcp": "dealer-postgres-mcp",
}

_docker_client = None


def _docker() -> docker.DockerClient:
    global _docker_client
    if _docker_client is None:
        _docker_client = docker.from_env()
    return _docker_client


@mcp.tool()
def check_service_health() -> dict:
    """Check whether the web backend is responding, and whether the database is reachable."""
    result = {"backend": "unknown", "database": "unknown"}

    try:
        resp = httpx.get(BACKEND_HEALTH_URL, timeout=5.0)
        result["backend"] = "healthy" if resp.status_code == 200 else f"unhealthy (HTTP {resp.status_code})"
    except Exception as e:
        result["backend"] = f"unreachable: {e}"

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        result["database"] = "healthy"
    except Exception as e:
        result["database"] = f"unreachable: {e}"

    return result


@mcp.tool()
def get_container_status() -> list[dict]:
    """List the status (running/exited/etc.) of every managed container."""
    client = _docker()
    statuses = []
    for label, container_name in MANAGED_SERVICES.items():
        try:
            c = client.containers.get(container_name)
            statuses.append({"service": label, "container": container_name, "status": c.status})
        except docker.errors.NotFound:
            statuses.append({"service": label, "container": container_name, "status": "not found"})
    return statuses


@mcp.tool()
def get_recent_logs(service: str, lines: int = 50) -> str:
    """
    Get the last N log lines from a managed service. `service` must be one
    of: backend, postgres, postgres-mcp.
    """
    if service not in MANAGED_SERVICES:
        return f"Unknown service '{service}'. Must be one of: {list(MANAGED_SERVICES)}"
    client = _docker()
    try:
        container = client.containers.get(MANAGED_SERVICES[service])
        logs = container.logs(tail=lines).decode("utf-8", errors="replace")
        return logs
    except docker.errors.NotFound:
        return f"Container for '{service}' not found."


@mcp.tool()
def restart_service(service: str) -> str:
    """
    Restart a managed service's container. `service` must be one of:
    backend, postgres, postgres-mcp. Use this only after checking logs and
    confirming a restart is a reasonable fix (e.g. the process is hung or
    crash-looping), not as a first response to every anomaly.
    """
    if service not in MANAGED_SERVICES:
        return f"Refused: '{service}' is not in the managed allow-list ({list(MANAGED_SERVICES)})."
    client = _docker()
    try:
        container = client.containers.get(MANAGED_SERVICES[service])
        container.restart(timeout=10)
        return f"Restarted '{service}' ({MANAGED_SERVICES[service]})."
    except docker.errors.NotFound:
        return f"Container for '{service}' not found."


@mcp.tool()
def run_pending_migrations() -> str:
    """
    Ensure the database schema is up to date (creates any missing tables
    and the pgvector extension). Safe to call repeatedly — idempotent.
    """
    from shared.database import Base  # Base already has models' tables registered (see import above)
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(bind=engine)
    return "Schema is up to date (extension ensured, tables created if missing)."


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
