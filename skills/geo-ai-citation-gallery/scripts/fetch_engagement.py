#!/usr/bin/env python3
"""
Batch-fetch Douyin engagement (digg / collect / share / follower / duration)
for a gallery package produced by geo-ai-citation-gallery.

Validated 2026-09-19 on 康丽根 Top50: digg 45/50, collect 43/50 via public pages
(Playwright + data-e2e), no login bypass, no invented numbers.

Usage:
  python scripts/fetch_engagement.py --package <分析包根目录>
  python scripts/fetch_engagement.py --package <包> --headed --retry-failed

Reads:  <包>/gallery/data.json  (needs rank, video_id, url)
Writes: <包>/work/engagement.json
        <包>/work/engagement.jsonl
        <包>/work/engagement_progress.txt

Then merge into gallery data.json / index.html (see references/capture-pipeline.md §互动).
"""
from __future__ import annotations

import argparse
import json
import time
import traceback
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError as e:
    raise SystemExit("需要 playwright：pip install playwright && playwright install chromium") from e

EXTRACT_JS = r"""
() => {
  const parse = (s) => {
    if (s == null) return null;
    s = String(s).trim().replace(/,/g, '').replace(/\s+/g, '');
    if (!s) return null;
    // Bare labels with no number → not a count (caller may treat as platform-zero)
    if (/^(赞|收藏|分享|评论|抢首评|喜欢)$/.test(s)) return null;
    const m = s.match(/^([\d.]+)\s*([万wW千kK]?)$/);
    if (!m) {
      const n = parseInt(s, 10);
      return Number.isFinite(n) ? n : null;
    }
    let n = parseFloat(m[1]);
    const u = m[2];
    if (u === '万' || u === 'w' || u === 'W') n *= 10000;
    if (u === '千' || u === 'k' || u === 'K') n *= 1000;
    return Math.round(n);
  };
  const body = (document.body && document.body.innerText) || '';
  const login = /请先登录|登录后观看|验证码|滑动验证|网络连接失败/.test(body) && body.length < 1200;
  const errorPage = !!document.querySelector('[data-e2e="error-page"]');
  const title = document.title || '';
  const genericTitle = /记录美好生活/.test(title) || !title;
  const scope =
    document.querySelector('[data-e2e="note-detail"]') ||
    document.querySelector('[data-e2e="feed-active-video"]') ||
    document.querySelector('[data-e2e="modal-video-container"]') ||
    document;
  const q = (sel) => scope.querySelector(sel);
  const digg = parse((q('[data-e2e="video-player-digg"]') || {}).innerText);
  const collect = parse((q('[data-e2e="video-player-collect"]') || {}).innerText);
  const share = parse((q('[data-e2e="video-player-share"]') || {}).innerText);
  const comment = parse((q('[data-e2e="feed-comment-icon"]') || {}).innerText);
  // Platform-zero hint: icons visible as bare 赞/收藏/分享 with no digits nearby
  const scopeText = (scope.innerText || '').replace(/\s+/g, '');
  const zeroDisplay = /赞|收藏|分享/.test(scopeText) && digg == null && collect == null &&
    !/\d/.test((q('[data-e2e="video-player-digg"]') || {}).innerText || '');
  let follower = null, account = null, publish_date = null;
  const ui = document.querySelector('[data-e2e="user-info"]') ||
             document.querySelector('[data-e2e="feed-video-nickname"]');
  if (ui) {
    const t = ui.innerText || '';
    const fm = t.match(/粉丝\s*([\d.]+)\s*([万wW千kK]?)/);
    if (fm) follower = parse(fm[1] + (fm[2] || ''));
    const lines = t.split('\n').map(x => x.trim()).filter(Boolean);
    for (const line of lines) {
      if (/粉丝|获赞|关注|直播/.test(line)) continue;
      if (line.length >= 1 && line.length <= 40) { account = line.replace(/^@/, ''); break; }
    }
  }
  const nick = document.querySelector('[data-e2e="feed-video-nickname"]');
  if (!account && nick) account = (nick.innerText || '').replace(/^@/, '').trim().slice(0, 40) || null;
  const dm = body.match(/·\s*(\d{1,2}月\d{1,2}日|\d{4}-\d{2}-\d{2})/);
  if (dm) publish_date = dm[1];
  let duration = null;
  const v = document.querySelector('video');
  if (v && isFinite(v.duration) && v.duration > 0 && v.duration < 36000) {
    duration = Math.round(v.duration * 10) / 10;
  }
  const tm = (scope.innerText || body).match(/(\d{1,2}):(\d{2})\s*\/\s*(\d{1,2}):(\d{2})/);
  if (duration == null && tm) {
    duration = parseInt(tm[3], 10) * 60 + parseInt(tm[4], 10);
  }
  let content_type = null;
  if (/图文/.test(scope.innerText || '')) content_type = '图文';
  return {
    digg, collect, share, comment, follower, account, publish_date, duration,
    content_type, title, href: location.href, login, errorPage, genericTitle,
    zeroDisplay, body_len: body.length
  };
}
"""


