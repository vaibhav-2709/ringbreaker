import json
import sys

from .agent import Investigator, explain
from .graph import connect, load


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    g = connect()
    if cmd in ("load", "run"):
        truth = load(g)
        print(f"loaded graph; planted rings: { {k: len(v) for k, v in truth.items()} }")
    if cmd == "run":
        cases = Investigator(g).sweep()
        for c in cases:
            print("=" * 78)
            print(explain(c))
        json.dump([c.to_dict() for c in cases], open("cases.json", "w"), indent=2)
        print("\nwrote cases.json")


if __name__ == "__main__":
    main()
