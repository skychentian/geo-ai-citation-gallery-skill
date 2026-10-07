#!/usr/bin/env python3
"""
GEO 数据包高引用视频信源提取 + 交付索引生成（默认抖音）。

交付层（包根目录）：
  视频索引.md
  _机器可读/top.json

过程层（包内 _过程/，默认保留证据）：
  各类 top JSON、含并列、分平台明细等

用法：
  python extract_top_videos.py \\
      --xlsx <数据包>/diagnosis-answers.xlsx \\
      --brand "天猫养车,天猫养车连锁" --top 10 --scope-platform douyin \\
      --stages 探索 --package-date 20260830 --out <包路径>/

  # 或读 analysis-v1 包的 tables/source-urls.csv
  python extract_top_videos.py --csv <数据包>/tables/source-urls.csv ...

  # 自定义一批问题（一行一题）
  python extract_top_videos.py ... --questions-file questions.txt --out <包路径>/
"""
import argparse
import json
import os
import re
from collections import Counter, defaultdict
from urllib.parse import urlsplit, parse_qsl, urlencode

try:
    import openpyxl
except ImportError:
    openpyxl = None

# 视频平台域名
DOUYIN_DOMAINS = {"iesdouyin.com", "douyin.com"}
VIDEO_DOMAINS = DOUYIN_DOMAINS | {
    "kuaishou.com", "bilibili.com", "ixigua.com", "haokan.baidu.com",
    "weibo.com", "weibo.cn",
}

STAGE_LABELS = {
    "exploration": "探索",
    "evaluation": "评估",
    "action": "行动",
}
STAGE_ALIASES = {
    "exploration": "exploration", "explore": "exploration", "探索": "exploration",
    "evaluation": "evaluation", "eval": "evaluation", "评估": "evaluation",
    "action": "action", "行动": "action",
}

TRACKING_PARAMS_PREFIX = ("utm_", "share_")
TRACKING_PARAMS = {"spm", "from", "wfr", "for", "refer", "ref", "traceid", "track_id", "sourceid"}


def sheet_rows(ws):
    rows = ws.iter_rows(values_only=True)
    header = next(rows)
    return header, [dict(zip(header, r)) for r in rows]


def parse_brands(brand_arg):
    return [b.strip() for b in (brand_arg or "").split(",") if b.strip()]


def parse_stages(stages_arg):
    if not stages_arg or not str(stages_arg).strip():
        return []
    out = []
    for part in str(stages_arg).split(","):
        key = part.strip()
        if not key:
            continue
        norm = STAGE_ALIASES.get(key) or STAGE_ALIASES.get(key.lower())
        if not norm:
            raise SystemExit(f"未知阶段「{key}」。可用：探索/评估/行动 或 exploration/evaluation/action")
        if norm not in out:
            out.append(norm)
    return out


def load_questions_file(path):
    questions = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            questions.append(s)
    if not questions:
        raise SystemExit(f"问题清单为空: {path}")
    return questions


def scope_label_from_args(stages, has_questions_file):
    if has_questions_file:
        return "自定义"
    if len(stages) == 1:
        return STAGE_LABELS[stages[0]]
    if not stages:
        return "全阶段"
    return "+".join(STAGE_LABELS[s] for s in stages)


def is_brand_question(question, brands):
    if not question:
        return False
    return any(b in question for b in brands)


def _host(url):
    try:
        return (urlsplit(str(url).strip()).hostname or "").lower()
    except Exception:
        return ""


def _host_in(host, domain_set):
    if not host:
        return False
    return any(host == d or host.endswith("." + d) for d in domain_set)


def normalize_url(url):
    if not url:
        return ""
    host = _host(url)
    video_id = extract_video_id(url)
    if video_id and _host_in(host, DOUYIN_DOMAINS):
        return f"douyin:video:{video_id}"
    if video_id.startswith("BV") and _host_in(host, {"bilibili.com"}):
        return f"bilibili:video:{video_id}"
    try:
        parts = urlsplit(str(url).strip())
    except Exception:
        return str(url).strip()
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/+$", "", parts.path or "")
    kept = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS
        and not k.lower().startswith(TRACKING_PARAMS_PREFIX)
    ]
    query = urlencode(sorted(kept))
    return f"{host}{path}" + (f"?{query}" if query else "")


def is_video(url, domain):
    if domain and _host_in(str(domain).lower().lstrip("."), VIDEO_DOMAINS):
        return True
    return _host_in(_host(url), VIDEO_DOMAINS)


