#!/usr/bin/env python3
"""Record a Twitter collection attempt when the required Chrome surface is unavailable.

No collection cursors advance.  The durable ledger captures every required source
and preserves its prior continuation evidence for the next successful browser run.
"""
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


def now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


repo = Path(sys.argv[1]).resolve()
owner = sys.argv[2]
captured_at = now_utc()
stamp = captured_at.replace("-", "").replace(":", "")
day = (datetime.fromisoformat(captured_at.replace("Z", "+00:00")) + timedelta(hours=8)).strftime("%Y/%m/%d")
raw_rel = f"twitter/raw/{day}/{stamp}-browser-unavailable.jsonl"
run_rel = f"twitter/runs/{day}/{stamp}.json"
state_path = repo / "twitter/state.json"
sources = json.loads((repo / "twitter/sources.json").read_text(encoding="utf-8"))
state = json.loads(state_path.read_text(encoding="utf-8"))
frozen = state.setdefault("frozen_sources", {})
error = "Chrome browser connection unavailable; no read-only authenticated surface available"

def attempt(kind, name, url):
    key = f"{kind}:{name}" if kind in {"account", "query"} else name
    prior = frozen.get(key, {})
    continuation = prior.get("continuation")
    return {"record_type": "source_attempt", "captured_at": captured_at,
            "source": key, "source_type": kind, "requested_url": url,
            "actual_url": None, "title": None, "stability_samples": [],
            "stable": False, "retry_count": 1, "batches": 0,
            "error": error, "observed_status_ids": [], "deepest_status_id": None,
            "checkpoint_reached": False, "continuation_input": continuation,
            "continuation_output": continuation}

records = []
for account in sources["official_accounts"] + sources["expert_accounts"]:
    records.append(attempt("account", account, f"https://x.com/{account}"))
for query in sources["topic_queries"]:
    records.append(attempt("query", query, "https://x.com/search?q=" + query.replace(" ", "%20") + "&f=live"))
records.append(attempt("following", "following", "https://x.com/home"))
records.append(attempt("for_you", "for_you", "https://x.com/home"))

raw_path = repo / raw_rel
run_path = repo / run_rel
raw_path.parent.mkdir(parents=True, exist_ok=True)
run_path.parent.mkdir(parents=True, exist_ok=True)
with raw_path.open("w", encoding="utf-8") as out:
    for record in records:
        out.write(json.dumps(record, ensure_ascii=False) + "\n")

for record in records:
    key = record["source"]
    prior = frozen.get(key, {})
    frozen[key] = {"frozen_at_utc": captured_at, "reason": error,
                   "last_deepest_status_id": prior.get("last_deepest_status_id"),
                   "last_raw_file": raw_rel, "continuation": prior.get("continuation"),
                   "previous_continuation": prior.get("previous_continuation")}
state["last_run_at_utc"] = captured_at
state["last_run_status"] = "partial_frozen"
state["last_run_reason"] = error
state["last_raw_file"] = raw_rel
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

by_kind = {kind: [r for r in records if r["source_type"] == kind] for kind in ("account", "query", "following", "for_you")}
run = {"schema_version": 3, "platform": "twitter", "status": "partial_frozen",
       "started_at_utc": captured_at, "completed_at_utc": now_utc(), "lock_owner": owner,
       "browser": {"surface": "Chrome", "read_only": True, "stable_samples_required": 3,
                   "connection": "unavailable"}, "raw_files": [raw_rel],
       "records": {"posts_observed": 0, "new_status_ids": 0, "replies_checked": 0, "replies_selected": 0},
       "layers": {"accounts": {"attempted": 19, "success": 0, "failure": 19, "sources": by_kind["account"]},
                  "queries": {"attempted": 5, "success": 0, "failure": 5, "sources": by_kind["query"]},
                  "following": {"attempted": 1, "success": 0, "failure": 1, "sources": by_kind["following"]},
                  "for_you": {"attempted": 1, "success": 0, "failure": 1, "sources": by_kind["for_you"]},
                  "replies": {"attempted": 0, "success": 0, "failure": 1, "reason": error}},
       "continuation": {"input": "origin/main frozen checkpoints and continuation evidence", "output": "unchanged; browser unavailable"},
       "health": {"pre_publish": "degraded_without_errors"},
       "publication": {"eligible": False, "reason": "partial frozen run; no public daily update"},
       "github": {"status": "pending_commit_and_push"}, "dingtalk": {"status": "not_sent"}}
run_path.write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"raw": raw_rel, "run": run_rel, "captured_at": captured_at}, ensure_ascii=False))
