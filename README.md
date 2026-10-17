# RingBreaker: a graph-native fraud investigation agent

**Graph Hacks track entered: Track 1, Agents That Act on Connected Data** (FalkorDB is the primary and only database).

RingBreaker treats a bank's accounts, owners, devices, addresses, merchants and transactions as one graph.
It finds organised fraud rings, **freezes the accounts, flags the victims, and shows the graph path behind every decision.**

- Public repo: `<ADD YOUR GITHUB REPO LINK>`
- Demo video: `<ADD YOUR VIDEO LINK>`
- Live deployment: none. Full local setup is below.

## AI assistance disclosure

This project was built with an AI coding assistant (Claude, by Anthropic) working with `<YOUR NAME>`.
Claude wrote the first version of the code, the synthetic data generator, the tests and this README.
`<YOUR NAME>` chose the track and direction, reviewed and ran the code, and can explain the graph model, the queries and the architecture.
`<EDIT THIS to say honestly what you personally did, changed or verified.>`

## What it catches

Three fraud patterns are planted among 420+ legitimate accounts, including innocent households that share a home or phone:

| Ring | Pattern | How the agent finds it |
| --- | --- | --- |
| Carousel | 6 new accounts pass money in a circle and share 3 devices | `algo.WCC` cluster, then variable-length cycle query |
| Mule farm | 10 unverified identities at one address all pay one collector | `algo.WCC` cluster, then `algo.pageRank` + fan-in |
| Shell merchant | 14 customers pay a storefront that settles into a few cash-out accounts | cluster, money-link expansion, merchant settlement traversal |

## Why the graph does the real work (rules 2 and 3)

Detection is done inside FalkorDB, not in Python over exported rows:

- Fraud clusters come from `algo.WCC` over the identity links. Without the graph there is no candidate list.
- Money loops come from a variable-length path query that returns to its start node.
- The collector hub comes from `algo.pageRank` plus a fan-in traversal.
- Victims come from a 4-hop path: settlement account to merchant to transaction to paying account.
- Decisions are written back as graph structure (`Case`, `COVERS`, `VICTIM`, `INVOLVES`) and `status` on accounts.

Take FalkorDB out and the agent has nothing to reason over.

## Setup

Requirements: Python 3.10+, and either Docker or the embedded option.

**Option A: FalkorDB in Docker (recommended)**

```bash
docker compose up -d                       # FalkorDB on :6379, Browser on :3000
pip install -r requirements.txt
export FALKORDB_HOST=localhost FALKORDB_PORT=6379
python3 -m ringbreaker run                 # loads data, investigates, prints explanations, writes cases.json
python3 -m ringbreaker.report              # writes report.html
```

**Option B: embedded FalkorDB, no Docker** (falkordblite)

```bash
pip install -r requirements.txt
python3 -m ringbreaker run
```

Other commands:

```bash
python3 -m tests.test_agent                # checks results against the planted ground truth (embedded DB)
python3 -m ringbreaker.mcp_server          # MCP server over stdio (tools listed below)
```

Open FalkorDB Browser at http://localhost:3000 (Docker option) and run `MATCH (c:Case)-[:COVERS]->(a:Account) RETURN c, a` to see the agent's decisions.

## Graph data model

```
(Customer)-[:OWNS]->(Account)
(Customer)-[:USES]->(Device)
(Customer)-[:LIVES_AT]->(Address)
(Account)-[:FROM]->(Txn)-[:TO]->(Account)           money transfer
(Account)-[:FROM]->(Txn)-[:AT]->(Merchant)          card purchase
(Account)-[:SETTLES_FOR]->(Merchant)                where a merchant's money lands
(Account)-[:SENT {txn, amount, ts}]->(Account)      derived shortcut, keeps the txn id for tracing

written by the agent:
(Case)-[:COVERS]->(Account)     (Case)-[:INVOLVES]->(Merchant)     (Case)-[:VICTIM]->(Account)
```

