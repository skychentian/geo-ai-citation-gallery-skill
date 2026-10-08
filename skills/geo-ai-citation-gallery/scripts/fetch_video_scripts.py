#!/usr/bin/env python3
"""
高引用视频文案拉取的调度与状态回写。

本脚本不直接访问网络——文案由 Agent 用外部通道拉取（抖音用 web.fetch 快速路径，
快手/B 站用 doubao-video-extract）。脚本负责：出待拉取清单、初始化文案模板、
扫描落盘文件并回写 top.json 状态。

用法：
  # 1) 出清单 + 初始化每个视频的文案模板（带头字段）
  python fetch_video_scripts.py --package <包路径> --init

  # 2) Agent 逐个用通道拉取，把文案填入 文案/<rank>_<slug>.md（保留头字段）

  # 3) 扫描文案文件，回写 top.json 状态
  python fetch_video_scripts.py --package <包路径> --verify

  # 只重试未成功 / 缺文件的
  python fetch_video_scripts.py --package <包路径> --verify --retry-failed
"""
import argparse
import json
import os
import re
from datetime import datetime

HEADER_FIELDS = ["来源", "平台", "账号", "发布时间", "时长", "播放量", "总字数", "拉取状态", "文案类型"]

TEMPLATE = """# {title}

> 来源：{url}
> 平台：{site}
> 账号：
> 发布时间：
> 时长：
> 播放量：
> 文案类型：未知
> 总字数：
> 拉取状态：{status}

---

（待填入拉取到的视频文案/逐字稿。抖音用 web.fetch 快速路径；快手/B 站用 doubao-video-extract。）
"""

STATUS_LABEL = {
    "ok": "已拉取",
    "short": "已拉取·短文案",
    "pending": "待拉取",
    "dead": "未拉取到·失效",
    "blocked": "未拉取到·受限",
    "bgm": "纯BGM无口播",
    "fail": "未拉取到",
}


def _slug(title):
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "", title or "")
    return s[:20] if s else "video"


def _needs_retry(it):
    return it.get("fetch_status") not in {"ok", "bgm"}


def write_template(path, it):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(TEMPLATE.format(
                title=it.get("title") or "（无标题）",
                url=it.get("url") or "",
                site=it.get("site") or it.get("domain") or "",
                status=STATUS_LABEL["pending"],
            ))
        return True
    return False