def is_douyin(url, domain):
    if domain and _host_in(str(domain).lower().lstrip("."), DOUYIN_DOMAINS):
        return True
    return _host_in(_host(url), DOUYIN_DOMAINS)


def extract_video_id(url):
    """从 iesdouyin/douyin 链接提取视频 ID；其它平台取 URL 片段尾。"""
    u = str(url or "")
    m = re.search(r"/(?:video|note)/(\d+)", u)
    if m:
        return m.group(1)
    m = re.search(r"[?&](?:modal_id|model_id|video_id)=(\d+)", u)
    if m:
        return m.group(1)
    m = re.search(r"/share/video/(\d+)", u)
    if m:
        return m.group(1)
    # bilibili BV 号
    m = re.search(r"(BV[0-9A-Za-z]{10})", u)
    if m:
        return m.group(1)
    return ""


def _new_entry():
    return {
        "title": "", "url": "", "domain": "", "site": "",
        "video_id": "", "citations": Counter(), "platforms": set(),
        "answer_keys": set(), "occurrence_keys": set(), "missing_answer_id": False,
        "source_rows": 0, "question_platforms": defaultdict(set),
    }


def _token(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _occurrence_key(r, platform, question):
    """缺 answer_id 时按回答行去重。无 round/response_index 则退化为 (平台, 问题)。"""
    rnd = _token(r.get("round"))
    if rnd is None:
        rnd = _token(r.get("round_index"))
    resp = _token(r.get("response_index"))
    if rnd is None and resp is None:
        return (platform, question)
    return ("row", platform, question, rnd, resp)


def _fill_entry(ent, r, url):
    ent["url"] = r.get("url") or url
    ent["title"] = r.get("title") or ent["title"]
    ent["domain"] = r.get("domain") or ent["domain"]
    ent["site"] = r.get("site") or ent["site"]
    if not ent["video_id"]:
        ent["video_id"] = extract_video_id(ent["url"])
    q = r.get("question") or ""
    p = r.get("platform_name") or ""
    ent["source_rows"] += 1
    answer_id = r.get("answer_id")
    if answer_id is None or not str(answer_id).strip():
        ent["missing_answer_id"] = True
        ent["occurrence_keys"].add(_occurrence_key(r, p, q))
    else:
        ent["answer_keys"].add((p, str(answer_id).strip()))
    if q:
        ent["citations"][q] += 1
        if p:
            ent["question_platforms"][q].add(p)
    if p:
        ent["platforms"].add(p)


def _to_item(ent, platform=None):
    item = {
        "title": ent["title"],
        "url": ent["url"],
        "domain": ent["domain"],
        "site": ent["site"],
        "video_id": ent["video_id"],
        "citation_count": len(ent["answer_keys"]) + len(ent["occurrence_keys"]),
        "question_count": len(ent["citations"]),
        "total_pickups": ent["source_rows"],
        "citation_count_status": "link_occurrence" if ent["missing_answer_id"] else "verified",
        "answer_keys": [list(k) for k in sorted(ent["answer_keys"])],
        "question_platforms": {q: sorted(p) for q, p in ent["question_platforms"].items()},
        "questions": sorted(ent["citations"]),
        "question_pickups": dict(sorted(ent["citations"].items())),
    }
    if platform is not None:
        item["platform"] = platform
    else:
        item["platforms"] = sorted(ent["platforms"])
    return item


def _sorted_items(items):
    metric = "citation_count" if all(x["citation_count"] is not None for x in items) else "question_count"
    for item in items:
        item["ranking_metric"] = metric
        item["ranking_count"] = item[metric]
    if metric == "citation_count" and any(x.get("citation_count_status") == "link_occurrence" for x in items):
        items.sort(key=lambda x: (-x["citation_count"], -x["question_count"], x["url"]))
    else:
        items.sort(key=lambda x: (-x["ranking_count"], x["url"]))
    return items


def aggregate(records):
    agg = defaultdict(_new_entry)
    for r in records:
        url = r.get("url")
        if not url:
            continue
        _fill_entry(agg[normalize_url(url)], r, url)
    return _sorted_items([_to_item(ent) for ent in agg.values()])


def to_json(list_):
    return [{"rank": i + 1, **x} for i, x in enumerate(list_)]


def _split_ties(list_, top):
    top_items = list_[: top]
    if top <= len(list_) and top_items:
        cutoff = top_items[-1]["ranking_count"]
        top_with_ties = [x for x in list_ if x["ranking_count"] >= cutoff]
    else:
        top_with_ties = list_
    return top_items, top_with_ties


def _slug(title):
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "", title or "")
    return s[:20] if s else "video"


