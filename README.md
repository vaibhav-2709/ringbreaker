# RingBreaker

**A graph-powered fraud investigator that finds hidden fraud rings, freezes them, and shows exactly why.**

Built for **Graph Hacks 2026 (WeMakeDevs x FalkorDB), Track 1: Agents That Act on Connected Data.** FalkorDB is the primary and only database.

| | |
| --- | --- |
| Live case report (saved output of one run) | https://vaibhav-2709.github.io/ringbreaker/report.html |
| Demo video | `<ADD YOUR VIDEO LINK>` |
| Source code | https://github.com/vaibhav-2709/ringbreaker |

> The report link is a **saved result** of the agent's run, so you can see what it produces without installing anything. The agent itself runs locally (setup below).

---

## What it does

Fraudsters create fake accounts that each look normal on their own. The giveaway is how the accounts are **connected**: they share a phone or address, pass money in circles, or all feed one collector account. Reading a spreadsheet row by row hides this.

RingBreaker stores the bank's data as a **graph** (accounts, owners, devices, addresses, merchants and payments as dots, with lines for "owns", "uses", "paid") and lets an investigator agent walk the connections.

For each suspicious group of accounts the agent will:

1. **Investigate**: pick graph tools based on what it finds.
2. **Decide**: freeze the group, escalate it, or clear it.
3. **Act**: freeze the accounts and flag the customers who were scammed.
4. **Explain**: show the exact chain of connections behind every point of its risk score.

In the demo data (about 470 accounts and 1,400+ transactions) it catches three planted fraud rings and clears six innocent look-alike groups.

| Ring | What it looks like | How it is caught |
| --- | --- | --- |
| **Carousel** | 6 brand-new accounts pass money round in a circle and share 3 devices | connected-components cluster, then a loop-finding query |
| **Mule farm** | 10 unverified identities at one address all pay one collector account | cluster, then PageRank and fan-in to find the collector |
| **Shell merchant** | A fake storefront takes money from 14 customers and settles into a few cash-out accounts | cluster, follow money to an extra member, trace the merchant's payers (the victims) |

## How it finds the result (step by step)

```
all accounts
   |  1. algo.WCC over owner / device / address links      -> groups of linked accounts
   v
each group
   |  2. check account age + KYC status                    -> new or unverified?
   |  3. find shared devices / addresses                   -> what ties them together?
   |        old + verified?  -> stop, it is a household (CLEAR)
   v
young or unverified groups
   |  4. look for money that returns to its sender         -> carousel
   |  5. look for one account collecting from many         -> PageRank + fan-in
   |  6. follow money to young accounts outside the group  -> hidden members
   |  7. check merchants that settle into the group        -> shell store + victims
   v
score the evidence -> FREEZE (60+) / ESCALATE (35-59) / CLEAR (<35)
   v
write the Case, the frozen accounts and the victims back into the graph
```

**Example (the carousel).** Six accounts are all younger than 90 days (+25). They share three devices (+20). A query finds that money goes
`ACCT0451 -> ACCT0456 -> ACCT0455 -> ACCT0454 -> ACCT0453 -> ACCT0452 -> ACCT0451`, ending where it started (+30).
Score 75, so the group is frozen, and the report shows each of those paths as evidence.

**Why not just ordinary rows?** The key questions are multi-hop ("owner, to device, to another owner", or "merchant, to payment, to payer"). In a table these need repeated self-joins. In FalkorDB they are one path pattern, and the clustering and PageRank run inside the database.

**Tool selection.** Cheap checks run first and decide what happens next. Old, verified groups (families sharing a home) stop after two tool calls, while young linked groups get the full toolkit. The order after that is fixed. A language model can choose tools freely through the MCP server.

---

## Run it yourself

Requirements: Python 3.10+, Docker (recommended).

**1. Start FalkorDB**

```bash
docker compose up -d        # FalkorDB on port 6379, FalkorDB Browser on http://localhost:3000
pip install -r requirements.txt
```

**2. Run the investigation**

macOS / Linux:
```bash
export FALKORDB_HOST=localhost FALKORDB_PORT=6379
python3 -m ringbreaker run          # loads data, investigates, prints explanations
python3 -m ringbreaker.report       # writes report.html (graph drawings + evidence)
```

Windows (PowerShell):
```powershell
$env:FALKORDB_HOST="localhost"; $env:FALKORDB_PORT="6379"
py -m ringbreaker run
py -m ringbreaker.report
```

You should see 3 `FREEZE` cases and 6 `CLEAR` cases. Open `report.html` in a browser.

**Other options**
- **FalkorDB Cloud or a remote server:** also set `FALKORDB_PASSWORD` (and `FALKORDB_USERNAME`, `FALKORDB_SSL=1` if needed).
- **Embedded, no Docker (macOS and Linux only):** run the same commands without setting `FALKORDB_HOST`. Uses `falkordblite`, which does not support Windows.

**Explore the graph.** Open http://localhost:3000, leave username and password empty, and try:

```cypher
MATCH (a:Account {status:'frozen'}) RETURN a
MATCH (c:Case)-[:VICTIM]->(v:Account), (c)-[:INVOLVES]->(m:Merchant) RETURN c, v, m
```

**Tests.** `python3 -m tests.test_agent` checks the agent against the planted rings (embedded database, macOS/Linux).

