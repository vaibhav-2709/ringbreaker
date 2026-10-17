"""Score the agent against the planted ground truth. Run: python3 -m tests.test_agent"""
import os
import tempfile

from ringbreaker.agent import Investigator
from ringbreaker.graph import connect, load


def run(seed):
    os.environ["RINGBREAKER_DB"] = os.path.join(tempfile.mkdtemp(), f"t{seed}.db")
    g = connect()
    truth = load(g, seed=seed)
    cases = Investigator(g).sweep()
    flagged = {a for c in cases if c.verdict == "FREEZE" for a in c.accounts}
    planted = set().union(*truth.values())
    tp, fp, fn = len(flagged & planted), len(flagged - planted), len(planted - flagged)
    frozen_in_graph = {r[0] for r in g.query("MATCH (a:Account {status:'frozen'}) RETURN a.id").result_set}
    assert frozen_in_graph == flagged, "graph status must match decisions"
    per_ring = {name: len(accts & flagged) / len(accts) for name, accts in truth.items()}
    return tp, fp, fn, per_ring


if __name__ == "__main__":
    for seed in (7, 11, 23):
        tp, fp, fn, per_ring = run(seed)
        print(f"seed {seed}: caught {tp}/{tp + fn} fraud accounts, {fp} false positives, per ring {per_ring}")
        assert fp == 0 and fn == 0, "expected perfect separation on the synthetic data"
    print("OK")
