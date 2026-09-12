#!/usr/bin/env python3
"""Normalize Douyin hashtags to at most 5. See references/hashtags.md."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def _norm_one(tag: str) -> str:
    t = (tag or "").strip()
    if not t:
        return ""
    if not t.startswith("#"):
        t = "#" + t.lstrip("#")
    return t


def normalize_hashtags(tags, limit: int = 5) -> tuple[list[str], bool]:
    if tags is None:
        return [], False
    if isinstance(tags, str):
        parts = re.split(r"[\s,，]+", tags.replace("＃", "#"))
        tags = [p for p in parts if p.strip()]
    seen: set[str] = set()
    out: list[str] = []
    for raw in tags:
        t = _norm_one(str(raw))
        if not t:
            continue
        key = t.casefold().replace("＃", "#")
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    truncated = len(out) > limit
    return out[:limit], truncated


def _patch_obj(obj: dict, limit: int) -> bool:
    if "hashtags" not in obj and "tags" not in obj:
        return False
    key = "hashtags" if "hashtags" in obj else "tags"
    raw = obj.get(key)
    new, truncated = normalize_hashtags(raw, limit=limit)
    if truncated and "hashtags_raw" not in obj:
        obj["hashtags_raw"] = list(raw) if isinstance(raw, list) else raw
    obj[key] = new
    if truncated:
        obj["hashtags_truncated"] = True
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Cap hashtags at 5 (Douyin limit).")
    ap.add_argument("path", type=Path, help="JSON file: object, list, or {items|videos|data: [...]}")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("-i", "--inplace", action="store_true")
    args = ap.parse_args()
    data = json.loads(args.path.read_text(encoding="utf-8"))
    changed = False
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                changed = _patch_obj(item, args.limit) or changed
    elif isinstance(data, dict):
        nested = None
        for k in ("items", "videos", "data", "rows"):
            if isinstance(data.get(k), list):
                nested = data[k]
                break
        if nested is not None:
            for item in nested:
                if isinstance(item, dict):
                    changed = _patch_obj(item, args.limit) or changed
        else:
            changed = _patch_obj(data, args.limit) or changed
    else:
        print("unsupported JSON root", file=sys.stderr)
        return 2
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if args.inplace:
        args.path.write_text(text, encoding="utf-8")
        print(f"updated {args.path}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
