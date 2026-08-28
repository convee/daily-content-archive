#!/usr/bin/env python3
"""Validate archive integrity and publication gates for every platform."""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


PLATFORMS = ("hackernews", "twitter", "reddit", "producthunt")
ID_PATTERNS = {
    "twitter": re.compile(r"(?<!\d)\d{15,22}(?!\d)"),
    "reddit": re.compile(r"\bt[13]_[a-z0-9]+\b"),
}


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def iter_jsonl(path):
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                try:
                    yield line_number, json.loads(line)
                except ValueError as exc:
                    raise ValueError("%s:%d: %s" % (path, line_number, exc))


def add_issue(report, severity, code, message, path=None):
    item = {"severity": severity, "code": code, "message": message}
    if path:
        item["path"] = str(path)
    report["issues"].append(item)


def find_references(value, prefix=""):
    refs = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = (prefix + "." + key).strip(".")
            if isinstance(child, str) and (key.endswith("_file") or key in ("raw_file", "run", "archive_file", "last_raw_file", "last_run_file")):
                if child.endswith((".json", ".jsonl", ".md")):
                    refs.append((child_prefix, child))
            elif key == "raw_files" and isinstance(child, list):
                refs.extend((child_prefix, item) for item in child if isinstance(item, str))
            refs.extend(find_references(child, child_prefix))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            refs.extend(find_references(child, "%s[%d]" % (prefix, index)))
    return refs


def latest_json(paths):
    valid = []
    for path in paths:
        try:
            data = load_json(path)
        except (OSError, ValueError):
            continue
        stamp = ""
        for key in ("finished_at_utc", "run_at", "run_at_utc", "retrieved_at_utc", "started_at_utc"):
            if isinstance(data.get(key), str):
                stamp = data[key]
                break
        valid.append((stamp, str(path), path, data))
    if not valid:
        return None, None
    _, _, path, data = max(valid)
    return path, data


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    fields = {}
    for line in text[4:end].splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip().lower()
    return fields, text[end + 5:]


def validate_syntax(repo, platform, report):
    json_count = jsonl_count = record_count = 0
    for path in sorted((repo / platform).rglob("*.json")):
        json_count += 1
        try:
            load_json(path)
        except (OSError, ValueError) as exc:
            add_issue(report, "error", "invalid_json", str(exc), path.relative_to(repo))
    for path in sorted((repo / platform).rglob("*.jsonl")):
        jsonl_count += 1
        try:
            record_count += sum(1 for _ in iter_jsonl(path))
        except (OSError, ValueError) as exc:
            add_issue(report, "error", "invalid_jsonl", str(exc), path.relative_to(repo))
    report["metrics"].update({"json_files": json_count, "jsonl_files": jsonl_count, "jsonl_records": record_count})


def validate_refs(repo, platform, report, documents):
    checked = set()
    for source_path, data in documents:
        for field, reference in find_references(data):
            if reference in checked:
                continue
            checked.add(reference)
            target = repo / reference
            if not target.is_file():
                add_issue(report, "error", "missing_reference", "%s references missing %s (%s)" % (source_path.relative_to(repo), reference, field), reference)
    report["metrics"]["references_checked"] = len(checked)


def raw_ids(repo, platform):
    pattern = ID_PATTERNS[platform]
    found = set()
    for path in (repo / platform / "raw").rglob("*"):
        if path.suffix not in (".json", ".jsonl") or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        found.update(pattern.findall(text))
    return found


def validate_daily(repo, platform, report):
    public = []
    partial_public = []
    for path in sorted((repo / platform).glob("[0-9][0-9][0-9][0-9]/*/*.md")):
        fields, body = frontmatter(path)
        is_public = fields.get("archive_page") in ("true", "yes")
        if is_public:
            public.append((path, body))
            if "测试简报" in body or "生产游标未推进" in body:
                partial_public.append(path)
    report["metrics"]["public_daily_pages"] = len(public)
    for path in partial_public:
        add_issue(report, "error", "partial_page_public", "partial/test evidence must not be exposed as a formal daily", path.relative_to(repo))
    if platform in ("hackernews", "twitter", "reddit") and not public:
        add_issue(report, "error", "no_public_daily", "platform has no formal public daily")
    if public:
        path, body = public[-1]
        if "溯源" not in body or ".json" not in body:
            add_issue(report, "error", "daily_missing_evidence", "latest public daily must link raw and run evidence", path.relative_to(repo))


def validate_hackernews(repo, report, state, run_path, run):
    if not run:
        add_issue(report, "error", "missing_run", "no Hacker News run found")
        return
    if run.get("complete") is not True or run.get("request_failures"):
        add_issue(report, "error", "incomplete_run", "latest Hacker News run is not complete", run_path.relative_to(repo))
    if state.get("last_max_item") != run.get("range_end_id_inclusive"):
        add_issue(report, "error", "cursor_mismatch", "state cursor does not match latest run end")
    raw = repo / str(run.get("raw_file", ""))
    if raw.is_file():
        records = list(iter_jsonl(raw))
        expected = int(run.get("story_count", 0)) + int(run.get("comment_count", 0))
        if len(records) != expected:
            add_issue(report, "error", "count_mismatch", "raw records %d != story+comment %d" % (len(records), expected), raw.relative_to(repo))
        if int(run.get("ids_checked", 0)) != int(run.get("range_end_id_inclusive", 0)) - int(run.get("range_start_id_exclusive", 0)):
            add_issue(report, "error", "window_mismatch", "ids_checked does not equal the inclusive window size", run_path.relative_to(repo))