def parse_meta(text):
    """解析文案头字段与正文。返回 (meta dict, body)。"""
    meta = {}
    for field in HEADER_FIELDS:
        m = re.search(rf"^> {re.escape(field)}：(.+)$", text, re.M)
        meta[field] = m.group(1).strip() if m else ""
    body = ""
    m = re.search(r"^---\s*\n(.*)$", text, re.S | re.M)
    if m:
        body = m.group(1)
    body = body.strip()
    return meta, body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True, help="分析包根目录")
    ap.add_argument("--init", action="store_true", help="出清单并初始化文案模板")
    ap.add_argument("--verify", action="store_true", help="扫描文案文件并回写 top.json 状态")
    ap.add_argument("--retry-failed", action="store_true", help="verify 时只处理未成功的")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    pkg = os.path.abspath(args.package)
    top_path = os.path.join(pkg, "_机器可读", "top.json")
    if not os.path.exists(top_path):
        raise SystemExit(f"缺少 {top_path}，请先跑 extract_top_videos.py")

    with open(top_path, encoding="utf-8") as f:
        doc = json.load(f)
    videos = doc.get("videos") or []
    if not videos:
        raise SystemExit("top.json 中 videos 为空")

    if args.limit:
        videos = videos[: args.limit]

    # ---- 初始化模板 ----
    if args.init:
        print("# 待拉取清单（请逐个用通道拉取文案后回填）\n")
        print("| 序号 | 标题 | 平台 | 链接 | 文案文件 |")
        print("|---|---|---|---|---|")
        for it in videos:
            rel = it.get("script_path") or ""
            path = os.path.join(pkg, rel) if rel else ""
            if path and not os.path.exists(path):
                write_template(path, it)
            print(f"| {it.get('rank')} | {it.get('title')} | {it.get('site')} | {it.get('url')} | {rel} |")
        print("\n完成：已初始化文案模板。拉取完成后跑 --verify 回写状态。")
        return

    # ---- 扫描回写 ----
    if args.verify:
        if args.retry_failed:
            videos = [v for v in videos if _needs_retry(v) or not v.get("script_path")
                      or not os.path.isfile(os.path.join(pkg, v["script_path"]))]
        records = []
        for it in videos:
            rel = it.get("script_path") or ""
            path = os.path.join(pkg, rel) if rel else ""
            rank = it.get("rank")
            title = it.get("title") or ""
            if path and os.path.isfile(path):
                with open(path, encoding="utf-8") as f:
                    meta, body = parse_meta(f.read())
            else:
                meta, body = {}, ""
            status_raw = meta.get("拉取状态", "")
            word_count = len(re.sub(r"\s", "", body))
            placeholder = body.startswith("（待填入") or body.startswith("（未能获取")
            if not path or not os.path.isfile(path):
                status, reason = "fail", "缺文件"
            elif placeholder or status_raw.startswith("待"):
                status, reason = "pending", "待拉取或核验"
            elif status_raw.startswith("纯BGM"):
                status, reason = "bgm", "纯BGM无口播"
            elif "受限" in status_raw:
                status, reason = "blocked", status_raw
            elif "失效" in status_raw:
                status, reason = "dead", status_raw
            elif status_raw.startswith("未拉取") or not body:
                status, reason = "fail", status_raw or "缺正文"
            elif status_raw.startswith("已拉取"):
                status, reason = "ok", ""
            else:
                status, reason = "pending", "拉取状态待核验"
            # 正文长度不能证明证据类型；未知正文保留，但不作为口播依据。
            kind = meta.get("文案类型") or it.get("text_type") or "未知"
            for target, source in (("account", "账号"), ("publish_date", "发布时间"),
                                   ("duration", "时长"), ("play_count", "播放量")):
                if meta.get(source):
                    it[target] = meta[source]
            source = meta.get("来源") or it.get("url")
            usable = status == "ok" and bool(source) and bool(body) and not placeholder
            evidence = {
                "title": bool(it.get("title") and it.get("url")),
                "caption": usable and kind in {"发布文案", "视频描述", "caption"},
                "transcript": usable and kind in {"口播文案", "口播逐字稿", "字幕转写", "transcript"},
                "visual": bool(it.get("visual_evidence_source") and it.get("visual_verified") is True),
                "engagement": bool(it.get("engagement_source") and it.get("engagement_verified") is True),
            }
            it.update({"fetch_status": status, "fail_reason": reason,
                       "text_type": kind, "word_count": word_count,
                       "eligibility": evidence,
                       "analysis_eligible": evidence["caption"] or evidence["transcript"]})
            records.append((rank, title, status, word_count, rel))

        with open(top_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)

        rec_path = os.path.join(pkg, "_过程", "拉取记录.md")
        os.makedirs(os.path.dirname(rec_path), exist_ok=True)
        lines = [
            f"# 拉取记录（{datetime.now().strftime('%Y-%m-%d %H:%M')}）\n",
            "> 校验不修改文案、不创建失败占位；按 eligibility 分维度使用证据，缺失与待处理状态保留在清单。\n",
            "| 序号 | 标题 | 状态 | 字数 | 文件 |",
            "|---|---|---|---|---|",
        ]
        for rank, title, status, wc, rel in records:
            lines.append(f"| {rank} | {title} | {status} | {wc} | {rel} |")
        with open(rec_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        ok = sum(1 for r in records if r[2] == "ok")
        short = sum(1 for r in records if r[2] == "short")
        bgm = sum(1 for r in records if r[2] == "bgm")
        fail = sum(1 for r in records if r[2] == "fail")
        print(
            f"\n完成：共 {len(records)} 条 ｜ 已获取正文 {ok} · 短文案 {short} · 纯BGM {bgm} · 失败 {fail}"
        )
        print(f"过程记录: {rec_path}")
        print("下一步: 按 analysis-phase.md 分维度分析证据，按需分工")
        return

    ap.print_help()


if __name__ == "__main__":
    main()