def _script_relpath(rank, title):
    return f"文案/{rank:02d}_{_slug(title)}.md"


def write_process_json(path, items):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(to_json(items), f, ensure_ascii=False, indent=2)


def write_top_pair(list_, label, process_dir, top):
    top_items, top_with_ties = _split_ties(list_, top)
    prefix = f"非品牌高引用视频{label}" if label else "非品牌高引用视频"
    write_process_json(os.path.join(process_dir, f"{prefix}top{top}.json"), top_items)
    write_process_json(os.path.join(process_dir, f"{prefix}top{top}含并列.json"), top_with_ties)
    name = label or "全部视频"
    low = top_items[-1]["ranking_count"] if top_items else 0
    metric = top_items[0]["ranking_metric"] if top_items else "question_count"
    print(f"[{name}] 总数 {len(list_)} ｜ Top{top}: {len(top_items)} 条, 排序 {metric}, 最低 {low} ｜ 含并列 {len(top_with_ties)} 条 → _过程/")
    return top_items, top_with_ties


def _index_basis(video_top):
    tail = "覆盖问题数按题干去重；信源行数含重复，不用于引用率。"
    if any(x.get("citation_count_status") == "link_occurrence" for x in video_top):
        return (
            "排序依据：引用次数（链接出现口径：数据包缺少回答标识，按同一视频在不同回答行中的出现次数计，"
            "同一平台同一问题同一回答行只计 1 次；并列按覆盖问题数）。" + tail
        )
    metric = video_top[0]["ranking_metric"] if video_top else "question_count"
    if metric == "citation_count":
        return "排序依据：引用回答数。引用回答数按平台与回答标识去重；" + tail
    return "排序依据：覆盖问题数（缺少完整回答标识，不能按引用次数排序）。引用回答数按平台与回答标识去重；" + tail


def _rate_clause(total_answers):
    if total_answers is None:
        return "未提供同范围全部回答，引用率不计算。"
    return f"引用率 = 引用次数 ÷ 同范围回答总数 {total_answers}（来自 answers 表，同品牌剔除/阶段/问题清单筛选）。"


