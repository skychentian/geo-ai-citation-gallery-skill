#!/usr/bin/env python3
"""Normalize analytical hashtags without truncation. See references/hashtags.md."""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from copy import deepcopy
from pathlib import Path


def _norm_one(tag: str) -> str:
    t = unicodedata.normalize("NFKC", tag or "").strip()
    if not t:
        return ""
    if not t.startswith("#"):
        t = "#" + t.lstrip("#")
    return t


def normalize_hashtags(tags, limit: int | None = None) -> tuple[list[str], bool]:
    if tags is None:
        return [], False
    if isinstance(tags, str):
        parts = re.split(r"[\s,，]+", unicodedata.normalize("NFKC", tags))
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
    truncated = limit is not None and len(out) > limit
    return out, truncated


def _patch_obj(obj: dict, limit: int | None = None) -> bool:
    if "hashtags" not in obj and "tags" not in obj:
        return False
    if limit is not None and limit < 0:
        raise ValueError("limit must be non-negative")
    key = "hashtags" if "hashtags" in obj else "tags"
    obj.setdefault("hashtags_raw", deepcopy(obj.get(key)))
    # Repeated runs always derive analytical tags from the preserved source.
    new, truncated = normalize_hashtags(obj["hashtags_raw"], limit=limit)
    obj[key] = new
    obj["hashtags"] = new
    if limit is not None:
        obj["hashtags_display"] = new[:limit]
        obj["hashtags_display_truncated"] = truncated
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Preserve source tags and normalize all analytical tags.")
    ap.add_argument("path", type=Path, help="JSON file: object, list, or {items|videos|data: [...]}")
    ap.add_argument("--limit", type=int, default=None, help="Optional display-only cap; analytical hashtags stay complete")
    ap.add_argument("-i", "--inplace", action="store_true")
    args = ap.parse_args()
    if args.limit is not None and args.limit < 0:
        ap.error("--limit must be non-negative")
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