def validate_twitter(repo, report, state, run_path, run):
    seen = set(str(item) for item in state.get("seen_status_ids", []))
    archived = raw_ids(repo, "twitter")
    missing = seen - archived
    report["metrics"].update({"seen_status_ids": len(seen), "raw_status_ids": len(archived), "missing_seen_status_ids": len(missing)})
    if missing:
        add_issue(report, "error", "seen_not_durable", "%d state status IDs are absent from raw evidence" % len(missing))
    if run and run.get("status") not in ("complete", "success"):
        add_issue(report, "warning", "latest_run_degraded", "latest Twitter run is %s; failed sources must retain their cursors" % run.get("status"), run_path.relative_to(repo))
    if run and not run.get("raw_files"):
        add_issue(report, "error", "run_missing_raw", "latest Twitter run has no durable raw_files", run_path.relative_to(repo))


def validate_reddit(repo, report, state, run_path, run):
    seen_posts = set(str(item) for item in state.get("seen_post_ids", []))
    seen_comments = set(str(item) for item in state.get("seen_comment_ids", []))
    archived = raw_ids(repo, "reddit")
    missing_posts = seen_posts - archived
    missing_comments = seen_comments - archived
    report["metrics"].update({"seen_post_ids": len(seen_posts), "seen_comment_ids": len(seen_comments), "raw_reddit_ids": len(archived)})
    if missing_posts or missing_comments:
        add_issue(report, "error", "seen_not_durable", "%d post and %d comment IDs are absent from raw evidence" % (len(missing_posts), len(missing_comments)))
    if run and run.get("failures"):
        add_issue(report, "warning", "latest_run_degraded", "latest Reddit run has %d independently frozen sources" % len(run["failures"]), run_path.relative_to(repo))
    if run and not run.get("raw_file"):
        add_issue(report, "error", "run_missing_raw", "latest Reddit run has no durable raw_file", run_path.relative_to(repo))


def validate_producthunt(repo, report, state, run_path, run):
    if not state.get("last_complete_date"):
        add_issue(report, "warning", "no_complete_date", "Product Hunt has no date that passed every formal publication gate")
    for date, ledger in state.get("date_ledger", {}).items():
        if ledger.get("status") == "complete" and ledger.get("missing_gates"):
            add_issue(report, "error", "invalid_complete_date", "%s is complete but still has missing gates" % date)
    if run and run.get("outcome") not in ("complete", "success"):
        add_issue(report, "warning", "latest_run_degraded", "latest Product Hunt formal run is %s" % run.get("outcome"), run_path.relative_to(repo))


def check_platform(repo, platform):
    report = {"platform": platform, "checked_at_utc": utc_now(), "status": "healthy", "metrics": {}, "issues": []}
    validate_syntax(repo, platform, report)
    state_path = repo / platform / "state.json"
    try:
        state = load_json(state_path)
    except (OSError, ValueError) as exc:
        add_issue(report, "error", "invalid_state", str(exc), state_path.relative_to(repo))
        state = {}
    run_globs = {
        "hackernews": [repo / platform / "runs"],
        "twitter": [repo / platform / "runs"],
        "reddit": [repo / platform / "runs"],
        "producthunt": [repo / platform / "run", repo / platform / "runs"],
    }
    run_paths = []
    for root in run_globs[platform]:
        if root.exists():
            run_paths.extend(root.rglob("*.json"))
    if platform == "producthunt":
        run_paths = [path for path in run_paths if ".intraday-" not in path.name and "snapshot" not in path.name]
    run_path, run = latest_json(run_paths)
    documents = [(state_path, state)]
    if run_path and run:
        documents.append((run_path, run))
        report["latest_run"] = str(run_path.relative_to(repo))
    validate_refs(repo, platform, report, documents)
    validate_daily(repo, platform, report)
    if platform == "hackernews":
        validate_hackernews(repo, report, state, run_path, run)
    elif platform == "twitter":
        validate_twitter(repo, report, state, run_path, run)
    elif platform == "reddit":
        validate_reddit(repo, report, state, run_path, run)
    else:
        validate_producthunt(repo, report, state, run_path, run)
    severities = set(issue["severity"] for issue in report["issues"])
    if "error" in severities:
        report["status"] = "unhealthy"
    elif "warning" in severities:
        report["status"] = "degraded"
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--platform", choices=PLATFORMS + ("all",), default="all")
    parser.add_argument("--strict", action="store_true", help="also fail on degraded status")
    parser.add_argument("--output", help="write the JSON report to this path")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    platforms = PLATFORMS if args.platform == "all" else (args.platform,)
    result = {"schema_version": 1, "checked_at_utc": utc_now(), "platforms": [check_platform(repo, item) for item in platforms]}
    encoded = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    if any(item["status"] == "unhealthy" for item in result["platforms"]):
        return 1
    if args.strict and any(item["status"] == "degraded" for item in result["platforms"]):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
