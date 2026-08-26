#!/usr/bin/env python3
"""Collect every Hacker News story in an item-id window.

The remote Git state is the source of truth. If a GitHub push fails, the next
run reads the old remote cursor and safely replays the same window.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import html
import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo


API_ROOT = "https://hacker-news.firebaseio.com/v0"
DOCS_URL = "https://github.com/HackerNews/API"
USER_AGENT = "daily-content-archive/1.0"


def fetch_json(url: str, retries: int = 4):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt + 1 == retries:
                raise
            time.sleep(2**attempt)


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def load_state(repo: Path, state_ref: str | None) -> dict:
    relative = "hackernews/state.json"
    if state_ref:
        result = subprocess.run(
            ["git", "show", f"{state_ref}:{relative}"],
            cwd=repo,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Cannot read authoritative cursor from {state_ref}:{relative}: "
                f"{result.stderr.strip()}"
            )
        return json.loads(result.stdout)
    return json.loads((repo / relative).read_text(encoding="utf-8"))


def fetch_item(item_id: int):
    return item_id, fetch_json(f"{API_ROOT}/item/{item_id}.json")


def normalize_item(item: dict, retrieved_at: str) -> dict:
    item_id = int(item["id"])
    item_type = item.get("type")
    normalized = {
        "item_id": item_id,
        "type": item_type,
        "title": html.unescape(item.get("title", "")) if item_type == "story" else None,
        "by": item.get("by"),
        "created_at_utc": dt.datetime.fromtimestamp(
            item.get("time", 0), tz=dt.timezone.utc
        ).isoformat().replace("+00:00", "Z"),
        "url": item.get("url") or f"https://news.ycombinator.com/item?id={item_id}",
        "hn_url": f"https://news.ycombinator.com/item?id={item_id}",
        "score": item.get("score", 0),
        "comments": item.get("descendants", 0),
        "parent": item.get("parent"),
        "kids": item.get("kids", []),
        "dead": bool(item.get("dead", False)),
        "deleted": bool(item.get("deleted", False)),
        "text": item.get("text"),
        "retrieved_at_utc": retrieved_at,
    }
    return normalized


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument(
        "--state-ref",
        help="Git ref containing the authoritative pushed state, e.g. origin/main",
    )
    parser.add_argument("--workers", type=int, default=24)
    args = parser.parse_args()

    repo = args.repo.resolve()
    state = load_state(repo, args.state_ref)
    start_id = int(state["last_max_item"])
    end_id = int(fetch_json(f"{API_ROOT}/maxitem.json"))
    if end_id < start_id:
        raise RuntimeError(f"HN maxitem moved backwards: {end_id} < {start_id}")

    retrieved = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    retrieved_at = retrieved.isoformat().replace("+00:00", "Z")
    failures: list[tuple[int, str]] = []
    null_ids: list[int] = []
    items: list[dict] = []

    ids = range(start_id + 1, end_id + 1)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_ids = {pool.submit(fetch_item, item_id): item_id for item_id in ids}
        for future in concurrent.futures.as_completed(future_ids):
            item_id = future_ids[future]
            try:
                _, item = future.result()
            except Exception as exc:  # preserve the failed ID; never advance cursor
                failures.append((item_id, str(exc)))
                continue
            if item is None:
                null_ids.append(item_id)
            elif item.get("type") in {"story", "comment"}:
                items.append(normalize_item(item, retrieved_at))

    if failures:
        sample = failures[:20]
        raise RuntimeError(
            f"Incomplete HN window: {len(failures)} item requests failed; sample={sample}"
        )

    items.sort(key=lambda value: value["item_id"])
    local_end = retrieved.astimezone(ZoneInfo("Asia/Shanghai"))
    folder = Path(
        "hackernews/raw",
        f"{local_end.year:04d}",
        f"{local_end.month:02d}",
        f"{local_end.day:02d}",
    )
    stem = f"items-{start_id + 1}-{end_id}"
    raw_path = repo / folder / f"{stem}.jsonl"
    raw_text = "".join(
        json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in items
    )
    atomic_write(raw_path, raw_text)

    run_path = repo / str(folder).replace("raw", "runs", 1) / f"{stem}.json"
    run_record = {
        "schema_version": 1,
        "source": API_ROOT + "/",
        "source_documentation": DOCS_URL,
        "range_start_id_exclusive": start_id,
        "range_end_id_inclusive": end_id,
        "ids_checked": max(0, end_id - start_id),
        "story_count": sum(item["type"] == "story" for item in items),
        "comment_count": sum(item["type"] == "comment" for item in items),
        "null_item_ids": null_ids,
        "request_failures": [],
        "retrieved_at_utc": retrieved_at,
        "raw_file": str(raw_path.relative_to(repo)),
        "complete": True,
    }
    atomic_write(
        run_path,
        json.dumps(run_record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )

    next_state = {
        "schema_version": 1,
        "source": API_ROOT + "/",
        "source_documentation": DOCS_URL,
        "last_max_item": end_id,
        "last_collected_at_utc": retrieved_at,
        "continuity_started_at_utc": state["continuity_started_at_utc"],
        "last_raw_file": str(raw_path.relative_to(repo)),
        "last_run_file": str(run_path.relative_to(repo)),
    }
    atomic_write(
        repo / "hackernews/state.json",
        json.dumps(next_state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )

    print(
        json.dumps(
            {
                "complete": True,
                "start_id_exclusive": start_id,
                "end_id_inclusive": end_id,
                "stories": sum(item["type"] == "story" for item in items),
                "comments": sum(item["type"] == "comment" for item in items),
                "raw_file": str(raw_path.relative_to(repo)),
                "run_file": str(run_path.relative_to(repo)),
                "state_file": "hackernews/state.json",
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
