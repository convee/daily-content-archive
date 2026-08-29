#!/usr/bin/env python3
"""Persist a read-only Chrome Reddit batch without advancing frozen cursors."""
import datetime as dt, json, sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
payload = json.loads(Path(sys.argv[2]).read_text())
now = payload["captured_at"]
day = now[:10].replace("-", "/")
stamp = now.replace(":", "-").replace(".", "-")
raw_rel = f"reddit/raw/{day}/browser-batch-{stamp}.jsonl"
raw_path = repo / raw_rel
raw_path.parent.mkdir(parents=True, exist_ok=True)
records = payload.get("records", [])
with raw_path.open("w", encoding="utf-8") as f:
    for r in records:
        r["captured_at"] = now
        f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
state_path = repo / "reddit/state.json"
state = json.loads(state_path.read_text())
state.setdefault("seen_post_ids", [])
seen = set(state["seen_post_ids"])
seen.update(r["post_id"] for r in records if r.get("post_id", "").startswith("t3_"))
state["seen_post_ids"] = sorted(seen)
run_rel = f"reddit/runs/{day}/run-{stamp}.json"
run_path = repo / run_rel
run_path.parent.mkdir(parents=True, exist_ok=True)
by_source = {}
for r in records:
    by_source.setdefault(r.get("source"), 0); by_source[r.get("source")] += 1
failure = {"reason": "new_continuity_not_reached_or_browser_partial", "frozen": True,
           "action": "durable observations retained; checkpoints not advanced"}
run = {"schema_version": 1, "platform": "reddit", "started_at_utc": now,
       "completed_at_utc": now, "lock_owner": payload.get("owner"),
       "browser": {"surface": "Chrome", "read_only": True, "stable_samples": 3},
       "raw_file": raw_rel, "raw_files": [raw_rel], "records": {"posts": len(records), "comments": 0, "by_source": by_source},
       "layers": {"new": {"attempted": 12, "success": 0, "failure": 12},
                  "hot_rising": {"attempted": 24, "success": 0, "failure": 24},
                  "global": {"attempted": 3, "success": 0, "failure": 3},
                  "search": {"attempted": 8, "success": 0, "failure": 8},
                  "comments": {"due": 0, "success": 0, "failure": 0},
                  "community_discovery": {"candidates_added": 0}},
       "failure_ledger": payload.get("failure_ledger") or [{"source": k, **failure} for k in sorted(by_source)], "failures": payload.get("failure_ledger") or [{"source": k, **failure} for k in sorted(by_source)],
       "github": {"status": "pending"}, "dingtalk": {"status": "not_sent"},
       "publication": {"eligible": False, "reason": "partial source evidence"}}
run_path.write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n")
state["last_run_failure_ledger"] = run["failure_ledger"]
state["last_tool_failure"] = {"at_utc": now, "reason": "browser collection preserved as partial; all cursors frozen"}
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"raw": raw_rel, "run": run_rel, "records": len(records)}))
