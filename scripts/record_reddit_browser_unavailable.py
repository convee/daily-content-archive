#!/usr/bin/env python3
"""Persist a no-browser Reddit attempt without advancing collection cursors."""
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
owner = sys.argv[2]
now = datetime.now(timezone.utc).replace(microsecond=0)
captured_at = now.isoformat().replace("+00:00", "Z")
day = (now + timedelta(hours=8)).strftime("%Y/%m/%d")
stamp = captured_at.replace(":", "-")
raw_rel = f"reddit/raw/{day}/browser-unavailable-{stamp}.jsonl"
run_rel = f"reddit/runs/{day}/run-{stamp}.json"
state_path = repo / "reddit/state.json"
sources = json.loads((repo / "reddit/sources.json").read_text(encoding="utf-8"))
state = json.loads(state_path.read_text(encoding="utf-8"))
communities = sources.get("priority_communities", sources.get("communities", []))
queries = sources.get("search_queries", sources.get("queries", []))
error = "Required logged-in local Chrome binding unavailable before navigation"

def entry(layer, source, checkpoint=None):
    return {"record_type": "source_attempt", "captured_at": captured_at,
            "layer": layer, "source": source, "checkpoint": checkpoint,
            "stable_samples": [], "retry_count": 1, "observed_post_ids": [],
            "status": "frozen", "error": error, "continuation_output": "unchanged"}

records = []
for name in communities:
    checkpoint = state.get("community_checkpoints", {}).get(name, {}).get("last_id")
    records.append(entry("new", name, checkpoint))
    records.append(entry("hot", name))
    records.append(entry("rising", name))
for name in ("Home", "Popular", "All"):
    records.append(entry("global", name))
for query in queries:
    records.append(entry("search", query, state.get("search_checkpoints", {}).get(query, {}).get("last_id")))

raw_path = repo / raw_rel
raw_path.parent.mkdir(parents=True, exist_ok=True)
with raw_path.open("w", encoding="utf-8") as out:
    for row in records:
        out.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

ledger = [
    {"source": "Chrome", "reason": error + "; no browser navigation or durable content capture occurred.", "frozen": True,
     "recovery": "Restore Chrome extension/connection; resume each source from saved checkpoint or continuation without cursor advancement."},
    {"source": f"New ({len(communities)} communities)", "reason": "Not run; no durable raw observations possible.", "frozen": True,
     "recovery": "Resume each /new feed independently to its boundary and archive every observed non-ad post before advancing only that checkpoint."},
    {"source": f"Hot/Rising ({len(communities) * 2} snapshots)", "reason": "Not run; no durable snapshots possible.", "frozen": True,
     "recovery": "Retry every Hot and Rising snapshot independently after Chrome recovery."},
    {"source": "Home/Popular/All", "reason": "Not run; no durable snapshots possible.", "frozen": True,
     "recovery": "Retry all three independently and verify All is distinct from Home."},
    {"source": f"Search ({len(queries)} queries)", "reason": "Not run; no modern Posts + New traversal occurred.", "frozen": True,
     "recovery": "Retry every query from its existing checkpoint after Chrome recovery."},
]
state["last_run_at_utc"] = captured_at
state["last_run_status"] = "partial_frozen"
state["last_run_failure_ledger"] = ledger
state["last_tool_failure"] = {"at_utc": captured_at, "reason": error}
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
run = {"schema_version": 2, "platform": "reddit", "status": "partial_frozen",
       "started_at_utc": captured_at, "completed_at_utc": captured_at, "lock_owner": owner,
       "browser": {"surface": "Chrome", "read_only": True, "status": "unavailable", "error": error,
                   "retries": [{"kind": "initial_binding", "result": "unavailable"}], "stability_sampling": "not_started"},
       "health": {"initial": "healthy", "final": "pending"}, "raw_file": raw_rel, "raw_files": [raw_rel],
       "records": {"posts": 0, "comments": 0, "selected_comments": 0},
       "layers": {"new": {"attempted": len(communities), "success": 0, "failure": len(communities)},
                  "hot_rising": {"attempted": len(communities) * 2, "success": 0, "failure": len(communities) * 2},
                  "global": {"attempted": 3, "success": 0, "failure": 3},
                  "search": {"attempted": len(queries), "success": 0, "failure": len(queries)},
                  "comments": {"due": 0, "success": 0, "failure": 0, "detail": "No comment page read; browser unavailable."},
                  "community_discovery": {"candidates_added": 0, "detail": "No source evidence captured."}},
       "failure_ledger": ledger, "github": {"status": "pending"}, "dingtalk": {"status": "not_sent"},
       "publication": {"eligible": False, "reason": "No durable content evidence; no daily brief or Pages replacement."}}
run_path = repo / run_rel
run_path.parent.mkdir(parents=True, exist_ok=True)
run_path.write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"raw": raw_rel, "run": run_rel, "communities": len(communities), "queries": len(queries)}, ensure_ascii=False))
