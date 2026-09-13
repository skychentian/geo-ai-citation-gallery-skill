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

HEADER_FIELDS = ["来源", "平台", "账号", "发布时间", "时长", "播放量", "总字数", "拉取状态"]

TEMPLATE = """# {title}

> 来源：{url}
> 平台：{site}
> 账号：
> 发布时间：
> 时长：
> 播放量：
> 总字数：
> 拉取状态：{status}

---

（待填入拉取到的视频文案/逐字稿。抖音用 web.fetch 快速路径；快手/B 站用 doubao-video-extract。）
"""

PLACEHOLDER = """# 【未拉取到】{title}

> 来源：{url}
> 平台：{site}
> 账号：
> 发布时间：
> 时长：
> 播放量：
> 总字数：0
> 拉取状态：{status}

---

（未能获取可用文案。原因：{reason}）
"""

STATUS_LABEL = {
    "ok": "已拉取",
    "short": "未拉取到·过短",
    "dead": "未拉取到·失效",
    "blocked": "未拉取到·受限",
    "bgm": "纯BGM无口播",
    "fail": "未拉取到",
}


def _slug(title):
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "", title or "")
    return s[:20] if s else "video"


def _needs_retry(it):
    if it.get("analysis_eligible") is True:
        return False
    return True


def write_template(path, it):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if not os.path.exists(path) or os.path.getsize(path) < 40:
        with open(path, "w", encoding="utf-8") as f:
            f.write(TEMPLATE.format(
                title=it.get("title") or "（无标题）",
                url=it.get("url") or "",
                site=it.get("site") or it.get("domain") or "",
                status=STATUS_LABEL["ok"],
            ))
        return True
    return False


def write_placeholder(path, it, status, reason):
    title = (it.get("title") or "（无标题）").strip()
    label = STATUS_LABEL.get(status, "未拉取到")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(PLACEHOLDER.format(
            title=title,
            url=it.get("url") or "",
            site=it.get("site") or it.get("domain") or "",
            status=label,
            reason=reason,
        ))


def parse_meta(text):
    """解析文案头字段与正文。返回 (meta dict, body)。"""
    meta = {}
    for field in HEADER_FIELDS:
        m = re.search(rf"^> {re.escape(field)}：(.+)$", text, re.M)
        meta[field] = m.group(1).strip() if m else ""
    body = text
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
            videos = [v for v in videos if _needs_retry(v)]
        records = []
        for it in videos:
            rel = it.get("script_path") or ""
            path = os.path.join(pkg, rel) if rel else ""
            rank = it.get("rank")
            title = it.get("title") or ""
            if not path or not os.path.isfile(path):
                write_placeholder(path, it, "fail", "缺文件")
                records.append((rank, title, "fail", 0, rel))
                continue
            with open(path, encoding="utf-8") as f:
                text = f.read()
            meta, body = parse_meta(text)
            status_raw = meta.get("拉取状态", "")
            word_count = len(re.sub(r"\s", "", body))
            # 判定：先认占位/占位标记，再认状态，最后认字数
            is_placeholder = "待填入" in body or "未能获取" in body or "待填入拉取" in text
            if title.startswith("【未拉取到】") or text.startswith("# 【未拉取到】") or is_placeholder:
                status = "fail"
                reason = status_raw or "未拉取"
                eligible = False
            elif status_raw.startswith("纯BGM"):
                status = "bgm"
                reason = "纯BGM无口播"
                eligible = False
            elif word_count < 50:
                status = "short"
                reason = "过短"
                eligible = False
            else:
                status = "ok"
                reason = "ok"
                eligible = True
            if status != "ok":
                write_placeholder(path, it, status, reason)
                word_count = 0
            fields = {
                "fetch_status": status,
                "fail_reason": reason,
                "account": meta.get("账号", ""),
                "publish_date": meta.get("发布时间", ""),
                "duration": meta.get("时长", ""),
                "play_count": meta.get("播放量", ""),
                "word_count": word_count if status == "ok" else 0,
                "analysis_eligible": eligible,
            }
            it.update(fields)
            records.append((rank, title, status, word_count, rel))

        with open(top_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)

        rec_path = os.path.join(pkg, "_过程", "拉取记录.md")
        os.makedirs(os.path.dirname(rec_path), exist_ok=True)
        lines = [
            f"# 拉取记录（{datetime.now().strftime('%Y-%m-%d %H:%M')}）\n",
            "> 每个 Top 序号都有对应 md（失败为【未拉取到】占位）。偏好分析只读 analysis_eligible=true。\n",
            "| 序号 | 标题 | 状态 | 字数 | 文件 |",
            "|---|---|---|---|---|",
        ]
        for rank, title, status, wc, rel in records:
            lines.append(f"| {rank:02d} | {title} | {status} | {wc} | {rel} |")
        with open(rec_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        ok = sum(1 for r in records if r[2] == "ok")
        short = sum(1 for r in records if r[2] == "short")
        bgm = sum(1 for r in records if r[2] == "bgm")
        fail = sum(1 for r in records if r[2] == "fail")
        print(
            f"\n完成：共 {len(records)} 条 ｜ 可分析 {ok} · 过短 {short} · 纯BGM {bgm} · 失败 {fail}"
        )
        print(f"过程记录: {rec_path}")
        print("下一步: 按 analysis-phase.md 派子 Agent 写偏好")
        return

    ap.print_help()


if __name__ == "__main__":
    main()
