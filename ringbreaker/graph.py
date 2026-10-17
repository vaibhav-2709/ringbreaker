"""Load the banking dataset into FalkorDB (embedded via falkordblite, or a remote FalkorDB)."""
import os
from collections import defaultdict

from .data import generate

GRAPH_NAME = "bank"
HIDDEN_PROPS = {"shell", "settles_via"}  # ground-truth hints that the agent must NOT see


def connect(path=None):
    """Remote FalkorDB if FALKORDB_HOST is set, otherwise an embedded instance on disk."""
    host = os.environ.get("FALKORDB_HOST")
    if host:
        from falkordb import FalkorDB
        db = FalkorDB(host=host, port=int(os.environ.get("FALKORDB_PORT", "6379")))
    else:
        from redislite.falkordb_client import FalkorDB
        db = FalkorDB(path or os.environ.get("RINGBREAKER_DB", "ringbreaker.db"))
    return db.select_graph(GRAPH_NAME)


def _clean(props):
    return {k: v for k, v in props.items() if k not in HIDDEN_PROPS}


def load(g, n_legit=420, seed=7):
    try:
        g.delete()
    except Exception:
        pass
    nodes, edges, truth = generate(n_legit=n_legit, seed=seed)

    for label in nodes:
        g.query(f"CREATE INDEX FOR (n:{label}) ON (n.id)")

    for label, rows in nodes.items():
        rows = [_clean(r) for r in rows]
        for i in range(0, len(rows), 400):
            g.query(f"UNWIND $rows AS r CREATE (n:{label}) SET n = r", {"rows": rows[i:i + 400]})

    grouped = defaultdict(list)
    for sl, sid, rel, dl, did in edges:
        grouped[(sl, rel, dl)].append({"s": sid, "d": did})
    for (sl, rel, dl), rows in grouped.items():
        for i in range(0, len(rows), 400):
            g.query(
                f"UNWIND $rows AS r MATCH (a:{sl} {{id: r.s}}), (b:{dl} {{id: r.d}}) CREATE (a)-[:{rel}]->(b)",
                {"rows": rows[i:i + 400]},
            )

    # Derived account->account money edge, keeps the txn id so every hop stays traceable.
    g.query(
        """MATCH (a:Account)-[:FROM]->(t:Txn)-[:TO]->(b:Account)
           CREATE (a)-[:SENT {txn: t.id, amount: t.amount, ts: t.ts}]->(b)"""
    )
    return truth


if __name__ == "__main__":
    g = connect()
    truth = load(g)
    print(g.query("MATCH (n) RETURN count(n)").result_set, g.query("MATCH ()-[r]->() RETURN count(r)").result_set)
    print({k: len(v) for k, v in truth.items()})
