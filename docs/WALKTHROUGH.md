# Understand RingBreaker (read this before you submit)

The rules say you must be able to explain the graph model, the queries, the architecture and the decisions.
This page is a plain-language guide. Read it, then run the code yourself and change something.

## The idea in one paragraph

Fraud rings hide because each record looks normal alone. The pattern only shows up in the connections:
accounts that share a phone, money that goes in a circle, one account collecting from many.
So the data is stored as a graph, and the agent asks the graph connection questions instead of reading rows.

## The five node types and why

- **Customer** owns an **Account**.
- Customers **use** a **Device** and **live at** an **Address**. Shared devices and addresses are the glue that links fake identities.
- **Txn** nodes are individual payments, **Merchant** nodes are shops.
- **SENT** is a shortcut edge between accounts that remembers which transaction it came from, so every hop can be traced.

## The agent's steps and the question each answers

| Step | Tool | Question it answers |
| --- | --- | --- |
| 1 | `identity_clusters` | Which accounts are tied together by owner, device or address? (`algo.WCC`) |
| 2 | `cluster_profile` | Are they new and unverified? |
| 3 | `shared_identity` | What exactly binds them? |
| 4 | `money_cycles` | Does money return to where it started? |
| 5 | `funnel_hub` | Does one account collect from many? (`algo.pageRank`) |
| 6 | `money_neighbours` | Are there young accounts outside the cluster trading with it? |
| 7 | `merchant_exposure` | Does a shop settle into the cluster, and who paid it? |

Clusters of old, verified accounts stop after step 3. That is the "tool selection": the agent spends effort only where earlier results justify it.

## Likely judge questions and honest answers

**Why a graph and not SQL?** The key questions are multi-hop: owner to device to owner, or settlement account to merchant to payment to payer. In SQL these are repeated self-joins. Here they are one path pattern, and WCC and PageRank run inside the database.

**What happens if you remove FalkorDB?** There is no cluster list, no cycle search and no hub ranking. The agent would have to rebuild all of that itself.

**Is the model learning anything?** No. The scoring is rule-based with hand-set weights in `agent.py`. A language model can drive the same tools through the MCP server.

**How do you know it works?** `tests/test_agent.py` compares against the planted rings: 20 of 20 caught, 0 false positives on 3 seeds. Be clear that the data is synthetic and the rings were designed by us, so this is a pipeline check, not a real-world accuracy claim.

**What would break on real data?** Loader code, the thresholds (90 days, 5 senders, the point weights) and probably the need for time windows. Real fraud is noisier.

**What is your own contribution?** Write this in your own words in the README disclosure. Examples that are honest only if true: you chose the track and the fraud scenario, you reviewed the queries, you ran the tests and changed a threshold or added a signal.

## Do these before you submit (about 30 minutes)

1. Run `python3 -m ringbreaker run` and read the output for CASE-001 and CASE-007.
2. Open `ringbreaker/tools.py` and read `money_cycles` and `funnel_hub` until you can explain each query line by line.
3. Change one number in `agent.py` (for example `FREEZE_AT`) and rerun `python3 -m tests.test_agent` to see what happens.
4. Add one small thing of your own, such as a new signal or a new ring type in `data.py`.
5. Edit the AI disclosure in the README so it is true.

## Demo video script (about 2 to 3 minutes)

1. **0:00 The problem (15s).** "Fraud rings hide because each account looks normal alone. The pattern lives in the connections."
2. **0:15 The graph (20s).** Show FalkorDB Browser or the data model from the README: customers, accounts, devices, addresses, transactions.
3. **0:35 Run the agent (30s).** Run `python3 -m ringbreaker run`. Point at CASE-002 (carousel) and CASE-001 (mule farm).
4. **1:05 The explanation (30s).** Open `report.html`. Show a graph drawing and one evidence path. "Every point of the score has a path behind it."
5. **1:35 Cleared households (15s).** "These six clusters share a home or phone but have old, verified accounts. The agent stopped after two tool calls."
6. **1:50 The shell merchant (25s).** CASE-007: the agent found an extra account through money flow and identified 14 victims.
7. **2:15 Actions and MCP (15s).** Show `Case` nodes in the graph and the MCP tool list.
8. **2:30 Close (10s).** Say what is real and what is synthetic, and what you would do next.
