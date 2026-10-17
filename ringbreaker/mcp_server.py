"""MCP server: exposes the graph tools so any MCP client (e.g. Claude) can investigate on its own.

Run:  python3 -m ringbreaker.mcp_server        (stdio transport)
Env:  RINGBREAKER_DB=path/to/ringbreaker.db    (embedded)  or  FALKORDB_HOST / FALKORDB_PORT (remote)
Load data first:  python3 -m ringbreaker load
"""
try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

from .agent import Investigator, explain
from .graph import connect
from .tools import Tools

mcp = _Server("ringbreaker")
_g = connect()
_t = Tools(_g)


@mcp.tool()
def find_suspicious_clusters(min_size: int = 3) -> dict:
    """Group accounts that share owners, devices or addresses (graph WCC). Start here."""
    return _t.identity_clusters(min_size)


@mcp.tool()
def profile_accounts(accounts: list[str]) -> dict:
    """Account age and KYC status for a set of account ids."""
    return _t.cluster_profile(accounts)


@mcp.tool()
def shared_identity_links(accounts: list[str]) -> dict:
    """Devices and addresses shared between the given accounts, with the path through the graph."""
    return _t.shared_identity(accounts)


@mcp.tool()
def detect_money_cycles(accounts: list[str], max_len: int = 6) -> dict:
    """Find funds that return to the account that sent them."""
    return _t.money_cycles(accounts, max_len)


@mcp.tool()
def find_funnel_hub(accounts: list[str]) -> dict:
    """Find a collector account that many of the given accounts pay into (uses PageRank)."""
    return _t.funnel_hub(accounts)


@mcp.tool()
def expand_via_money(accounts: list[str], young_days: int = 90) -> dict:
    """Young accounts outside the set that transact with it."""
    return _t.money_neighbours(accounts, young_days)


@mcp.tool()
def merchant_exposure(accounts: list[str]) -> dict:
    """Merchants settling into the given accounts, and the customers who paid them."""
    return _t.merchant_exposure(accounts)


@mcp.tool()
def run_full_investigation() -> str:
    """Let the built-in investigator sweep every cluster, act, and return explanations."""
    return "\n\n".join(explain(c) for c in Investigator(_g).sweep())


@mcp.tool()
def freeze_accounts(case_id: str, accounts: list[str], reason: str) -> dict:
    """ACTION: freeze accounts and record a Case node linking them. Only call after evidence is gathered."""
    return _t.record_case(case_id, "FREEZE", 0, accounts, [reason], [])


if __name__ == "__main__":
    mcp.run()
