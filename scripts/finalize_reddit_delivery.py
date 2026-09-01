#!/usr/bin/env python3
"""Attach verified GitHub and DingTalk delivery facts to a Reddit run."""
import json, sys
from pathlib import Path

repo = Path(sys.argv[1])
run_path = repo / sys.argv[2]
commit, task, conversation, message, status = sys.argv[3:]
run = json.loads(run_path.read_text())
run["github"] = {"status": "pushed", "commit": commit, "remote": "origin/main"}
run["dingtalk"] = {"status": "sent", "openTaskId": task, "openConversationId": conversation, "openMessageId": message, "sendStatus": status}
if isinstance(run.get("health"), dict):
    run["health"]["final"] = "healthy"
run_path.write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n")
state_path = repo / "reddit/state.json"
state = json.loads(state_path.read_text())
state["last_dingtalk_delivery"] = run["dingtalk"]
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
