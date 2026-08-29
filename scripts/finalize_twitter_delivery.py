#!/usr/bin/env python3
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
run_rel, commit, task, message, status = sys.argv[2:]
target = "cid4JFchXCBwQIK2cKxUXZwWw=="
state_path = repo / "twitter/state.json"
run_path = repo / run_rel
state = json.loads(state_path.read_text(encoding="utf-8"))
run = json.loads(run_path.read_text(encoding="utf-8"))
now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
delivery = {"status":"sent" if status == "SUCCESS" else "failed", "target_openConversationId":target,
 "target_verified":True, "message_type":"exception_alert", "openTaskId":task, "openMessageId":message,
 "sendStatus":status, "verified_at_utc":now}
run["github"] = {"status":"pushed","commit":commit,"remote":"origin/main","verified":True}
run["dingtalk"] = delivery
run["finalized_at_utc"] = now
state["last_dingtalk_delivery"] = delivery
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
run_path.write_text(json.dumps(run, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
