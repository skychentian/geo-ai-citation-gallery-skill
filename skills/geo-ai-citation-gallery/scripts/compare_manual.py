#!/usr/bin/env python3
"""对比 douyin_fetch.py 输出与分析包里的手动结果（只读两边）。

用法（在技能根目录，即本文件所在 scripts/ 的上一级）:
  python3 scripts/compare_manual.py --package <分析包> --out <douyin_fetch 输出目录> [--ranks 1-10]

写出 <out>/compare.json 和 <out>/compare.md：每个字段两边是否有值、是否一致。
依赖：Python 标准库（argparse、json、re、difflib），无第三方包。
"""
import argparse, json, re, difflib
from pathlib import Path

MISSING = (None, "", "暂未抓取到", [], "null")

def miss(v): return v in MISSING or (isinstance(v, float) and v != v)
def norm(s): return re.sub(r"[\s\W_]+", "", str(s or ""))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--ranks", default="")
    a = ap.parse_args()
    pkg, out = Path(a.package), Path(a.out)
    man = {it["rank"]: it for it in json.loads((pkg/"gallery/data.json").read_text())["data"]}
    eng = {r["rank"]: r for r in json.loads((pkg/"work/engagement.json").read_text())}
    tr = {}
    for l in (pkg/"work/transcripts.jsonl").read_text().splitlines():
        if l.strip(): r = json.loads(l); tr[r["rank"]] = r
    imgs_dir = pkg/"gallery/images"
    scr = {it["rank"]: it for it in json.loads((out/"items.json").read_text())}
    ranks = sorted(scr)
    if a.ranks:
        lo, _, hi = a.ranks.partition("-"); ranks = [r for r in ranks if int(lo) <= r <= int(hi or lo)]
    fields = ["title", "desc", "hashtags", "account", "follower_count", "digg_count", "collect_count",
              "share_count", "comment_count", "content_type", "duration_sec", "publish_date",
              "images", "cover", "video_file", "frames", "transcript"]
    cov = {f: {"script": 0, "manual": 0, "both": 0, "consistent": 0} for f in fields}
    rows = []
    for r in ranks:
        s, m, e, t = scr[r], man.get(r, {}), eng.get(r, {}), tr.get(r, {})
        mfiles = sorted(p.name for p in imgs_dir.glob(f"{r:02d}_*")) if imgs_dir.exists() else []
        mv = {
            "title": m.get("title"), "desc": m.get("original_desc"), "hashtags": m.get("hashtags"),
            "account": m.get("account_name") or m.get("account"),
            "follower_count": m.get("follower_count"), "digg_count": m.get("digg_count"),
            "collect_count": m.get("collect_count"), "share_count": m.get("share_count"),
            "comment_count": m.get("comment_count"), "content_type": m.get("content_type"),
            "duration_sec": m.get("duration_sec"), "publish_date": m.get("publish_date"),
            "images": mfiles if m.get("content_type") == "图文" else None,
            "cover": next((f for f in mfiles if "cover" in f), None),
            "video_file": None, "frames": None,
            "transcript": t.get("text") if t.get("status") == "ok" else None,
        }
        sv = {
            "title": s.get("title"), "desc": s.get("original_desc"), "hashtags": s.get("hashtags"),
            "account": s.get("account_name"), "follower_count": s.get("follower_count"),
            "digg_count": s.get("digg_count"), "collect_count": s.get("collect_count"),
            "share_count": s.get("share_count"), "comment_count": s.get("comment_count"),
            "content_type": s.get("content_type"), "duration_sec": s.get("duration_sec"),
            "publish_date": s.get("publish_date"), "images": s.get("images") or None,
            "cover": s.get("cover"), "video_file": s.get("video_file"), "frames": s.get("frames") or None,
            "transcript": s.get("transcript"),
        }
        row = {"rank": r, "video_id": s.get("video_id"), "script_type": s.get("content_type"),
               "manual_type": m.get("content_type"), "fields": {}}
        for f in fields:
            a_, b_ = sv[f], mv[f]
            has_s, has_m = not miss(a_), not miss(b_)
            cov[f]["script"] += has_s; cov[f]["manual"] += has_m
            note, ok = "", None
            if has_s and has_m:
                cov[f]["both"] += 1
                if f in ("digg_count", "collect_count", "share_count", "comment_count", "follower_count"):
                    d = a_ - b_; pct = (d / b_ * 100) if b_ else None
                    # 手动值来自 2026-09-19 DOM 显示（万/千 取整），允许增长
                    approx = b_ >= 10000 and b_ % 1000 == 0
                    ok = (d >= 0 and (pct is None or pct <= 30)) or (approx and abs(d) <= b_ * 0.06)
                    note = f"脚本 {a_} vs 手动 {b_}，差 {d:+d}" + (f"（{pct:+.1f}%）" if pct is not None else "") + ("；手动为万级近似值" if approx else "")
                elif f == "duration_sec":
                    d = float(a_) - float(b_); ok = abs(d) <= max(1.0, 0.03 * float(b_))
                    note = f"脚本 {a_} vs 手动 {b_}，差 {d:+.1f}s"
                elif f == "content_type":
                    ok = (a_ == b_) or (a_ == "视频" and b_ == "口播"); note = f"脚本 {a_} / 手动 {b_}"
                elif f in ("title", "desc"):
                    nb = norm(str(b_).rstrip("…").rstrip("...")); na = norm(a_)
                    full = norm(s.get("original_desc"))
                    ok = bool(nb) and (nb in full or full.startswith(nb[:30]) or na.startswith(nb[:20]))
                    note = f"手动{len(str(b_))}字 / 脚本{len(str(a_))}字；手动是否为脚本完整文案的前缀/子串: {ok}"
                elif f == "hashtags":
                    ms = {norm(x).lower() for x in b_}; ss = {norm(x).lower() for x in a_}
                    ok = ms <= ss; note = f"手动{len(b_)}个 / 脚本{len(a_)}个；手动缺: {sorted(ss-ms)}；脚本缺: {sorted(ms-ss)}"
                elif f == "publish_date":
                    mm = re.match(r"(?:(\d{4})-)?(\d{1,2})[-月](\d{1,2})", str(b_))
                    sd = str(a_)
                    ok = bool(mm) and int(sd[5:7]) == int(mm.group(2)) and int(sd[8:10]) == int(mm.group(3))
                    note = f"脚本 {a_}（createTime）/ 手动 {b_}（DOM 文本正则）"
                elif f == "account":
                    ok = norm(a_) == norm(b_); note = f"脚本 {a_} / 手动 {b_}"
                elif f == "images":
                    ok = len(a_) >= len(b_); note = f"脚本 {len(a_)} 张 / 手动 {len(b_)} 张"
                elif f == "transcript":
                    na, nb = norm(a_), norm(b_)
                    ratio = difflib.SequenceMatcher(None, na[:3000], nb[:3000], autojunk=False).ratio()
                    ok = ratio >= 0.6; note = f"字数 脚本{len(na)} / 手动{len(nb)}；前3000字相似度 {ratio:.2f}"
                else:
                    ok = True; note = "两边都有"
                cov[f]["consistent"] += bool(ok)
            elif has_s: note = "仅脚本有"
            elif has_m: note = "仅手动有"
            else: note = "两边都无"
            row["fields"][f] = {"script": has_s, "manual": has_m, "consistent": ok, "note": note}
        rows.append(row)
    n = len(rows)
    res = {"n": n, "ranks": ranks, "coverage": cov, "rows": rows}
    (out/"compare.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    L = [f"# 脚本 vs 手动 对比（{n} 条，rank {ranks[0]}–{ranks[-1]}）", "",
         "| 字段 | 脚本有值 | 手动有值 | 两边都有 | 一致 |", "|---|---|---|---|---|"]
    for f in fields:
        c = cov[f]; L.append(f"| {f} | {c['script']}/{n} | {c['manual']}/{n} | {c['both']} | {c['consistent']}/{c['both']} |")
    L += ["", "## 逐条差异（只列两边都有但不一致、或单边有）", ""]
    for row in rows:
        items = [f"{f}: {v['note']}" for f, v in row["fields"].items()
                 if v["consistent"] is False or (v["script"] != v["manual"])]
        L.append(f"- rank {row['rank']}（脚本:{row['script_type']} / 手动:{row['manual_type']}）")
        for x in items: L.append(f"  - {x}")
    L += ["", "## 数值字段明细", ""]
    for row in rows:
        nums = [f"{f}: {row['fields'][f]['note']}" for f in ("digg_count","collect_count","share_count","comment_count","follower_count","duration_sec") if row['fields'][f]['script'] and row['fields'][f]['manual']]
        L.append(f"- rank {row['rank']}: " + "；".join(nums))
    (out/"compare.md").write_text("\n".join(L) + "\n")
    print("\n".join(L[:len(fields)+4]))

if __name__ == "__main__":
    main()
