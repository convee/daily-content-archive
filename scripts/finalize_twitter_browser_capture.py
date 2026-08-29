#!/usr/bin/env python3
"""Persist one read-only Chrome Twitter sweep without advancing unproven cursors."""
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


repo = Path(sys.argv[1]).resolve()
capture = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
owner = capture["owner"]
captured_at = capture["captured_at"]
stamp = captured_at.replace("-", "").replace(":", "").replace("Z", "Z")
day = (datetime.fromisoformat(captured_at.replace("Z", "+00:00")) + timedelta(hours=8)).strftime("%Y/%m/%d")
raw_rel = f"twitter/raw/{day}/{stamp}-browser-sweep.jsonl"
run_rel = f"twitter/runs/{day}/{stamp}.json"
raw_path, run_path = repo / raw_rel, repo / run_rel
raw_path.parent.mkdir(parents=True, exist_ok=True)
run_path.parent.mkdir(parents=True, exist_ok=True)
state_path = repo / "twitter/state.json"
state = json.loads(state_path.read_text(encoding="utf-8"))

posts, sources_by_id = {}, defaultdict(set)
attempts = []
for source in capture["results"]:
    source_key = f"{source['kind']}:{source['name']}"
    ids = []
    for row in source.get("observed", []):
        sid = str(row.get("status_id") or "")
        if not sid:
            continue
        ids.append(sid)
        posts.setdefault(sid, row)
        sources_by_id[sid].add(source_key)
    attempts.append({
        "source": source_key, "source_type": source["kind"], "requested_url": source["requested_url"],
        "actual_url": source.get("actual_url"), "title": source.get("title"),
        "stability_samples": source.get("stability_samples", []), "stable": source.get("stable"),
        "retry_count": source.get("retry_count", 0), "batches": 1,
        "observed_status_ids": ids, "deepest_status_id": ids[-1] if ids else None,
        "checkpoint_reached": False, "continuation_input": state.get("frozen_sources", {}).get(source_key, {}).get("continuation"),
    })
for feed in capture["feeds"]:
    source_key = feed["name"]
    ids = []
    for row in feed.get("observed", []):
        sid = str(row.get("status_id") or "")
        if sid:
            ids.append(sid); posts.setdefault(sid, row); sources_by_id[sid].add(source_key)
    attempts.append({"source": source_key, "source_type": source_key, "requested_url": "https://x.com/home",
        "actual_url": feed.get("actual_url"), "batches": feed.get("batches", []), "observed_status_ids": ids,
        "deepest_status_id": ids[-1] if ids else None, "checkpoint_reached": False,
        "continuation_input": state.get("frozen_sources", {}).get(source_key, {}).get("continuation")})

reply_records = []
selected_reply_ids = {"2093386529846722913", "2093386531247718425", "2093386533638389907", "2093386535618113627", "2093442176919220624", "2093684355541368880", "2093508781002920226"}
for page in capture["replies"]:
    for row in page.get("observed_replies", []):
        sid = str(row.get("status_id") or "")
        if not sid: continue
        reply_records.append({"record_type":"reply","reply_id":sid,"parent_status_id":page["parent_status_id"],
          "author":row.get("author"),"posted_at_utc":row.get("posted_at_utc"),"permalink":row.get("permalink"),
          "text":row.get("text"),"public_engagement":{"likes":row.get("likes"),"replies":row.get("replies"),"reposts":row.get("reposts")},
          "captured_at":captured_at,"selected":sid in selected_reply_ids,
          "selection_reason":("official method/result detail" if sid.startswith("209338653") else "concrete quality or hardware caveat") if sid in selected_reply_ids else "checked but not selected"})

with raw_path.open("w", encoding="utf-8") as out:
    for attempt in attempts:
        out.write(json.dumps({"record_type":"source_attempt","captured_at":captured_at,**attempt}, ensure_ascii=False)+"\n")
    for sid, row in posts.items():
        out.write(json.dumps({"record_type":"status","status_id":sid,"author":row.get("author"),
          "posted_at_utc":row.get("posted_at_utc"),"text":row.get("text"),"permalink":row.get("permalink"),
          "media_or_links":[],"public_engagement":{"likes":row.get("likes"),"replies":row.get("replies"),"reposts":row.get("reposts")},
          "captured_at":captured_at,"source_types":sorted(sources_by_id[sid]),"thread_relationship":"unknown"}, ensure_ascii=False)+"\n")
    for row in reply_records: out.write(json.dumps(row, ensure_ascii=False)+"\n")

seen = set(map(str, state.get("seen_status_ids", [])))
new_ids = sorted(set(posts) - seen)
state["seen_status_ids"] = sorted(seen | set(posts), key=int)
state["last_run_at_utc"] = captured_at
state["last_run_status"] = "partial_frozen"
state["last_run_reason"] = "All 19 accounts, five Latest queries, Following and For You were attempted in read-only Chrome. Continuous checkpoints were not reached; all continuous cursors frozen. For You remains an incomplete eight-batch discovery snapshot."
frozen = state.setdefault("frozen_sources", {})
for attempt in attempts:
    key = attempt["source"]
    if key == "for_you": reason="eight_batches_completed_without_two_consecutive_zero_new_batches"
    elif key == "following": reason="continuity_boundary_not_reached_in_eight_batches"
    else: reason="continuity_boundary_not_reached_in_visible_stable_window"
    prior = frozen.get(key, {})
    frozen[key] = {"frozen_at_utc":captured_at,"reason":reason,"last_deepest_status_id":attempt["deepest_status_id"],"last_raw_file":raw_rel,
      "continuation":{"last_observed_id":attempt["deepest_status_id"],"captured_at":captured_at,"batches":len(attempt["batches"]) if isinstance(attempt["batches"],list) else attempt["batches"]},
      "previous_continuation":prior.get("continuation")}
state["last_raw_file"] = raw_rel

accounts=[a for a in attempts if a["source_type"]=="account"]
queries=[a for a in attempts if a["source_type"]=="query"]
following=[a for a in attempts if a["source"]=="following"]
for_you=[a for a in attempts if a["source"]=="for_you"]
run={"schema_version":3,"platform":"twitter","status":"partial_frozen","started_at_utc":captured_at,"completed_at_utc":utc_now(),
 "lock_owner":owner,"browser":{"surface":"Chrome","read_only":True,"stable_samples_required":3},"raw_files":[raw_rel],
 "records":{"posts_observed":len(posts),"new_status_ids":len(new_ids),"replies_checked":len(reply_records),"replies_selected":sum(r["selected"] for r in reply_records)},
 "layers":{"accounts":{"attempted":len(accounts),"success":0,"failure":len(accounts),"sources":accounts},"queries":{"attempted":len(queries),"success":0,"failure":len(queries),"sources":queries},"following":{"attempted":1,"success":0,"failure":1,"sources":following},"for_you":{"attempted":1,"success":0,"failure":1,"sources":for_you},"replies":{"attempted":len(capture["replies"]),"success":len(capture["replies"]),"failure":0,"pages":capture["replies"]}},
 "continuation":{"input":"state.frozen_sources","output":"updated per attempted source"},"health":{"pre_publish":"degraded_without_errors"},"publication":{"eligible":False,"reason":"partial frozen sweep; no public daily update"},"github":{"status":"pending_commit_and_push"},"dingtalk":{"status":"not_sent"}}
state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
run_path.write_text(json.dumps(run,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps({"raw":raw_rel,"run":run_rel,"posts":len(posts),"new":len(new_ids),"replies":len(reply_records),"selected_replies":sum(r["selected"] for r in reply_records)},ensure_ascii=False))