def strategies(vid: str):
    return [
        ("note", f"https://www.douyin.com/note/{vid}"),
        ("video", f"https://www.douyin.com/video/{vid}"),
        ("modal", f"https://www.douyin.com/jingxuan?modal_id={vid}"),
        ("share", f"https://www.iesdouyin.com/share/video/{vid}"),
    ]


def pick_best(cands: list[dict]) -> dict | None:
    """Prefer note > video > modal > share.
    Allow errorPage marker when digg/collect already present (false positive common).
    """
    order = {"note": 0, "video": 1, "modal": 2, "share": 3}
    scored = []
    for c in cands:
        if c.get("login"):
            continue
        if c.get("digg") is None and c.get("collect") is None:
            continue
        pen = 0
        if c.get("errorPage"):
            pen += 1
        if c.get("genericTitle") and c.get("strategy") != "modal":
            pen += 5
        if c.get("genericTitle") and c.get("strategy") == "modal":
            pen += 2
        scored.append((order.get(c.get("strategy"), 9) + pen, c))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0])
    return scored[0][1]


def fetch_one(page, it: dict, wait_ms: int = 4500) -> dict:
    rank = it["rank"]
    vid = str(it["video_id"])
    cands = []
    for name, url in strategies(vid):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=40000)
            page.wait_for_timeout(wait_ms)
            info = page.evaluate(EXTRACT_JS)
            info["strategy"] = name
            info["page_url"] = page.url
            cands.append(info)
            print(
                f"  {name}: digg={info.get('digg')} collect={info.get('collect')} "
                f"share={info.get('share')} fol={info.get('follower')} dur={info.get('duration')} "
                f"title={str(info.get('title'))[:36]!r} login={info.get('login')} "
                f"err={info.get('errorPage')} zero={info.get('zeroDisplay')}",
                flush=True,
            )
            if (
                name in ("note", "video")
                and info.get("digg") is not None
                and info.get("collect") is not None
                and not info.get("genericTitle")
                and not info.get("login")
            ):
                break
            if info.get("login"):
                break
        except Exception as e:
            print(f"  {name} fail: {e}", flush=True)
            cands.append({"strategy": name, "error": str(e), "digg": None, "collect": None})
    best = pick_best(cands)
    rec = {
        "rank": rank,
        "video_id": vid,
        "url": it.get("url"),
        "status": "missing",
        "source": None,
        "digg_count": None,
        "collect_count": None,
        "share_count": None,
        "comment_count": None,
        "follower_count": None,
        "duration_sec": None,
        "account_name": None,
        "publish_date": None,
        "content_type_hint": None,
        "page_url": None,
        "attempts": [
            {
                k: c.get(k)
                for k in (
                    "strategy",
                    "digg",
                    "collect",
                    "share",
                    "follower",
                    "login",
                    "errorPage",
                    "zeroDisplay",
                    "title",
                    "error",
                )
            }
            for c in cands
        ],
    }
    if best:
        rec.update(
            {
                "status": "ok",
                "source": f"Douyin DOM data-e2e via {best.get('strategy')}",
                "digg_count": best.get("digg"),
                "collect_count": best.get("collect"),
                "share_count": best.get("share"),
                "comment_count": best.get("comment"),
                "follower_count": best.get("follower"),
                "duration_sec": best.get("duration"),
                "account_name": best.get("account"),
                "publish_date": best.get("publish_date"),
                "content_type_hint": best.get("content_type"),
                "page_url": best.get("page_url") or best.get("href"),
            }
        )
        if rec["digg_count"] is None or rec["collect_count"] is None:
            rec["status"] = "partial"
    else:
        # Platform-zero: visible 赞|收藏|分享 icons with no digits
        zero = next((c for c in cands if c.get("zeroDisplay") and not c.get("login")), None)
        if zero:
            rec.update(
                {
                    "status": "ok",
                    "source": "Douyin DOM; bare 赞｜收藏｜分享（无数字=平台零互动展示）",
                    "digg_count": 0,
                    "collect_count": 0,
                    "share_count": 0,
                    "comment_count": 0,
                    "duration_sec": zero.get("duration"),
                    "follower_count": zero.get("follower"),
                    "page_url": zero.get("page_url") or zero.get("href"),
                }
            )
        elif any(c.get("login") for c in cands):
            rec["status"] = "login_wall"
            rec["source"] = "login wall — stopped; keep 暂未抓取到"
        else:
            rec["status"] = "missing"
            rec["source"] = "no digg/collect in DOM — keep 暂未抓取到"
        # Still keep duration if any attempt had it
        if rec.get("duration_sec") is None:
            for c in cands:
                if c.get("duration") is not None:
                    rec["duration_sec"] = c["duration"]
                    break
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch Douyin digg/collect/share for gallery TopN")
    ap.add_argument("--package", required=True, help="分析包根目录（含 gallery/data.json）")
    ap.add_argument("--headed", action="store_true", help="有头浏览器（遇墙更易观察）")
    ap.add_argument("--retry-failed", action="store_true", help="只重试 digg 仍为 null 的条目")
    ap.add_argument("--wait-ms", type=int, default=4500, help="每页等待毫秒")
    ap.add_argument("--chrome", default="/usr/bin/google-chrome", help="Chrome 可执行路径")
    args = ap.parse_args()

    pkg = Path(args.package).resolve()
    gallery = pkg / "gallery"
    work = pkg / "work"
    work.mkdir(parents=True, exist_ok=True)
    (work / "capture_logs").mkdir(parents=True, exist_ok=True)
    data_path = gallery / "data.json"
    if not data_path.exists():
        raise SystemExit(f"缺少 {data_path}")
    data = json.loads(data_path.read_text(encoding="utf-8"))
    items = data["data"] if isinstance(data, dict) else data

    out = work / "engagement.json"
    out_jsonl = work / "engagement.jsonl"
    progress = work / "engagement_progress.txt"

    existing: dict[int, dict] = {}
    if out.exists():
        try:
            for r in json.loads(out.read_text(encoding="utf-8")):
                if r.get("digg_count") is not None and not args.retry_failed:
                    existing[r["rank"]] = r
                elif args.retry_failed and r.get("digg_count") is not None:
                    existing[r["rank"]] = r
        except Exception:
            pass

    if args.retry_failed:
        todo = [it for it in items if it["rank"] not in existing]
    else:
        todo = items
        # keep existing as results base
    print(f"resume keep digg: {sorted(existing)}; todo={len(todo) if args.retry_failed else len(items)-len(existing)}", flush=True)

    results_by: dict[int, dict] = dict(existing)

    with sync_playwright() as p:
        launch_kwargs = {
            "headless": not args.headed,
            "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-dev-shm-usage"],
        }
        chrome = Path(args.chrome)
        if chrome.exists():
            launch_kwargs["executable_path"] = str(chrome)
        browser = p.chromium.launch(**launch_kwargs)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
            extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9"},
        )
        page = context.new_page()
        for it in items:
            rank = it["rank"]
            if rank in existing and not (args.retry_failed and existing[rank].get("digg_count") is None):
                if rank in existing and existing[rank].get("digg_count") is not None:
                    print(f"\n=== rank {rank:02d} SKIP existing ===", flush=True)
                    results_by[rank] = existing[rank]
                    continue
            if args.retry_failed and rank in existing and existing[rank].get("digg_count") is not None:
                continue
            print(f"\n=== rank {rank:02d} vid={it['video_id']} ===", flush=True)
            try:
                rec = fetch_one(page, it, wait_ms=args.wait_ms)
            except Exception:
                traceback.print_exc()
                rec = {
                    "rank": rank,
                    "video_id": str(it["video_id"]),
                    "status": "error",
                    "error": traceback.format_exc()[-500],
                    "digg_count": None,
                    "collect_count": None,
                    "share_count": None,
                    "follower_count": None,
                    "duration_sec": None,
                }
            results_by[rank] = rec
            results_sorted = [results_by[r] for r in sorted(results_by)]
            out.write_text(json.dumps(results_sorted, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            out_jsonl.write_text(
                "\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in results_sorted) + "\n",
                encoding="utf-8",
            )
            with open(progress, "a", encoding="utf-8") as f:
                f.write(
                    f"{rank} {rec.get('status')} digg={rec.get('digg_count')} "
                    f"collect={rec.get('collect_count')} share={rec.get('share_count')} src={rec.get('source')}\n"
                )
            time.sleep(0.8)
        browser.close()

    results = [results_by[r] for r in sorted(results_by)]
    ok = [r for r in results if r.get("digg_count") is not None]
    fail = [r["rank"] for r in results if r.get("digg_count") is None]
    print("\n==== SUMMARY ====", flush=True)
    print("digg", len(ok), "/", len(results), flush=True)
    print("collect", sum(1 for r in results if r.get("collect_count") is not None), flush=True)
    print("share", sum(1 for r in results if r.get("share_count") is not None), flush=True)
    print("follower", sum(1 for r in results if r.get("follower_count") is not None), flush=True)
    print("duration", sum(1 for r in results if r.get("duration_sec") is not None), flush=True)
    print("fail digg ranks", fail, flush=True)
    print(f"wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