def build_index(video_top, args, idx_path, scope_label="全阶段"):
    brand_disp = " / ".join(parse_brands(args.brand))
    scope_word = "仅抖音" if args.scope_platform == "douyin" else "全平台"
    L = []
    L.append(f"# 高引用视频信源索引（Top{args.top} · {scope_label} · {scope_word}）\n")
    L.append(
        f"> 品牌：{brand_disp} ｜ 范围：{scope_label} ｜ 平台范围：{scope_word} ｜ "
        f"剔除品牌题后 · 数据包期 {args.package_date}。"
    )
    total_answers = getattr(args, "_total_answers", None)
    L.append(f"> {_index_basis(video_top)}{_rate_clause(total_answers)}\n")
    L.append("## 一、视频引用次数表（Top%s）\n" % args.top)
    L.append("| 排名 | 视频标题 | 平台 | 引用次数 | 覆盖问题数 | 信源行数 | 原始链接 |")
    L.append("|---|---|---|---|---|---|---|")
    for i, x in enumerate(video_top):
        L.append(
            f"| {i+1} | {x['title']} | {x['site']} | {x['citation_count'] if x['citation_count'] is not None else '未获取'} | {x['question_count']} | "
            f"{x['total_pickups']} | {x['url']} |"
        )
    L.append("")
    L.append("## 二、视频 ↔ 问题收录映射\n")
    L.append("『收录』指该问题对应的 AI 回答引用了此视频信源。\n")
    for i, x in enumerate(video_top):
        rank = i + 1
        rel = _script_relpath(rank, x["title"])
        L.append(f"### 视频 {rank}：{x['title']}")
        L.append(f"- 平台：{x['site']} ｜ 引用次数：{x['citation_count'] if x['citation_count'] is not None else '未获取'} ｜ 覆盖 {x['question_count']} 道问题 ｜ 信源 {x['total_pickups']} 行")
        L.append(f"- 链接：{x['url']}")
        L.append(f"- 文案文件：`{rel}`\n")
        L.append("**被以下问题收录：**")
        pickups = x.get("question_pickups") or {}
        for q in x["questions"]:
            plats = " / ".join(x.get("question_platforms", {}).get(q, []))
            n = pickups.get(q, 1)
            L.append(f"- {q}（提取 {n} 次{'｜' + plats if plats else ''}）")
        L.append("")
    with open(idx_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print(f"交付: {idx_path}")


def _app_rate(citation_count, total_answers):
    if not total_answers or citation_count is None:
        return None
    return round(100 * citation_count / total_answers, 1)


def build_top_json(args, video_top):
    brands = parse_brands(args.brand)
    videos = []
    platforms = set()
    total_answers = getattr(args, "_total_answers", None)
    for i, x in enumerate(video_top):
        rank = i + 1
        plats = x.get("platforms") or []
        platforms |= set(plats)
        videos.append({
            "rank": rank,
            "title": x["title"],
            "url": x["url"],
            "site": x["site"],
            "domain": x["domain"],
            "video_id": x.get("video_id") or "",
            "citation_count": x["citation_count"],
            "question_count": x["question_count"],
            "citation_count_status": x["citation_count_status"],
            "app_rate": _app_rate(x["citation_count"], total_answers),
            "answer_keys": x["answer_keys"],
            "ranking_metric": x["ranking_metric"],
            "ranking_count": x["ranking_count"],
            "question_platforms": x["question_platforms"],
            "total_pickups": x["total_pickups"],
            "platforms": plats,
            "questions": x["questions"],
            "script_path": _script_relpath(rank, x["title"]),
            "account": "",
            "publish_date": "",
            "duration": "",
            "play_count": "",
            "word_count": None,
            "fetch_status": "pending",
            "analysis_eligible": False,
        })
    stages = getattr(args, "_stages_resolved", []) or []
    scope_label = getattr(args, "_scope_label", "全阶段")
    link_occurrence = any(x.get("citation_count_status") == "link_occurrence" for x in video_top)
    return {
        "meta": {
            "schema_version": 2,
            "ranking_metric": video_top[0]["ranking_metric"] if video_top else None,
            "total_answers": total_answers,
            "rate_status": "computed" if total_answers is not None else "needs_matching_answer_population",
            "denominator_source": (
                "diagnosis-answers.xlsx:answers（同品牌剔除/阶段/问题清单筛选）"
                if total_answers is not None else None
            ),
            "citation_count_status": "link_occurrence" if link_occurrence else "verified",
            "brand": brands,
            "package_date": args.package_date,
            "scope_platform": args.scope_platform,
            "scope_word": "仅抖音" if args.scope_platform == "douyin" else "全平台",
            "top": args.top,
            "platforms": sorted(platforms),
            "stages": stages,
            "scope_label": scope_label,
            "questions_file": bool(getattr(args, "questions_file", "") or ""),
        },
        "videos": videos,
    }


def _blank_record(record):
    for value in record.values():
        if value is not None and str(value).strip():
            return False
    return True


def load_answers(args):
    """xlsx 的 answers 表（表头, 行）；csv 或无此表时返回 None。"""
    if not getattr(args, "xlsx", ""):
        return None
    if openpyxl is None:
        return None
    wb = openpyxl.load_workbook(args.xlsx, read_only=True, data_only=True)
    try:
        if "answers" not in wb.sheetnames:
            return None
        try:
            return sheet_rows(wb["answers"])
        except StopIteration:
            return None
    finally:
        wb.close()


def count_answer_population(loaded, brands, stages, question_set):
    """同范围回答总数。loaded 为 None 时无法计算。"""
    if not loaded:
        return None
    header, rows = loaded
    fields = {name for name in header if name}
    has_status = "status" in fields
    id_fields = [name for name in ("platform_name", "question", "round", "index") if name in fields]
    keys = set()
    for record in rows:
        if _blank_record(record):
            continue
        if is_brand_question(record.get("question"), brands):
            continue
        if stages and (record.get("stage") or "") not in stages:
            continue
        if question_set is not None and (record.get("question") or "") not in question_set:
            continue
        if has_status and record.get("status") != "completed":
            continue
        keys.add(tuple("" if record.get(name) is None else str(record.get(name)).strip() for name in id_fields))
    return len(keys)


def load_records(args):
    """从 xlsx(source_urls) 或 csv(source-urls) 读原始信源行。"""
    if args.xlsx:
        if openpyxl is None:
            raise SystemExit("缺少 openpyxl：python3 -m pip install openpyxl")
        wb = openpyxl.load_workbook(args.xlsx, read_only=True, data_only=True)
        if "source_urls" not in wb.sheetnames:
            wb.close()
            raise SystemExit("xlsx 中无 source_urls sheet")
        _, rows = sheet_rows(wb["source_urls"])
        wb.close()
        return rows
    if args.csv:
        import csv
        with open(args.csv, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rows = [dict(r) for r in reader]
        return rows
    raise SystemExit("必须提供 --xlsx 或 --csv 之一")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", default="", help="数据包 diagnosis-answers.xlsx（含 source_urls sheet）")
    ap.add_argument("--csv", default="", help="analysis-v1 包的 tables/source-urls.csv")
    ap.add_argument("--brand", required=True, help="品牌名，逗号分隔多个别名")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--scope-platform", choices=["douyin", "all"], default="douyin",
                    help="douyin=仅抖音（默认）；all=全部视频平台")
    ap.add_argument("--package-date", required=True, help="数据包期日期 YYYYMMDD")
    ap.add_argument("--stages", default="",
                    help="题型阶段筛选，逗号分隔：探索/评估/行动。默认不筛=全阶段")
    ap.add_argument("--questions-file", default="", help="自定义问题清单（一行一题）")
    ap.add_argument("--out", required=True, help="分析包根目录（04-高引用分析/高引用视频分析-.../）")
    args = ap.parse_args()
    if args.top < 1:
        raise SystemExit("--top 必须为正整数")
    if os.path.exists(os.path.join(args.out, "_机器可读", "top.json")) or os.path.exists(os.path.join(args.out, "视频索引.md")):
        raise SystemExit("目标已有提取成果，请使用新的包目录；本脚本不覆盖已有报告。")

    brands = parse_brands(args.brand)
    if not brands:
        raise SystemExit("--brand 不能为空")
    if not re.fullmatch(r"\d{8}", args.package_date):
        raise SystemExit("--package-date 须为 YYYYMMDD")

    stages = parse_stages(args.stages)
    question_set = set(load_questions_file(args.questions_file)) if args.questions_file else None
    scope_label = scope_label_from_args(stages, bool(args.questions_file))
    args._stages_resolved = stages
    args._scope_label = scope_label

    rows = load_records(args)
    args._total_answers = count_answer_population(load_answers(args), brands, stages, question_set)
    nonbrand = [r for r in rows if not is_brand_question(r.get("question"), brands)]
    if stages:
        before = len(nonbrand)
        nonbrand = [r for r in nonbrand if (r.get("stage") or "") in stages]
        print(f"阶段筛选 {scope_label}：{before} → {len(nonbrand)} 条信源行")
    if question_set is not None:
        before = len(nonbrand)
        nonbrand = [r for r in nonbrand if (r.get("question") or "") in question_set]
        print(f"问题清单筛选：{before} → {len(nonbrand)} 条信源行（清单 {len(question_set)} 题）")
        if not nonbrand:
            raise SystemExit("筛选后无信源：请核对问题清单是否与数据包题干完全一致")

    def _keep(r):
        if not is_video(r.get("url"), r.get("domain")):
            return False
        if args.scope_platform == "douyin" and not is_douyin(r.get("url"), r.get("domain")):
            return False
        return True

    video_rows = [r for r in nonbrand if _keep(r)]
    if not video_rows:
        scope_word = "仅抖音" if args.scope_platform == "douyin" else "全部视频平台"
        raise SystemExit(
            f"范围「{scope_label}」在剔除品牌题后没有可用{scope_word}视频信源。"
            "常见原因：该阶段题全是点名品牌的题；或问题清单与题干不完全一致。"
            "请换阶段、放宽品牌别名、改用自定义问题清单，或换平台范围。"
        )

    out = args.out
    process_dir = os.path.join(out, "_过程")
    machine_dir = os.path.join(out, "_机器可读")
    os.makedirs(process_dir, exist_ok=True)
    os.makedirs(machine_dir, exist_ok=True)
    os.makedirs(os.path.join(out, "文案"), exist_ok=True)

    videos = aggregate(video_rows)
    video_top, _ = write_top_pair(videos, "", process_dir, args.top)
    build_index(video_top, args, os.path.join(out, "视频索引.md"), scope_label=scope_label)
    top_doc = build_top_json(args, video_top)
    top_path = os.path.join(machine_dir, "top.json")
    with open(top_path, "w", encoding="utf-8") as f:
        json.dump(top_doc, f, ensure_ascii=False, indent=2)
    print(f"交付: {top_path}（{len(top_doc['videos'])} 条）｜范围：{scope_label}")
    print("下一步: python scripts/fetch_video_scripts.py --package <包路径>")


if __name__ == "__main__":
    main()