**MCP server.** `python3 -m ringbreaker.mcp_server` exposes the graph tools to any MCP client so a language model can investigate by itself: `find_suspicious_clusters`, `profile_accounts`, `shared_identity_links`, `detect_money_cycles`, `find_funnel_hub`, `expand_via_money`, `merchant_exposure`, `run_full_investigation`, `freeze_accounts`.

---

## Graph data model

```
(Customer)-[:OWNS]->(Account)
(Customer)-[:USES]->(Device)
(Customer)-[:LIVES_AT]->(Address)
(Account)-[:FROM]->(Txn)-[:TO]->(Account)           money transfer
(Account)-[:FROM]->(Txn)-[:AT]->(Merchant)          card purchase
(Account)-[:SETTLES_FOR]->(Merchant)                where a merchant's money lands
(Account)-[:SENT {txn, amount, ts}]->(Account)      derived shortcut that keeps the transaction id

written by the agent:
(Case)-[:COVERS]->(Account)   (Case)-[:INVOLVES]->(Merchant)   (Case)-[:VICTIM]->(Account)
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

The labels used to plant the fraud rings are **never loaded into the graph**, so the agent has to detect fraud from structure alone.

## Cypher queries and graph algorithms the product depends on

All are in `ringbreaker/tools.py`.

| Tool | What it runs |
| --- | --- |
| `identity_clusters` | `CALL algo.WCC({nodeLabels:['Account','Customer','Device','Address'], relationshipTypes:['OWNS','USES','LIVES_AT']})` |
| `shared_identity` | `MATCH (a:Account)<-[:OWNS]-(c:Customer)-[:USES]->(x:Device) WHERE a.id IN $ids RETURN x.id, collect(DISTINCT a.id)` (same for `LIVES_AT` and Address) |
| `money_cycles` | `MATCH p=(a:Account)-[:SENT*3..6]->(a) WHERE a.id IN $ids WITH DISTINCT [n IN nodes(p) \| n.id] AS path RETURN path` |
| `funnel_hub` | `CALL algo.pageRank('Account','SENT')` plus a fan-in count: `MATCH (s)-[r:SENT]->(h) ... count(DISTINCT s.id) ORDER BY senders DESC` |
| `money_neighbours` | `MATCH (m:Account)-[r:SENT]-(o:Account) WHERE m.id IN $ids AND NOT o.id IN $ids AND o.age_days < $young RETURN DISTINCT o.id` |
| `merchant_exposure` | `MATCH (s:Account)-[:SETTLES_FOR]->(m:Merchant) ... OPTIONAL MATCH (v:Account)-[:FROM]->(t:Txn)-[:AT]->(m)` |
| `record_case`, `record_victims` | `MERGE (c:Case ...)`, `MERGE (c)-[:COVERS]->(a)`, `SET a.status='frozen'` |

## Why the graph does the real work

- Fraud clusters come from `algo.WCC`. Without the graph there is no list of suspects.
- Money loops come from a variable-length path query that returns to its start.
- The collector account comes from `algo.pageRank` plus a fan-in traversal.
- Victims come from a 4-hop path: settlement account, merchant, transaction, paying account.
- Decisions are written back as graph structure and account status.

Remove FalkorDB and the agent has nothing to reason over.

## Data

All data is **synthetic**, generated by `ringbreaker/data.py` with a fixed random seed. No private, personal, paywalled or login-protected data is used.

## Results and honest limits

- On the synthetic data the agent catches 20 of 20 planted fraud accounts with 0 false positives across 3 random seeds (`tests/test_agent.py`). The rings and thresholds were designed by us, so this shows the pipeline works, **not** that it would be this accurate on real banking data.
- The decision policy is rule-based with hand-set weights (`ringbreaker/agent.py`). A language model can drive the same tools through the MCP server, but the built-in investigator does not use one.
- Real data would need new loader code, re-tuned thresholds and probably time windows.

## AI assistance disclosure

This project was built with an AI coding assistant (Claude, by Anthropic) working with our team.
Claude wrote the first version of the code, the synthetic data generator, the tests and the documentation.
The team chose the track and the fraud-investigation direction, read the hackathon rules and had the project adjusted to meet them, ran and checked the results, and is responsible for understanding and explaining the graph model, the queries and the architecture.

### Team and contributions

| Member | What they did |
| --- | --- |
| Vaibhav (GitHub: [vaibhav-2709](https://github.com/vaibhav-2709)) | Team lead. Chose Track 1 after comparing the three tracks, registered the team, reviewed the rules and the submission requirements, installed Docker and ran the project against FalkorDB on Windows (which exposed the Windows setup problem that was then fixed), explored the graph in FalkorDB Browser, created the public repository and the GitHub Pages report, and prepared the submission. |
| `<TEAMMATE 2 NAME>` | `<what they actually did, for example "wrote the blog post" or "added the shortest-path tool">` |
| `<TEAMMATE 3 NAME>` | `<what they actually did>` |

`<ADD any feature or change the team made to the code, for example a new fraud signal, once it exists.>`

## Project layout

```
ringbreaker/data.py        synthetic banking graph and the planted rings
ringbreaker/graph.py       loads the graph into FalkorDB (remote, Docker or embedded)
ringbreaker/tools.py       graph tools (Cypher + algorithms) that return evidence paths
ringbreaker/agent.py       investigator: tool selection, scoring, actions, explanations
ringbreaker/mcp_server.py  MCP tools for language models
ringbreaker/report.py      builds the HTML case report
tests/test_agent.py        accuracy check against the planted rings
docker-compose.yml         FalkorDB and FalkorDB Browser
```
