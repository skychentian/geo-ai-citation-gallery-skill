#!/usr/bin/env python3
"""
单条 URL 测试下载（带 Referer），用于验证 CDN 是否可拉、Referer 是否够。

用法：
  python download_one.py 'https://...' [out.png|out.bin]
  python download_one.py 'https://...' --png out.png   # 强制经 Pillow 存 PNG

依赖：标准库；--png 需要 pip install pillow
"""
from __future__ import annotations

import argparse
import io
import sys
import urllib.request

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
REFERER = "https://www.douyin.com/"


def main() -> int:
    p = argparse.ArgumentParser(description="Download one media URL with Douyin Referer")
    p.add_argument("url")
    p.add_argument("out", nargs="?", default="download_one.bin")
    p.add_argument("--png", metavar="PATH", help="decode with Pillow and save as PNG")
    args = p.parse_args()

    req = urllib.request.Request(
        args.url,
        headers={"User-Agent": UA, "Referer": REFERER},
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = resp.read()
            ctype = resp.headers.get("Content-Type", "")
    except Exception as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1

    print(f"ok bytes={len(data)} content-type={ctype!r}")

    if args.png:
        try:
            from PIL import Image
        except ImportError:
            print("FAIL: pip install pillow", file=sys.stderr)
            return 1
        Image.open(io.BytesIO(data)).convert("RGB").save(args.png, "PNG")
        print(f"wrote {args.png}")
    else:
        with open(args.out, "wb") as f:
            f.write(data)
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
