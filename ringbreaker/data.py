"""Synthetic banking graph with planted fraud rings.

Entities: Customer, Account, Device, Address, Merchant, Txn
Edges:    OWNS, USES (customer->device), LIVES_AT, FROM / TO (txn flow), AT (txn->merchant)

Three rings are planted among legitimate noise:
  RING_A  "carousel"   money moves in a cycle between accounts that share devices
  RING_B  "mule farm"  many synthetic identities share one address, funnel cash to one hub
  RING_C  "fan-in"     many victims' accounts pay a shell merchant, which pays out to a few cash-out accounts

Ground truth is returned so tests can check recall and false positives.
"""
import random
from datetime import datetime, timedelta

SEED = 7
FIRST = ["Aarav", "Diya", "Kabir", "Meera", "Rohan", "Isha", "Vikram", "Anaya", "Arjun", "Saanvi",
         "Dev", "Tara", "Neil", "Riya", "Kunal", "Pooja", "Aditya", "Nisha", "Yash", "Kavya"]
LAST = ["Sharma", "Iyer", "Patel", "Gupta", "Nair", "Rao", "Mehta", "Singh", "Das", "Bose",
        "Kapoor", "Joshi", "Menon", "Shah", "Verma"]
CITIES = ["Mumbai", "Delhi", "Bengaluru", "Pune", "Chennai", "Kolkata", "Hyderabad", "Jaipur"]
MERCH_CATS = ["grocery", "fuel", "electronics", "travel", "dining", "pharmacy", "fashion", "utilities"]