| Node | Properties |
| --- | --- |
| Customer | id, name, kyc (`verified` or `pending`) |
| Account | id, age_days, balance, status (set by the agent) |
| Device | id, kind |
| Address | id, city, line |
| Merchant | id, name, category |
| Txn | id, amount, ts, kind |
| Case | id, verdict, score, reasons |

Ground-truth labels used to plant the rings are never loaded into the graph, so the agent must detect fraud from structure.

## Cypher queries and algorithms the product depends on

All live in `ringbreaker/tools.py`.

| Tool | What it runs |
| --- | --- |
| `identity_clusters` | `CALL algo.WCC({nodeLabels:['Account','Customer','Device','Address'], relationshipTypes:['OWNS','USES','LIVES_AT']})` |
| `shared_identity` | `MATCH (a:Account)<-[:OWNS]-(c:Customer)-[:USES]->(x:Device) WHERE a.id IN $ids RETURN x.id, collect(DISTINCT a.id)` (same for `LIVES_AT`/Address) |
| `money_cycles` | `MATCH p=(a:Account)-[:SENT*3..6]->(a) WHERE a.id IN $ids WITH DISTINCT [n IN nodes(p) \| n.id] AS path RETURN path` |
| `funnel_hub` | `CALL algo.pageRank('Account','SENT')` plus `MATCH (s)-[r:SENT]->(h) ... count(DISTINCT s.id) ORDER BY senders DESC` |
| `money_neighbours` | `MATCH (m:Account)-[r:SENT]-(o:Account) WHERE m.id IN $ids AND NOT o.id IN $ids AND o.age_days < $young RETURN DISTINCT o.id` |
| `merchant_exposure` | `MATCH (s:Account)-[:SETTLES_FOR]->(m:Merchant) ... OPTIONAL MATCH (v:Account)-[:FROM]->(t:Txn)-[:AT]->(m)` |
| `record_case`, `record_victims` | `MERGE (c:Case ...)`, `MERGE (c)-[:COVERS]->(a)`, `SET a.status='frozen'` |

## How the agent decides

1. Find clusters with `algo.WCC`.
2. For each cluster, start with the cheapest check (account age and KYC), then shared devices and addresses.
3. Mature, verified clusters stop here (a household). Young or unverified ones get cycle, hub, money-expansion and merchant checks.
4. Each signal adds points and carries a graph path as evidence. 60+ freezes, 35 to 59 escalates, below 35 clears.
5. The decision and its evidence are written back to the graph.

MCP tools exposed by `ringbreaker.mcp_server`: `find_suspicious_clusters`, `profile_accounts`, `shared_identity_links`, `detect_money_cycles`, `find_funnel_hub`, `expand_via_money`, `merchant_exposure`, `run_full_investigation`, `freeze_accounts`.
A model such as Claude can call them to investigate on its own.

## Data (rule 6)

All data is **synthetic**, generated by `ringbreaker/data.py` with a fixed seed. No private, personal, paywalled or login-protected data is used.

## Results and honest limits

- On the synthetic data the agent catches 20 of 20 planted fraud accounts with 0 false positives across 3 random seeds (`tests/test_agent.py`). I designed the rings and tuned the thresholds, so this shows the pipeline works, not that it would be this accurate on real banking data.
- The decision policy is rule-based with hand-set weights. The language model enters through MCP.
- Real data would need new loader code and re-tuned thresholds.

## Layout

```
ringbreaker/data.py        synthetic banking graph + planted rings
ringbreaker/graph.py       loader (FalkorDB, remote or embedded)
ringbreaker/tools.py       graph tools (Cypher + algorithms) with evidence paths
ringbreaker/agent.py       investigator: tool selection, scoring, actions, explanations
ringbreaker/mcp_server.py  MCP tools
ringbreaker/report.py      HTML case report
tests/test_agent.py        accuracy check vs ground truth
docker-compose.yml         FalkorDB + Browser
```
