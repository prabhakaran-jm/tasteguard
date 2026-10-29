"""Five consecutive live Lisbon stress evaluate→repair checks."""

from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error

BASE = "https://tasteguard-342276031814.us-central1.run.app"


def post(path: str, body: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def one_run(i: int) -> None:
    _, prop = post(
        "/api/propose", {"preset_id": "stress-lisbon-live", "force_live": False}
    )
    code_e, ev = post(
        "/api/evaluate",
        {
            "preset_id": "stress-lisbon-live",
            "force_live": False,
            "candidates": prop["candidates"],
        },
    )
    assert code_e == 200, (i, code_e, ev)
    assert ev["result"]["policy_verdict"] == "FAIL", ev["result"]["policy_verdict"]
    keepers = {
        c["input"]["name"]
        for c in ev["result"]["candidates"]
        if c["item_verdict"] == "allow"
    }
    assert {"A Cevicheria", "Cervejaria Ramiro"} <= keepers, keepers
    code_r, rep = post("/api/repair", {"evaluation_id": ev["evaluation_id"]})
    assert code_r == 200, (i, code_r, rep)
    final = rep["final"]
    assert final["policy_verdict"] == "PASS", final.get("message")
    names = [c["input"]["name"] for c in final["candidates"]]
    assert len(names) == 5 and len(set(names)) == 5, names
    assert all(c["item_verdict"] == "allow" for c in final["candidates"])
    assert {"A Cevicheria", "Cervejaria Ramiro"} <= set(names)
    print(f"run {i}: PASS {names}")


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    for i in range(1, n + 1):
        one_run(i)
    print(f"ALL {n} LIVE STRESS RUNS PASSED")


if __name__ == "__main__":
    main()
