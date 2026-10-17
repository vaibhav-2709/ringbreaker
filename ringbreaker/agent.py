"""RingBreaker investigator agent.

The agent works from the graph, not from a fixed script:
  1. discovers candidate clusters with a graph algorithm (WCC over identity links)
  2. picks tools per cluster based on what the previous tool showed (cheap checks first, stop early on clean clusters)
  3. follows money links outward to find members the identity graph missed
  4. scores the evidence, decides FREEZE / ESCALATE / CLEAR
  5. writes Case / COVERS / VICTIM edges and account status back into the graph
Every point of the score carries the graph path that earned it.
"""
from dataclasses import dataclass, field

from .tools import Tools

FREEZE_AT = 60
ESCALATE_AT = 35


@dataclass
class Signal:
    name: str
    points: int
    why: str
    evidence: list = field(default_factory=list)


@dataclass
class Case:
    case_id: str
    accounts: list
    verdict: str = "CLEAR"
    score: int = 0
    signals: list = field(default_factory=list)
    trace: list = field(default_factory=list)   # (tool, why this tool, what it found)
    victims: list = field(default_factory=list)
    merchant: str | None = None
    hub: str | None = None
    cycles: list = field(default_factory=list)

    def to_dict(self):
        return {
            "case_id": self.case_id, "verdict": self.verdict, "score": self.score, "accounts": self.accounts,
            "hub": self.hub, "cycles": self.cycles, "merchant": self.merchant, "victims": self.victims,
            "signals": [s.__dict__ for s in self.signals],
            "trace": [{"tool": t, "why": w, "found": f} for t, w, f in self.trace],
        }


class Investigator:
    def __init__(self, g, write_back=True):
        self.t = Tools(g)
        self.write_back = write_back

    # ------------------------------------------------------------------
    def sweep(self, min_cluster=3):
        found = self.t.identity_clusters(min_cluster)
        cases = []
        for i, accounts in enumerate(found["data"]["clusters"], start=1):
            cases.append(self.investigate(f"CASE-{i:03d}", accounts, found["summary"] if i == 1 else None))
        return cases

    # ------------------------------------------------------------------
    def investigate(self, case_id, accounts, discovery_note=None):
        case = Case(case_id, list(accounts))
        step = lambda tool, why, res: case.trace.append((tool, why, res["summary"]))
        if discovery_note:
            case.trace.append(("identity_clusters", "start from structure: group accounts that share owners, devices or addresses", discovery_note))

        # --- 1. cheapest question first: do these accounts even look new / unverified?
        prof = self.t.cluster_profile(case.accounts)
        step("cluster_profile", "check account age and KYC before spending effort on deeper traversals", prof)
        p = prof["data"]
        if p["young_share"] >= 0.8:
            case.signals.append(Signal("new_accounts", 25, f"{p['young']} of {p['n']} accounts are younger than 90 days"))
        if p["pending_kyc_share"] >= 0.5:
            case.signals.append(Signal("unverified_kyc", 20, f"{p['pending']} of {p['n']} owners have unverified KYC"))

        # --- 2. who is tied together, and by what?
        shared = self.t.shared_identity(case.accounts)
        step("shared_identity", "find the devices/addresses that bind the cluster together", shared)
        devs, addrs = shared["data"]["devices"], shared["data"]["addresses"]
        heavy_dev = any(len(a) >= 3 for a in devs.values())
        heavy_addr = any(len(a) >= 4 for a in addrs.values())
        if len(devs) >= 2 or heavy_dev or heavy_addr:
            case.signals.append(Signal("shared_identity", 20,
                                       f"{len(devs)} shared device(s), {len(addrs)} shared address(es) across owners", shared["evidence"][:4]))

        # --- early exit: old, verified accounts with no further red flags -> do not burn more queries
        if p["young_share"] < 0.5 and p["pending_kyc_share"] < 0.2:
            case.trace.append(("(stop)", "mature, verified accounts: sharing a home or phone is normal; no deeper traversal needed", "cluster looks like a household"))
            return self._decide(case)

        # --- 3. money behaviour
        cyc = self.t.money_cycles(case.accounts)
        step("money_cycles", "young linked accounts: test whether money returns to its origin", cyc)
        if cyc["data"]["cycles"]:
            case.cycles = cyc["data"]["cycles"]
            case.signals.append(Signal("money_carousel", 30, f"{len(case.cycles)} cycle(s) where funds return to the sender", cyc["evidence"][:3]))

        hub = self.t.funnel_hub(case.accounts)
        step("funnel_hub", "test for a collector account that members pay into (PageRank + in-cluster fan-in)", hub)
        if hub["data"].get("hub") and hub["data"]["senders"] >= 5:
            case.hub = hub["data"]["hub"]
            case.signals.append(Signal("funnel_hub", 25, f"{case.hub} collects from {hub['data']['senders']} cluster members", hub["evidence"]))

        # --- 4. follow money one hop outward, then re-check the larger cluster
        nb = self.t.money_neighbours(case.accounts)
        step("money_neighbours", "identity links can miss members; follow money to young neighbours", nb)
        extra = nb["data"]["accounts"]
        if extra:
            case.accounts = sorted(set(case.accounts) | set(extra))
            case.signals.append(Signal("money_expansion", 10, f"{len(extra)} young account(s) outside the cluster trade with it: {', '.join(extra)}", nb["evidence"][:3]))

        # --- 5. does a merchant settle into this cluster? then the people who paid it are victims
        mx = self.t.merchant_exposure(case.accounts)
        step("merchant_exposure", "check whether a merchant settles into the cluster (a shell storefront)", mx)
        for m in mx["data"]["merchants"]:
            if len(m["victims"]) >= 5:
                case.merchant, case.victims = m["merchant"], m["victims"]
                case.signals.append(Signal("shell_merchant", 25,
                                           f"{m['merchant']} ({m['name']}) settles into the cluster; {len(m['victims'])} accounts paid it a total of {m['total']}",
                                           mx["evidence"]))
        return self._decide(case)

    # ------------------------------------------------------------------
    def _decide(self, case):
        case.score = sum(s.points for s in case.signals)
        case.verdict = "FREEZE" if case.score >= FREEZE_AT else "ESCALATE" if case.score >= ESCALATE_AT else "CLEAR"
        if self.write_back:
            reasons = [f"{s.name}(+{s.points})" for s in case.signals]
            self.t.record_case(case.case_id, case.verdict, case.score, case.accounts, reasons, [])
            if case.verdict == "FREEZE" and case.merchant:
                self.t.record_victims(case.case_id, case.victims, case.merchant)
        return case


def explain(case):
    """Plain-language explanation of a decision, with the graph path behind every reason."""
    lines = [f"{case.case_id}: {case.verdict} (score {case.score}) on {len(case.accounts)} accounts", ""]
    if case.signals:
        lines.append("Why:")
        for s in case.signals:
            lines.append(f"  +{s.points:<3}{s.name}: {s.why}")
            for e in s.evidence[:2]:
                lines.append(f"        path: {e}")
    else:
        lines.append("Why: no risk signals fired.")
    if case.victims:
        lines.append(f"\nAction: freeze {len(case.accounts)} accounts; notify {len(case.victims)} customers who paid {case.merchant}.")
    elif case.verdict == "FREEZE":
        lines.append(f"\nAction: freeze {len(case.accounts)} accounts.")
    lines.append("\nTools used: " + " -> ".join(t for t, _, _ in case.trace))
    return "\n".join(lines)
