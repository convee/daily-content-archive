#!/usr/bin/env python3
"""Persist a Chrome-captured Reddit batch, advancing only proven cursors."""
import json, sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
capture = json.loads(Path(sys.argv[2]).read_text())
now = capture["captured_at"]
day = now[:10].replace("-", "/")
stamp = now.replace(":", "-").replace(".", "-")
raw_rel = f"reddit/raw/{day}/capture-{stamp}.jsonl"
run_rel = f"reddit/runs/{day}/run-{stamp}.json"
state_path = repo / "reddit/state.json"
state = json.loads(state_path.read_text())

historical = set()
for path in (repo / "reddit/raw").rglob("*.jsonl"):
    for line in path.open(encoding="utf-8", errors="replace"):
        try:
            item = json.loads(line)
            for ident in (item.get("post_id"), item.get("comment_id")):
                if ident: historical.add(ident)
        except json.JSONDecodeError: pass

posts, comments = {}, {}
def add_post(row):
    ident = row.get("post_id")
    if not ident: return
    row = dict(row); row["captured_at"] = now
    existing = posts.setdefault(ident, row)
    existing["source_labels"] = sorted(set(existing.get("source_labels", [])) | set(row.get("source_labels", [])))
def add_comment(row):
    ident = row.get("comment_id")
    if not ident: return
    row = dict(row); row["captured_at"] = now; row["capture_round"] = "revisit"
    existing = comments.setdefault(ident, row)
    existing["source_labels"] = sorted(set(existing.get("source_labels", [])) | set(row.get("source_labels", [])))

for payload in capture["new"].values():
    for row in payload.get("observed", []): add_post(row)
for payload in capture["snapshots"].values():
    for row in payload.get("observed", []): add_post(row)
for payload in capture["global"].values():
    for row in payload.get("observed", []): add_post(row)
for payload in capture["search"].values():
    for row in payload.get("observed", []): add_post(row)
for payload in capture["comments"].values():
    for row in payload.get("observed", []): add_comment(row)

written = [r for k,r in {**posts, **comments}.items() if k not in historical]
def record_id(row):
    return row.get("comment_id") or row.get("post_id")
raw_path = repo / raw_rel; raw_path.parent.mkdir(parents=True, exist_ok=True)
existing_raw = []
if raw_path.exists():
    for line in raw_path.open(encoding="utf-8", errors="replace"):
        try: existing_raw.append(json.loads(line))
        except json.JSONDecodeError: pass
with raw_path.open("w", encoding="utf-8") as out:
    merged_raw = {record_id(r): r for r in existing_raw}
    merged_raw.update({record_id(r): r for r in written})
    for row in sorted(merged_raw.values(), key=record_id):
        out.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

all_durable = historical | {ident for r in written for ident in (r.get("post_id"), r.get("comment_id")) if ident}
new_success = 0
new_failures = []
for community, payload in capture["new"].items():
    ids = {r["post_id"] for r in payload.get("observed", [])}
    proven = payload.get("status") == "success" and payload.get("crossed") and ids <= all_durable
    prior = state.setdefault("community_checkpoints", {}).setdefault(community, {})
    if proven:
        prior.update({"last_id": payload["new_head_id"], "first_id": payload["new_head_id"], "new_head_id": payload["new_head_id"], "previous_checkpoint": payload["checkpoint"], "previous_checkpoint_reached": True, "observed_post_ids": sorted(ids), "observed_count": len(ids), "written_count": len(ids), "captured_at": now, "scroll_batches": len(payload.get("stable_batches", [])), "last_raw_file": raw_rel, "status": "success", "continuation": None, "failure_reason": None})
        new_success += 1
    else:
        prior.update({"captured_at": now, "observed_post_ids": sorted(ids), "observed_count": len(ids), "written_count": len(ids), "last_raw_file": raw_rel, "status": "frozen", "continuation": {"next_url": payload.get("continuation"), "last_observed_id": payload.get("observed", [{}])[-1].get("post_id") if payload.get("observed") else None, "captured_at": now}, "failure_reason": "continuity_boundary_not_reached"})
        new_failures.append({"source": "New:"+community, "reason": "continuity boundary not reached in four stable pages", "frozen": True, "last_checkpoint": payload.get("checkpoint"), "recovery": "resume saved next_url and merge with this durable window"})

