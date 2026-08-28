#!/usr/bin/env python3
"""Small, dependency-free lease locks for archive automations.

Locks live under .git, so they are never published.  A lease has an explicit
owner and expiry; only that owner can release it.  Expired leases are moved
aside atomically before a new owner is admitted.
"""

import argparse
import json
import os
import shutil
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def lock_root(repo):
    root = Path(repo).resolve() / ".git" / "archive-locks"
    root.mkdir(parents=True, exist_ok=True)
    return root


def lock_path(repo, name):
    if not name or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in name):
        raise ValueError("lock name may only contain letters, numbers, '-' and '_'")
    return lock_root(repo) / (name + ".lock")


def read_owner(path):
    try:
        with (path / "owner.json").open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def acquire(args):
    path = lock_path(args.repo, args.name)
    now = time.time()
    payload = {
        "schema_version": 1,
        "name": args.name,
        "owner": args.owner,
        "pid": os.getpid(),
        "host": os.uname().nodename,
        "acquired_at_utc": utc_now(),
        "acquired_at_epoch": now,
        "expires_at_epoch": now + args.ttl,
        "ttl_seconds": args.ttl,
    }
    for _ in range(2):
        try:
            path.mkdir()
            tmp = path / ("owner.%s.tmp" % uuid.uuid4().hex)
            with tmp.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(str(tmp), str(path / "owner.json"))
            print(json.dumps({"acquired": True, "lock": str(path), "owner": payload}, ensure_ascii=False))
            return 0
        except FileExistsError:
            current = read_owner(path)
            expires = float(current.get("expires_at_epoch", 0) or 0)
            if expires > now:
                print(json.dumps({"acquired": False, "reason": "busy", "lock": str(path), "owner": current}, ensure_ascii=False))
                return 3
            stale = path.with_name(path.name + ".stale-" + uuid.uuid4().hex)
            try:
                os.replace(str(path), str(stale))
                shutil.rmtree(str(stale), ignore_errors=True)
            except FileNotFoundError:
                continue
    print(json.dumps({"acquired": False, "reason": "race", "lock": str(path)}, ensure_ascii=False))
    return 4


def release(args):
    path = lock_path(args.repo, args.name)
    if not path.exists():
        print(json.dumps({"released": True, "reason": "already_absent", "lock": str(path)}, ensure_ascii=False))
        return 0
    current = read_owner(path)
    if current.get("owner") != args.owner:
        print(json.dumps({"released": False, "reason": "owner_mismatch", "lock": str(path), "owner": current}, ensure_ascii=False))
        return 5
    tombstone = path.with_name(path.name + ".released-" + uuid.uuid4().hex)
    try:
        os.replace(str(path), str(tombstone))
        shutil.rmtree(str(tombstone), ignore_errors=True)
    except FileNotFoundError:
        pass
    print(json.dumps({"released": True, "lock": str(path), "owner": args.owner}, ensure_ascii=False))
    return 0


def status(args):
    path = lock_path(args.repo, args.name)
    owner = read_owner(path) if path.exists() else None
    expired = bool(owner and float(owner.get("expires_at_epoch", 0) or 0) <= time.time())
    print(json.dumps({"locked": path.exists(), "expired": expired, "lock": str(path), "owner": owner}, ensure_ascii=False))
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    subparsers = parser.add_subparsers(dest="command", required=True)
    acquire_parser = subparsers.add_parser("acquire")
    acquire_parser.add_argument("--name", required=True)
    acquire_parser.add_argument("--owner", required=True)
    acquire_parser.add_argument("--ttl", type=int, default=5400)
    acquire_parser.set_defaults(func=acquire)
    release_parser = subparsers.add_parser("release")
    release_parser.add_argument("--name", required=True)
    release_parser.add_argument("--owner", required=True)
    release_parser.set_defaults(func=release)
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--name", required=True)
    status_parser.set_defaults(func=status)
    args = parser.parse_args()
    if hasattr(args, "ttl") and args.ttl < 60:
        parser.error("--ttl must be at least 60 seconds")
    try:
        return args.func(args)
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    sys.exit(main())
