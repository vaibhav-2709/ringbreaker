"""Graph tools the investigator agent can choose between.

Every tool returns {"tool", "summary", "data", "evidence"}.
`evidence` is a list of human-readable graph paths, e.g.
    ACCT0421 -[OWNS]<- CUST0421 -[USES]-> DEV0390 <-[USES]- CUST0425 -[OWNS]-> ACCT0425
so each decision can be traced back to real nodes and edges.
"""
from collections import defaultdict

IDENTITY_LABELS = ["Account", "Customer", "Device", "Address"]
IDENTITY_RELS = ["OWNS", "USES", "LIVES_AT"]


def _res(tool, summary, data=None, evidence=None):
    return {"tool": tool, "summary": summary, "data": data or {}, "evidence": evidence or []}


class Tools:
    def __init__(self, g):
        self.g = g
        self._pr = None

    def q(self, cypher, params=None):
        return self.g.query(cypher, params or {}).result_set

    # ---------------------------------------------------------------- discovery
    def identity_clusters(self, min_size=3):
        """Weakly connected components over who-owns-what / who-uses-what / who-lives-where."""
        rows = self.q(
            """CALL algo.WCC({nodeLabels:$labels, relationshipTypes:$rels})
               YIELD node, componentId
               WITH componentId AS cid, collect(CASE WHEN 'Account' IN labels(node) THEN node.id END) AS accts
               RETURN cid, [a IN accts WHERE a IS NOT NULL] AS accounts""",
            {"labels": IDENTITY_LABELS, "rels": IDENTITY_RELS},
        )
        clusters = [sorted(accts) for _, accts in rows if len(accts) >= min_size]
        clusters.sort(key=len, reverse=True)
        return _res("identity_clusters",
                    f"WCC over identity links found {len(clusters)} cluster(s) with >= {min_size} accounts",
                    {"clusters": clusters})

    # ---------------------------------------------------------------- profiling
    def cluster_profile(self, accounts):
        rows = self.q(
            """MATCH (c:Customer)-[:OWNS]->(a:Account) WHERE a.id IN $ids
               RETURN a.id, a.age_days, c.kyc, c.id""",
            {"ids": accounts},
        )
        ages = [r[1] for r in rows]
        pending = sum(1 for r in rows if r[2] != "verified")
        young = sum(1 for a in ages if a < 90)
        n = max(len(rows), 1)
        return _res(
            "cluster_profile",
            f"{len(rows)} accounts, median age {sorted(ages)[len(ages)//2]}d, {young} younger than 90d, {pending} with unverified KYC",
            {"n": len(rows), "young_share": young / n, "pending_kyc_share": pending / n,
             "median_age": sorted(ages)[len(ages) // 2], "young": young, "pending": pending},
        )

    def shared_identity(self, accounts):
        """Which devices / addresses tie two or more of these accounts together, and via which owners."""
        out, ev = {"devices": {}, "addresses": {}}, []
        for kind, rel, label in (("devices", "USES", "Device"), ("addresses", "LIVES_AT", "Address")):
            rows = self.q(
                f"""MATCH (a:Account)<-[:OWNS]-(c:Customer)-[:{rel}]->(x:{label}) WHERE a.id IN $ids
                    RETURN x.id, collect(DISTINCT a.id), collect(DISTINCT c.id)""",
                {"ids": accounts},
            )
            for xid, accts, custs in rows:
                if len(accts) >= 2:
                    out[kind][xid] = accts
                    first, rest = accts[0], accts[1:]
                    for other in rest:
                        ev.append(f"{first} <-[OWNS]- owner -[{rel}]-> {xid} <-[{rel}]- owner -[OWNS]-> {other}")
        n_dev, n_addr = len(out["devices"]), len(out["addresses"])
        return _res("shared_identity",
                    f"{n_dev} device(s) and {n_addr} address(es) are shared across accounts in the cluster", out, ev)

    def money_cycles(self, accounts, max_len=6):
        """Funds that return to their origin (carousel / round-tripping)."""
        rows = self.q(
            f"""MATCH p=(a:Account)-[:SENT*3..{max_len}]->(a) WHERE a.id IN $ids
                WITH DISTINCT [n IN nodes(p) | n.id] AS path
                RETURN path LIMIT 50""",
            {"ids": accounts},
        )
        seen, cycles = set(), []
        for (path,) in rows:
            key = frozenset(path[:-1])
            if key in seen:
                continue
            seen.add(key)
            cycles.append(path)
        ev = [" -[SENT]-> ".join(c) for c in cycles]
        return _res("money_cycles",
                    f"{len(cycles)} distinct money cycle(s)" if cycles else "no money cycles", {"cycles": cycles}, ev)

    def funnel_hub(self, accounts):
        """Is there a collector inside the cluster that many members pay into? Uses global PageRank + local in-degree."""
        if self._pr is None:
            rows = self.q("CALL algo.pageRank('Account','SENT') YIELD node, score RETURN node.id, score")
            self._pr = {r[0]: r[1] for r in rows}
        rows = self.q(
            """MATCH (s:Account)-[r:SENT]->(h:Account) WHERE s.id IN $ids AND h.id IN $ids
               RETURN h.id, count(DISTINCT s.id) AS senders, sum(r.amount) AS total
               ORDER BY senders DESC, total DESC LIMIT 3""",
            {"ids": accounts},
        )
        if not rows:
            return _res("funnel_hub", "no internal money flow", {"hub": None})
        hub, senders, total = rows[0]
        ev = []
        srows = self.q(
            """MATCH (s:Account)-[r:SENT]->(h:Account {id:$h}) WHERE s.id IN $ids
               RETURN s.id, r.txn, r.amount ORDER BY r.amount DESC LIMIT 5""",
            {"h": hub, "ids": accounts},
        )
        for sid, txn, amt in srows:
            ev.append(f"{sid} -[SENT {txn}: {amt}]-> {hub}")
        return _res("funnel_hub",
                    f"{hub} receives from {senders} cluster members (total {total}); global PageRank {self._pr.get(hub, 0):.3f}",
                    {"hub": hub, "senders": senders, "total": total, "pagerank": self._pr.get(hub, 0)}, ev)

    # ---------------------------------------------------------------- expansion (multi-hop)
    def money_neighbours(self, accounts, young_days=90):
        """Young accounts outside the cluster that trade money with it: likely extra members the identity graph missed."""
        rows = self.q(
            """MATCH (m:Account)-[r:SENT]-(o:Account) WHERE m.id IN $ids AND NOT o.id IN $ids AND o.age_days < $young
               RETURN DISTINCT o.id, m.id, r.txn, r.amount""",
            {"ids": accounts, "young": young_days},
        )
        found = sorted({r[0] for r in rows})
        ev = [f"{m} -[SENT {t}: {a}]- {o}" for o, m, t, a in rows[:8]]
        return _res("money_neighbours", f"{len(found)} young account(s) transact with the cluster", {"accounts": found}, ev)

    def merchant_exposure(self, accounts):
        """Merchants whose settlement account is in the cluster, and the customers who paid them (the victims)."""
        rows = self.q(
            """MATCH (s:Account)-[:SETTLES_FOR]->(m:Merchant) WHERE s.id IN $ids
               OPTIONAL MATCH (v:Account)-[:FROM]->(t:Txn)-[:AT]->(m)
               RETURN m.id, m.name, s.id, collect(DISTINCT v.id), sum(t.amount)""",
            {"ids": accounts},
        )
        res = []
        ev = []
        for mid, mname, sid, victims, total in rows:
            victims = [v for v in victims if v]
            res.append({"merchant": mid, "name": mname, "settlement_account": sid, "victims": victims, "total": total or 0})
            ev.append(f"{sid} -[SETTLES_FOR]-> {mid} <-[AT]- txn <-[FROM]- {len(victims)} paying accounts")
        return _res("merchant_exposure",
                    f"{len(res)} merchant(s) settle into the cluster" if res else "no merchant settles into the cluster",
                    {"merchants": res}, ev)

    # ---------------------------------------------------------------- actions (write back to the graph)
    def record_case(self, case_id, verdict, score, accounts, reasons, evidence):
        self.q("MERGE (c:Case {id:$id}) SET c.verdict=$v, c.score=$s, c.reasons=$r", {"id": case_id, "v": verdict, "s": score, "r": reasons})
        self.q("MATCH (a:Account) WHERE a.id IN $ids MATCH (c:Case {id:$id}) MERGE (c)-[:COVERS]->(a)", {"ids": accounts, "id": case_id})
        if verdict == "FREEZE":
            self.q("MATCH (a:Account) WHERE a.id IN $ids SET a.status='frozen'", {"ids": accounts})
        return _res("record_case", f"{case_id}: {verdict} recorded on {len(accounts)} accounts")

    def record_victims(self, case_id, victims, merchant_id):
        self.q(
            """MATCH (c:Case {id:$id}), (m:Merchant {id:$m})
               MERGE (c)-[:INVOLVES]->(m)
               WITH c
               MATCH (v:Account) WHERE v.id IN $vs
               MERGE (c)-[:VICTIM]->(v)
               SET v.status = 'notify'""",
            {"id": case_id, "m": merchant_id, "vs": victims},
        )
        return _res("record_victims", f"{len(victims)} victim accounts flagged for outreach")