snap_success = 0
for key, payload in capture["snapshots"].items():
    entry = dict(payload); entry.pop("observed", None); entry["archive_file"] = raw_rel; entry["captured_at"] = now; entry["evidence_status"] = "durable_raw"; entry["frozen"] = payload.get("status") != "success"
    state.setdefault("community_discovery_snapshots", {})[key] = entry
    snap_success += payload.get("status") == "success"
for key, payload in capture["global"].items():
    entry = dict(payload); entry.pop("observed", None); entry["archive_file"] = raw_rel; entry["captured_at"] = now; entry["evidence_status"] = "durable_raw"; entry["frozen"] = payload.get("status") != "success"
    state.setdefault("global_feed_snapshots", {})[key] = entry
for query, payload in capture["search"].items():
    prior = state.setdefault("search_checkpoints", {}).setdefault(query, {})
    prior.update({"status": "frozen", "frozen": True, "last_attempt_at": now, "last_discovery_snapshot": {"actual_url": payload.get("actual_url"), "results": len(payload.get("observed", [])), "first_id": payload.get("first_id"), "last_id": payload.get("last_id"), "archive_file": raw_rel, "captured_at": now, "stable_counts": payload.get("stable_counts")}, "failure_reason": payload.get("reason", "search boundary not crossed")})

comment_success = 0
for post_id, payload in capture["comments"].items():
    if payload.get("status") == "success" and all(r.get("comment_id") in all_durable for r in payload.get("observed", [])):
        comment_success += 1
        state["thread_revisit_queue"] = [q for q in state.get("thread_revisit_queue", []) if q.get("post_id") != post_id]

state["seen_post_ids"] = sorted(set(state.get("seen_post_ids", [])) | set(posts))
state["seen_comment_ids"] = sorted(set(state.get("seen_comment_ids", [])) | set(comments))
state["last_successful_new_run_at_utc"] = now if new_success else state.get("last_successful_new_run_at_utc")
state["last_run_failure_ledger"] = new_failures + [{"source":"Search 8 queries", "reason":"all queries saved only discovery snapshots; time boundaries not crossed", "frozen":True, "recovery":"resume each modern Posts+New result stream"}]
state["last_tool_failure"] = {"at_utc": now, "reason":"search continuity remains frozen; New failures isolated to three saved continuations"}
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")

run = {"schema_version":2,"platform":"reddit","started_at_utc":now,"completed_at_utc":now,"lock_owner":capture["owner"],"browser":{"surface":"Chrome","read_only":True,"stable_samples":3},"raw_file":raw_rel,"raw_files":[raw_rel],"records":{"posts":len(posts),"comments":len(comments),"written":len(written)},"layers":{"new":{"attempted":12,"success":new_success,"failure":12-new_success},"hot_rising":{"attempted":24,"success":snap_success,"failure":24-snap_success},"global":{"attempted":3,"success":sum(v.get("status")=="success" for v in capture["global"].values()),"failure":sum(v.get("status")!="success" for v in capture["global"].values())},"search":{"attempted":8,"success":0,"failure":8},"comments":{"due":len(capture["comments"]),"success":comment_success,"failure":len(capture["comments"])-comment_success},"community_discovery":{"candidates_added":0}},"failure_ledger":state["last_run_failure_ledger"],"failures":state["last_run_failure_ledger"],"github":{"status":"pending"},"dingtalk":{"status":"not_sent"},"publication":{"eligible":False,"reason":"search continuity frozen"}}
run_path=repo/run_rel; run_path.parent.mkdir(parents=True,exist_ok=True); run_path.write_text(json.dumps(run,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({"raw":raw_rel,"run":run_rel,"posts":len(posts),"comments":len(comments),"written":len(written),"new_success":new_success,"snapshot_success":snap_success,"comment_success":comment_success},ensure_ascii=False))