def generate(n_legit=420, seed=SEED):
    rnd = random.Random(seed)
    t0 = datetime(2026, 9, 1)
    nodes = {"Customer": [], "Account": [], "Device": [], "Address": [], "Merchant": [], "Txn": []}
    edges = []  # (src_label, src_id, rel, dst_label, dst_id)
    truth = {"RING_A": set(), "RING_B": set(), "RING_C": set()}
    ctr = {"cust": 0, "acct": 0, "dev": 0, "addr": 0, "txn": 0}

    def name():
        return f"{rnd.choice(FIRST)} {rnd.choice(LAST)}"

    def add_address(city=None, street=None):
        ctr["addr"] += 1
        aid = f"ADDR{ctr['addr']:04d}"
        nodes["Address"].append({"id": aid, "city": city or rnd.choice(CITIES),
                                 "line": street or f"{rnd.randint(1, 240)} {rnd.choice(['MG Road','Park St','Lake View','Hill Rd','Station Rd'])}"})
        return aid

    def add_device():
        ctr["dev"] += 1
        did = f"DEV{ctr['dev']:04d}"
        nodes["Device"].append({"id": did, "kind": rnd.choice(["android", "ios", "web"])})
        return did

    def add_customer(addr, devs, age_days=None, kyc="verified"):
        ctr["cust"] += 1
        cid = f"CUST{ctr['cust']:04d}"
        nodes["Customer"].append({"id": cid, "name": name(), "kyc": kyc})
        edges.append(("Customer", cid, "LIVES_AT", "Address", addr))
        for d in devs:
            edges.append(("Customer", cid, "USES", "Device", d))
        ctr["acct"] += 1
        aid = f"ACCT{ctr['acct']:04d}"
        age = age_days if age_days is not None else rnd.randint(200, 3000)
        nodes["Account"].append({"id": aid, "age_days": age, "balance": rnd.randint(2000, 90000)})
        edges.append(("Customer", cid, "OWNS", "Account", aid))
        return cid, aid

    def add_merchant(mid, name_, cat, shell=False):
        nodes["Merchant"].append({"id": mid, "name": name_, "category": cat, "shell": shell})
        return mid

    def add_txn(src, dst, amount, when, kind="transfer", merchant=None):
        ctr["txn"] += 1
        tid = f"TXN{ctr['txn']:05d}"
        nodes["Txn"].append({"id": tid, "amount": int(amount), "ts": when.isoformat(timespec="minutes"), "kind": kind})
        edges.append(("Account", src, "FROM", "Txn", tid))
        if merchant:
            edges.append(("Txn", tid, "AT", "Merchant", merchant))
        else:
            edges.append(("Txn", tid, "TO", "Account", dst))
        return tid

    # ---- merchants (legit)
    merchants = []
    for i in range(30):
        merchants.append(add_merchant(f"MERCH{i:03d}", f"{rnd.choice(['Fresh','Metro','Urban','Prime','Daily'])} {rnd.choice(MERCH_CATS).title()} {i}",
                                      rnd.choice(MERCH_CATS)))

    # ---- every legit merchant settles to an old, verified corporate account (so settlement links are not a giveaway)
    for m in merchants:
        _, sa = add_customer(add_address(), [add_device()], age_days=rnd.randint(1500, 4000))
        edges.append(("Account", sa, "SETTLES_FOR", "Merchant", m))

    # ---- legitimate customers: mostly one device/one address; a few innocent household overlaps
    legit_accts = []
    households = []
    for _ in range(n_legit):
        if households and rnd.random() < 0.08:
            addr, shared_dev = rnd.choice(households)       # family sharing a home (innocent)
            devs = [shared_dev] if rnd.random() < 0.3 else [add_device()]
        else:
            addr, shared_dev = add_address(), add_device()
            households.append((addr, shared_dev))
            devs = [shared_dev]
        _, acct = add_customer(addr, devs)
        legit_accts.append(acct)

    # ---- legit traffic
    for _ in range(1400):
        a = rnd.choice(legit_accts)
        when = t0 + timedelta(minutes=rnd.randint(0, 40 * 24 * 60))
        if rnd.random() < 0.7:
            add_txn(a, None, rnd.randint(80, 4500), when, "purchase", rnd.choice(merchants))
        else:
            b = rnd.choice(legit_accts)
            if b != a:
                add_txn(a, b, rnd.randint(200, 9000), when)

    # ---- RING A: carousel. 6 accounts, 3 shared devices, money cycles A->B->C->D->E->F->A, amounts decay slightly
    shared_devs = [add_device() for _ in range(3)]
    ring_a_addrs = [add_address() for _ in range(3)]
    ring_a = []
    for i in range(6):
        _, acct = add_customer(ring_a_addrs[i % 3], [shared_devs[i % 3], shared_devs[(i + 1) % 3]], age_days=rnd.randint(20, 60))
        ring_a.append(acct)
    base = t0 + timedelta(days=30)
    amt = 48000
    for lap in range(3):
        for i, a in enumerate(ring_a):
            add_txn(a, ring_a[(i + 1) % 6], amt, base + timedelta(hours=lap * 20 + i * 2))
            amt *= 0.985
    truth["RING_A"] = set(ring_a)

    # ---- RING B: mule farm. 9 synthetic identities at ONE address, unverified KYC, all drain to a hub
    farm_addr = add_address("Pune", "14 Lake View")
    hub_cust, hub = add_customer(farm_addr, [add_device()], age_days=15, kyc="pending")
    mules = []
    for i in range(9):
        _, m = add_customer(farm_addr, [add_device()], age_days=rnd.randint(5, 25), kyc="pending")
        mules.append(m)
        # incoming from random legit victims, then outgoing to the hub
        for _ in range(2):
            add_txn(rnd.choice(legit_accts), m, rnd.randint(4000, 9500), base + timedelta(hours=rnd.randint(0, 200)))
        add_txn(m, hub, rnd.randint(7000, 17000), base + timedelta(hours=rnd.randint(210, 260)))
    truth["RING_B"] = set(mules) | {hub}

    # ---- RING C: fan-in to a shell merchant, then pay out to cash-out accounts
    shell = add_merchant("MERCH_SHELL1", "QuickRefund Services", "electronics", shell=True)
    victims = rnd.sample(legit_accts, 14)
    for v in victims:
        add_txn(v, None, rnd.randint(1500, 6000), base + timedelta(hours=rnd.randint(0, 150)), "purchase", shell)
    cashout_devs = [add_device() for _ in range(2)]
    cashout = []
    for i in range(3):
        _, c = add_customer(add_address(), [cashout_devs[i % 2]], age_days=rnd.randint(10, 40))
        cashout.append(c)
    # shell merchant settles to cash-out accounts: model as txns from a settlement account owned by the same operator
    _, settle = add_customer(add_address(), [cashout_devs[0]], age_days=30)
    nodes["Merchant"][-1]["settles_via"] = settle
    edges.append(("Account", settle, "SETTLES_FOR", "Merchant", shell))
    for c in cashout:
        add_txn(settle, c, rnd.randint(18000, 26000), base + timedelta(hours=rnd.randint(160, 230)))
    truth["RING_C"] = set(cashout) | {settle}

    return nodes, edges, truth


if __name__ == "__main__":
    n, e, t = generate()
    print({k: len(v) for k, v in n.items()}, "edges:", len(e))
    print({k: len(v) for k, v in t.items()})
