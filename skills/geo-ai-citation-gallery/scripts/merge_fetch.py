#!/usr/bin/env python3
"""把 douyin_fetch.py 的产出合并进分析包的 data.json。只用 Python 标准库。

用法（在技能根目录，即本文件所在 scripts/ 的上一级）:

  python3 scripts/merge_fetch.py --package <分析包> --fetch <douyin_fetch 输出目录> \\
      [--data gallery/data.json] [--images-dir gallery/images] [--shots-dir shots] \\
      [--shots-video] [--report-dir <默认 包/work/merge_fetch>] [--dry-run] [--overwrite] \\
      [--overwrite-fields f1,f2] [--keep-manual-desc-date] [--ranks 1,2,5]

规则摘要:
  - 按 video_id 字符串对齐。rank 只做辅助核对，不一致照样合并并写入报告。
  - 默认：发布文案和发布日期用抖音原文覆盖，其他字段只填空。
    覆盖字段：original_desc、post_desc、post_title、post_title_source、publish_date。
    可靠才覆盖：对应 field_status 为 ok，脚本值非 null 非空。
    original_desc / post_desc 看 desc，post_title 看 title，publish_date 看 publish_time 且值为 YYYY-MM-DD。
    抓不到、null 或非 ok 时不覆盖，保留旧值。
    post_title_source 只在 post_title 被写入或已相同时跟着更新。
  - 其他字段只填空：null、空字符串、空列表、「暂未抓取到」、「暂未获取」。已有人工值（含人工 0）不覆盖。
  - 两边都有值且不同、又没有被覆盖 → 报告「冲突（未覆盖）」，列出人工值 / 脚本值。
  - 字符串只差空白（换行、连续空格、首尾空格）视为相同：不算改动、不写、不记冲突，覆盖时也不改写。
    报告单独计「只差空白，未改」。
  - 人工值为 0、该行 eng_suspect_zero 为 true、脚本值非 0 → 冲突里标注「人工 0 可疑」。
  - --keep-manual-desc-date：发布文案和发布日期也改回只填空，差异记入冲突。
  - 优先级：--overwrite（全部）> --overwrite-fields 列出的字段 > 默认文案日期覆盖（除非 --keep-manual-desc-date）> 只填空。
  - --overwrite：脚本值可靠时覆盖人工值，报告写旧值 → 新值。content_type 例外，只在人工为空时填。
  - --overwrite-fields f1,f2：列出的字段按覆盖规则更新，记入「覆盖（旧值 → 新值）」。
    没列出的发布文案和发布日期仍按默认覆盖，记入「默认覆盖」，除非同时给了 --keep-manual-desc-date。
    其他字段只填空。与默认文案日期覆盖叠加，不是互相关掉。
    未知字段名报错退出。content_type 不支持覆盖，写进列表会报错退出（只在人工为空时填）。
    与 --overwrite 同时给出时以 --overwrite（全部）为准，并在报告里写明。
    例：--overwrite-fields digg_count。
  - 覆盖 original_desc 时，旧值若既不等于 citation_title（空白等价）也不等于新值，写入 original_desc_prev（已有非空则不覆盖）。
  - citation_title 只取 _机器可读/top.json 同 video_id 的 title，任何模式都不从脚本取值。
    在覆盖文案之前写入。已有 citation_title 且与 top.json 不同时，默认不覆盖、记冲突。
  - title / title_short 不修改。
  - 脚本值为 null / 缺失 → 不写。脚本值为 0 → 只有 field_status 对应字段 status=ok 才写。
  - fetch 条目 status 为 blocked 或 missing → 该条不写任何脚本值。
  - 不确定的字段不写。play_count 不合并。
  - post_desc 取 items.original_desc，field_status.desc=ok 才写。
    模板 / build_report 的「发布文案全文」读 original_desc，不读 post_desc。
    默认模式下，原「original_desc 实为诊断包引用标题」只报已被默认覆盖的条数。
    --overwrite-fields 未点名 original_desc 时同样只报条数。
    点名覆盖 original_desc（或 --overwrite）时按覆盖参数只报条数。
    只有 --keep-manual-desc-date 且没有点名覆盖 original_desc 时仍列出这些条目。
  - post_title / citation_title：模板不读这两个字段，页面不变。
  - 人工已有 transcript 但没有 transcript_status 时，补 transcript_status=pending。
  - 图片（封面、抽帧、图文原图）复制到 shots-dir。mp4 / m4a 默认不复制，仍留在 fetch 输出目录；
    给了 --shots-video 才复制进 shots-dir。报告「文件」一节写明未复制及原因。
  - 可补图（未改）只复制到 shots-dir。只有 data.images 真被写入时才复制进 images-dir。
    --dry-run 不复制任何文件。
  - 写入前把 data.json 备份为同目录 data.json.bak-merge-YYYYMMDDHHMMSS（本地时间）。
  - --dry-run 不写任何文件，只把差异摘要打到标准输出。
"""

from __future__ import annotations

import argparse
import filecmp
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path


EMPTY_TEXT = ("", "暂未抓取到", "暂未获取")
ENGAGEMENT_FIELDS = (
    "follower_count",
    "digg_count",
    "collect_count",
    "share_count",
    "comment_count",
)
VIDEO_DETAIL = ("口播", "混剪")
VIDEO_TYPES = ("视频", "口播", "混剪")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
SHOTS_EXTRA_SUFFIXES = {".mp4", ".m4a"}
KEY_FIELDS = (
    "digg_count",
    "collect_count",
    "share_count",
    "comment_count",
    "follower_count",
    "publish_date",
    "account_name",
    "original_desc",
    "images",
)
STATUS_KEY = {
    "original_desc": "desc",
    "hashtags": "hashtags",
    "account": "account",
    "account_name": "account",
    "follower_count": "follower_count",
    "digg_count": "digg_count",
    "collect_count": "collect_count",
    "share_count": "share_count",
    "comment_count": "comment_count",
    "duration_sec": "duration_sec",
    "publish_date": "publish_time",
    "transcript": "transcript",
    "content_type": "content_type",
    "images": "images",
    "image_count": "images",
    "frame_count": "frames",
    "post_title": "title",
    "post_desc": "desc",
}
STAT_FIELDS = (
    "original_desc",
    "post_desc",
    "hashtags",
    "account",
    "account_name",
    "follower_count",
    "digg_count",
    "collect_count",
    "share_count",
    "comment_count",
    "duration_sec",
    "publish_date",
    "transcript",
    "transcript_status",
    "content_type",
    "images",
    "image_count",
    "frame_count",
    "post_title",
    "post_title_source",
    "citation_title",
)
BACKFILL_NOTE = (
    "build_report 要求有 transcript 就必须有状态，未核对一律 pending"
)
TEMPLATE_NOTE = (
    "模板不读 post_title / citation_title，页面不变。模板也不读 post_desc；"
    "页面「发布文案全文」读 original_desc"
)
DESC_DATE_FIELDS = (
    "original_desc",
    "post_desc",
    "post_title",
    "post_title_source",
    "publish_date",
)
DESC_ALIAS_TITLE = "original_desc 实为诊断包引用标题"
DESC_ALIAS_NOTE = (
    "模板 / build_report 的「发布文案全文」读 original_desc，"
    "要让页面显示平台真实文案，跑 `--overwrite-fields original_desc`。"
)
DESC_ALIAS_DEFAULT_NOTE = (
    "这些条目的 original_desc 原为诊断包引用标题，已被默认覆盖，改用抖音原文。"
    "诊断包标题留在 citation_title。"
)
DESC_ALIAS_FLAG_NOTE = (
    "这些条目的 original_desc 原为诊断包引用标题，已按本次覆盖参数更新。"
    "诊断包标题留在 citation_title。"
)
DEFAULT_DESC_NOTE = (
    "默认覆盖发布文案和发布日期：original_desc、post_desc、post_title、post_title_source、publish_date。"
    "对应 field_status 为 ok 且脚本值非空才覆盖（original_desc / post_desc 看 desc，post_title 看 title，"
    "publish_date 看 publish_time 且值为 YYYY-MM-DD）。抓不到、null 或非 ok 时保留旧值。"
    "post_title_source 只在 post_title 被写入或已相同时跟着更新。其他字段仍只填空。"
)
PRIORITY_NOTE = (
    "优先级：--overwrite（全部）> --overwrite-fields 列出的字段 > "
    "默认文案日期覆盖（除非 --keep-manual-desc-date）> 只填空。"
)
KEEP_NOTE = (
    "本次已给 --keep-manual-desc-date：发布文案和发布日期按只填空，差异记入冲突（未覆盖）。"
)
PREV_NOTE = (
    "覆盖 original_desc 时，旧值若不是 citation_title（空白等价）也不是新值，写入 original_desc_prev；已有非空值不覆盖。"
)
BOTH_OVERWRITE_NOTE = (
    "同时给出 --overwrite 与 --overwrite-fields，以 --overwrite（全部字段）为准。"
)
WS_NOTE = "字符串只差空白（换行、连续空格、首尾空格）视为相同，不记冲突，覆盖时也不改写。只差空白单独计数，不算改动。"
VIDEO_SKIP_NOTE = "mp4 / m4a 默认不复制进 shots，仍在 fetch 输出目录。需要时加 --shots-video。"
OVERWRITE_FIELD_NAMES = tuple(name for name in STAT_FIELDS if name != "content_type")
FIELD_STAT_KEYS = ("filled", "default_overwritten", "overwritten")


def die(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(2)


def is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value in EMPTY_TEXT:
        return True
    if isinstance(value, (list, tuple)) and len(value) == 0:
        return True
    return False


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def whitespace_key(value: str) -> str:
    """换行、连续空白、首尾空白压成单空格后的比较键。"""
    return " ".join(value.split())


def values_equal(left, right) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left == right
    if is_number(left) and is_number(right):
        return left == right
    if isinstance(left, str) and isinstance(right, str):
        return whitespace_key(left) == whitespace_key(right)
    if isinstance(left, list) and isinstance(right, list):
        return left == right
    return left == right


def is_yyyy_mm_dd(value) -> bool:
    if not isinstance(value, str) or len(value) != 10:
        return False
    if value[4] != "-" or value[7] != "-":
        return False
    year, month, day = value[0:4], value[5:7], value[8:10]
    return year.isdigit() and month.isdigit() and day.isdigit()


def title_matches_citation(title, citation) -> bool:
    """空白归一后，title 去掉末尾省略号，非空且是 citation_title 的前缀（含完全相等）。

    空标题和占位「（无短标题）」算其他来源。
    """
    if not isinstance(title, str) or not isinstance(citation, str):
        return False
    title_key = whitespace_key(title)
    citation_key = whitespace_key(citation)
    if title_key.endswith("…"):
        title_key = whitespace_key(title_key[:-1])
    elif title_key.endswith("..."):
        title_key = whitespace_key(title_key[:-3])
    if title_key == "" or citation_key == "" or is_empty(title_key) or is_empty(citation_key):
        return False
    if title_key == "（无短标题）":
        return False
    return citation_key.startswith(title_key)


def summarize_title_source(rows: list) -> dict:
    other_ranks = []
    citation_count = 0
    for row in rows:
        if title_matches_citation(row.get("title"), row.get("citation_title")):
            citation_count += 1
        else:
            other_ranks.append(as_rank(row.get("rank")))
    return {
        "note": "title 本轮不改",
        "citation_title_count": citation_count,
        "other_count": len(other_ranks),
        "other_ranks": other_ranks,
        "label_citation": "诊断包引用标题",
        "label_other": "其他来源",
    }


def as_rank(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def video_id_of(row: dict) -> str:
    value = row.get("video_id")
    if value is None:
        return ""
    return str(value).strip()


def field_meta(fields: dict, key: str) -> tuple[str | None, str]:
    meta = fields.get(key)
    if not isinstance(meta, dict):
        return None, ""
    status = meta.get("status")
    reason = meta.get("reason") or ""
    if not isinstance(status, str):
        return None, str(reason)
    return status, str(reason)


def for_report(value):
    if isinstance(value, str):
        text = value.replace("\r\n", "\n").replace("\n", "\\n")
        if len(text) > 80:
            return text[:80] + "…"
        return text
    if isinstance(value, list):
        copied = list(value)
        if len(copied) > 6:
            return copied[:6] + [f"…共{len(value)}项"]
        return copied
    return value


def show(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def suspect_zero(row: dict, field: str, manual, script) -> bool:
    if field not in ENGAGEMENT_FIELDS:
        return False
    if not is_number(manual) or manual != 0:
        return False
    if not is_number(script) or script == 0:
        return False
    return row.get("eng_suspect_zero") is True


def copy_value(value):
    if isinstance(value, list):
        return list(value)
    return value


def parse_ranks(text: str):
    if text is None or str(text).strip() == "":
        return None
    ranks = set()
    for part in str(text).split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit():
            raise argparse.ArgumentTypeError("ranks 应为逗号分隔的正整数，例如 1,2,5")
        ranks.add(int(part))
    if not ranks:
        raise argparse.ArgumentTypeError("ranks 为空")
    return ranks


def parse_overwrite_fields(text: str):
    if text is None or str(text).strip() == "":
        raise argparse.ArgumentTypeError("overwrite-fields 需要逗号分隔的字段名，例如 original_desc")
    names = []
    seen = set()
    unknown = []
    blocked_content_type = False
    for part in str(text).split(","):
        name = part.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        if name == "content_type":
            blocked_content_type = True
            continue
        if name not in OVERWRITE_FIELD_NAMES:
            unknown.append(name)
            continue
        names.append(name)
    if blocked_content_type:
        raise argparse.ArgumentTypeError("content_type 不支持覆盖，只在人工为空时填")
    if unknown:
        known = "、".join(OVERWRITE_FIELD_NAMES)
        raise argparse.ArgumentTypeError("未知字段：" + "、".join(unknown) + "。可用字段：" + known)
    if not names:
        raise argparse.ArgumentTypeError("overwrite-fields 为空")
    return names


def under(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path


def load_json(path: Path):
    if not path.is_file():
        die(f"找不到文件：{path}")
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except UnicodeError:
        die(f"文件不是 UTF-8：{path}")
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        die(f"JSON 无法解析：{path}（{exc}）")
    return obj, raw, text


def split_rows(obj):
    """返回 (rows, container)。container 为 None 表示根就是 list。"""
    if isinstance(obj, list):
        return obj, None
    if isinstance(obj, dict) and isinstance(obj.get("data"), list):
        return obj["data"], obj
    die("无法识别 data.json 结构：需要 list，或含 data 列表的对象")


def load_items(fetch: Path) -> list:
    obj, _, _ = load_json(fetch / "items.json")
    if not isinstance(obj, list):
        die(f"{fetch / 'items.json'} 不是列表")
    for item in obj:
        if not isinstance(item, dict):
            die("items.json 里有非对象条目")
    return obj


def load_field_status(fetch: Path) -> dict:
    obj, _, _ = load_json(fetch / "field_status.json")
    if not isinstance(obj, list):
        die(f"{fetch / 'field_status.json'} 不是列表")
    by_id = {}
    for row in obj:
        if not isinstance(row, dict):
            die("field_status.json 里有非对象条目")
        vid = video_id_of(row)
        if not vid:
            continue
        by_id.setdefault(vid, row)
    return by_id


def load_citation_titles(package: Path):
    """文件不存在返回 None。存在则返回 video_id → title。"""
    path = package / "_机器可读" / "top.json"
    if not path.is_file():
        return None
    obj, _, _ = load_json(path)
    videos = obj.get("videos") if isinstance(obj, dict) else None
    found = {}
    if not isinstance(videos, list):
        return found
    for row in videos:
        if not isinstance(row, dict):
            continue
        vid = video_id_of(row)
        title = row.get("title")
        if not vid or not isinstance(title, str) or title.strip() == "":
            continue
        if title in EMPTY_TEXT:
            continue
        found.setdefault(vid, title)
    return found


def reliable_text(item: dict, fields: dict, item_key: str, status_key: str):
    status, _reason = field_meta(fields, status_key)
    if status != "ok":
        return None
    value = item.get(item_key)
    if not isinstance(value, str) or value in EMPTY_TEXT:
        return None
    return value


def reliable_count(item: dict, fields: dict, key: str):
    status, _reason = field_meta(fields, key)
    if status != "ok":
        return None
    value = item.get(key)
    if not is_number(value):
        return None
    return value


def reliable_tags(item: dict, fields: dict):
    status, _reason = field_meta(fields, "hashtags")
    if status != "ok":
        return None
    value = item.get("hashtags")
    if not isinstance(value, list) or len(value) == 0:
        return None
    if not all(isinstance(tag, str) and tag not in EMPTY_TEXT for tag in value):
        return None
    return list(value)


def reliable_transcript(item: dict, fields: dict):
    if item.get("transcript_status") != "ok":
        return None
    status, _reason = field_meta(fields, "transcript")
    if status != "ok":
        return None
    value = item.get("transcript")
    if not isinstance(value, str) or value.strip() == "" or value in EMPTY_TEXT:
        return None
    return value


def reliable_content_type(item: dict, fields: dict):
    status, _reason = field_meta(fields, "content_type")
    if status != "ok":
        return None
    value = item.get("content_type")
    if value not in ("图文", "视频"):
        return None
    return value


def reliable_post_title(item: dict, fields: dict):
    status, _reason = field_meta(fields, "title")
    if status != "ok":
        return None, None
    title = item.get("title")
    if not isinstance(title, str) or title in EMPTY_TEXT:
        return None, None
    source = item.get("title_source")
    if not isinstance(source, str) or source in EMPTY_TEXT:
        source = None
    return title, source


def resolve_fetch_file(fetch_dir: Path, rel) -> Path | None:
    if not isinstance(rel, str) or rel.strip() == "":
        return None
    rel_path = Path(rel)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        return None
    name = rel_path.name
    if name in ("", ".", ".."):
        return None
    root = fetch_dir.resolve()
    candidate = (fetch_dir / rel_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def is_cover_name(value) -> bool:
    name = Path(str(value)).name
    stem = Path(name).stem
    suffix = Path(name).suffix
    return stem.endswith("_cover") and suffix != ""


def manual_cover_only(row: dict) -> bool:
    images = row.get("images")
    if not isinstance(images, list) or len(images) == 0:
        return False
    if row.get("capture_status") == "cover_only":
        return True
    return all(is_cover_name(item) for item in images)


def rank_token(rank: int) -> str:
    return f"{rank:02d}"


def inspect_transfer(fetch_dir: Path, rel: str, root: Path, rank: int, where: str, images_only: bool):
    """查看一次复制会怎样。不写盘。后缀不在范围内时返回 None。"""
    src = resolve_fetch_file(fetch_dir, rel)
    name = Path(rel).name if isinstance(rel, str) else ""
    suffix = Path(name).suffix.lower()
    dest_rel = f"douyin_fetch/{rank_token(rank)}/{name}"
    entry = {
        "rank": rank,
        "where": where,
        "src": rel if isinstance(rel, str) else "",
        "dest": dest_rel,
        "action": "missing",
    }
    if src is None or name in ("", ".", ".."):
        return {"entry": entry, "src_path": None, "dest_path": None}
    allowed = IMAGE_SUFFIXES if images_only else IMAGE_SUFFIXES | SHOTS_EXTRA_SUFFIXES
    if suffix not in allowed:
        return None
    if not src.is_file():
        return {"entry": entry, "src_path": None, "dest_path": None}
    dest = root / dest_rel
    if dest.exists():
        try:
            same = filecmp.cmp(src, dest, shallow=False)
        except OSError:
            entry["action"] = "diff"
        else:
            entry["action"] = "same" if same else "diff"
    else:
        entry["action"] = "would_copy"
    return {"entry": entry, "src_path": src, "dest_path": dest}


def planned_images(item: dict, fields: dict, content_type: str) -> list[str]:
    rels = []
    if content_type == "图文":
        status, _reason = field_meta(fields, "images")
        if status != "ok":
            return []
        images = item.get("images")
        if not isinstance(images, list):
            return []
        for rel in images:
            if isinstance(rel, str) and rel:
                rels.append(rel)
    elif content_type == "视频":
        cover_status, _reason = field_meta(fields, "cover")
        if cover_status == "ok" and isinstance(item.get("cover"), str) and item.get("cover"):
            rels.append(item["cover"])
        frames_status, _reason = field_meta(fields, "frames")
        frames = item.get("frames")
        if frames_status == "ok" and isinstance(frames, list):
            for frame in frames:
                if isinstance(frame, dict) and isinstance(frame.get("file"), str) and frame.get("file"):
                    rels.append(frame["file"])
                elif isinstance(frame, str) and frame:
                    rels.append(frame)
    deduped = []
    seen = set()
    for rel in rels:
        if rel in seen:
            continue
        seen.add(rel)
        deduped.append(rel)
    return deduped


def extra_shot_rels(item: dict) -> list[str]:
    rels = []
    for key in ("video_file", "audio_file"):
        rel = item.get(key)
        if isinstance(rel, str) and rel:
            rels.append(rel)
    return rels


class Merger:
    def __init__(self, args, package: Path, fetch: Path, data_path: Path, images_dir: Path, shots_dir: Path):
        self.args = args
        self.package = package
        self.fetch = fetch
        self.data_path = data_path
        self.images_dir = images_dir
        self.shots_dir = shots_dir
        self.overwrite_all = bool(args.overwrite)
        self.overwrite_field_list = list(args.overwrite_fields) if args.overwrite_fields else None
        self.overwrite_field_set = set(self.overwrite_field_list or [])
        self.both_overwrite = bool(self.overwrite_all and self.overwrite_field_list)
        self.keep_manual_desc_date = bool(getattr(args, "keep_manual_desc_date", False))
        self.dry_run = bool(args.dry_run)
        self.filled = []
        self.overwritten = []
        self.desc_date_overwritten = []
        self.original_desc_prev_saved = []
        self.citation_alias_overwritten = []
        self.whitespace_unchanged = 0
        self.conflicts = []
        self.image_supplements = []
        self.zeros_written = []
        self.file_ops = []
        self.videos_not_copied = []
        self.shots_video = bool(getattr(args, "shots_video", False))
        self.backfill_ids = []
        self.content_type_notes = []
        self.field_stats = {name: {key: 0 for key in FIELD_STAT_KEYS} for name in STAT_FIELDS}

    def bump(self, field: str, kind: str) -> None:
        slot = self.field_stats.setdefault(field, {key: 0 for key in FIELD_STAT_KEYS})
        slot[kind] = slot.get(kind, 0) + 1

    def overwrite_kind(self, field: str) -> str | None:
        """flag：--overwrite，或 --overwrite-fields 点名的字段。
        default：未点名的文案和日期。--keep-manual-desc-date 时这些字段改为只填空。
        None：只填空。
        """
        if field == "content_type":
            return None
        if self.overwrite_all:
            return "flag"
        if field in self.overwrite_field_set:
            return "flag"
        if self.keep_manual_desc_date:
            return None
        if field in DESC_DATE_FIELDS:
            return "default"
        return None

    def allows_overwrite(self, field: str) -> bool:
        return self.overwrite_kind(field) is not None

    def zero_basis(self, fields: dict, field: str) -> dict:
        status_key = STATUS_KEY.get(field, field)
        status, reason = field_meta(fields, status_key)
        return {"field_status": status, "reason": reason, "status_key": status_key}

    def record_fill(self, row: dict, field: str, value, fields: dict | None) -> None:
        stored = copy_value(value)
        row[field] = stored
        entry = {
            "rank": as_rank(row.get("rank")),
            "video_id": video_id_of(row),
            "field": field,
            "value": for_report(stored),
        }
        self.filled.append(entry)
        self.bump(field, "filled")
        if is_number(stored) and stored == 0 and fields is not None:
            basis = self.zero_basis(fields, field)
            self.zeros_written.append({
                "rank": entry["rank"],
                "video_id": entry["video_id"],
                "field": field,
                "value": 0,
                "field_status": basis["field_status"],
                "reason": basis["reason"],
                "status_key": basis["status_key"],
            })

    def record_overwrite(self, row: dict, field: str, old, new, fields: dict | None, *, bucket: str = "flag") -> None:
        stored = copy_value(new)
        row[field] = stored
        entry = {
            "rank": as_rank(row.get("rank")),
            "video_id": video_id_of(row),
            "field": field,
            "old": for_report(old),
            "new": for_report(stored),
        }
        if suspect_zero(row, field, old, stored):
            entry["note"] = "人工 0 可疑"
        if bucket == "default":
            self.desc_date_overwritten.append(entry)
            self.bump(field, "default_overwritten")
        else:
            self.overwritten.append(entry)
            self.bump(field, "overwritten")
        if field == "original_desc":
            self.note_citation_alias(row, old, stored)
            self.maybe_save_original_desc_prev(row, old, stored)
        if is_number(stored) and stored == 0 and fields is not None:
            basis = self.zero_basis(fields, field)
            self.zeros_written.append({
                "rank": entry["rank"],
                "video_id": entry["video_id"],
                "field": field,
                "value": 0,
                "field_status": basis["field_status"],
                "reason": basis["reason"],
                "status_key": basis["status_key"],
                "overwritten": True,
            })

    def note_whitespace(self, field: str, manual, script_value) -> None:
        if field not in DESC_DATE_FIELDS:
            return
        if isinstance(manual, str) and isinstance(script_value, str) and manual != script_value:
            self.whitespace_unchanged += 1

    def note_citation_alias(self, row: dict, old, new) -> None:
        citation = row.get("citation_title")
        if not isinstance(old, str) or not isinstance(citation, str):
            return
        if is_empty(citation) or not values_equal(old, citation):
            return
        if values_equal(old, new):
            return
        self.citation_alias_overwritten.append({
            "rank": as_rank(row.get("rank")),
            "video_id": video_id_of(row),
        })

    def maybe_save_original_desc_prev(self, row: dict, old, new) -> None:
        """人工文案既不是诊断包标题、也不是新文案时，空才写入 original_desc_prev。"""
        if is_empty(old) or values_equal(old, new):
            return
        citation = row.get("citation_title")
        if isinstance(citation, str) and not is_empty(citation) and values_equal(old, citation):
            return
        if "original_desc_prev" in row and not is_empty(row.get("original_desc_prev")):
            return
        row["original_desc_prev"] = old
        self.original_desc_prev_saved.append({
            "rank": as_rank(row.get("rank")),
            "video_id": video_id_of(row),
            "value": for_report(old),
        })

    def record_conflict(self, row: dict, field: str, manual, script, note: str = "") -> None:
        entry = {
            "rank": as_rank(row.get("rank")),
            "video_id": video_id_of(row),
            "field": field,
            "manual": for_report(manual),
            "script": for_report(script),
            "suspect_zero": suspect_zero(row, field, manual, script),
        }
        if note:
            entry["note"] = note
        self.conflicts.append(entry)

    def apply_value(self, row: dict, field: str, script_value, fields: dict, *, allow_overwrite: bool = True, note: str = "") -> str:
        if script_value is None:
            return "skip"
        manual = row.get(field) if field in row else None
        empty = field not in row or is_empty(manual)
        if empty:
            self.record_fill(row, field, script_value, fields)
            return "fill"
        if values_equal(manual, script_value):
            self.note_whitespace(field, manual, script_value)
            return "same"
        if field == "content_type" and script_value == "视频" and manual in VIDEO_DETAIL:
            return "same_granularity"
        kind = self.overwrite_kind(field) if allow_overwrite else None
        if kind:
            self.record_overwrite(
                row, field, manual, script_value, fields, bucket="default" if kind == "default" else "flag"
            )
            return "overwrite"
        self.record_conflict(row, field, manual, script_value, note=note)
        return "conflict"

    def commit_transfer(self, inspected: dict, *, copy: bool) -> str | None:
        entry = inspected["entry"]
        action = entry["action"]
        src = inspected["src_path"]
        dest = inspected["dest_path"]
        if copy and action == "would_copy" and src is not None and dest is not None and not self.dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            entry["action"] = "copied"
            action = "copied"
        self.file_ops.append(entry)
        if action in ("copied", "same", "would_copy"):
            return entry["dest"]
        return None

    def consider_extra_shot(self, row: dict, rel: str) -> None:
        """mp4 / m4a 默认留在 fetch 输出目录。--shots-video 才复制进 shots。"""
        suffix = Path(rel).suffix.lower() if isinstance(rel, str) else ""
        if suffix not in SHOTS_EXTRA_SUFFIXES:
            return
        rank = as_rank(row.get("rank"))
        if rank is None:
            return
        if self.shots_video:
            inspected = inspect_transfer(self.fetch, rel, self.shots_dir, rank, "shots", False)
            if inspected is not None:
                self.commit_transfer(inspected, copy=True)
            return
        src = resolve_fetch_file(self.fetch, rel)
        self.videos_not_copied.append({
            "rank": rank,
            "video_id": video_id_of(row),
            "src": rel,
            "exists": src is not None and src.is_file(),
            "note": VIDEO_SKIP_NOTE,
        })

    def apply_images(self, row: dict, item: dict, fields: dict, content_type: str | None) -> None:
        if content_type not in ("图文", "视频"):
            return
        rank = as_rank(row.get("rank"))
        if rank is None:
            return
        plan = planned_images(item, fields, content_type)
        manual_images = row.get("images")
        manual_list = list(manual_images) if isinstance(manual_images, list) else []
        images_empty = "images" not in row or is_empty(manual_images)
        supplement = (not images_empty) and manual_cover_only(row) and len(plan) > len(manual_list)
        want_write = images_empty and len(plan) > 0
        want_replace = supplement and self.allows_overwrite("images")
        if not (want_write or want_replace or supplement):
            self.apply_counts(row, item, fields, content_type)
            return

        image_inspected = []
        placed = []
        for rel in plan:
            inspected = inspect_transfer(self.fetch, rel, self.images_dir, rank, "images", True)
            image_inspected.append(inspected)
            if inspected and inspected["entry"]["action"] in ("would_copy", "same"):
                placed.append(inspected["entry"]["dest"])
        placed_all = len(plan) > 0 and len(placed) == len(plan)
        # 只有 data.images 真会被写入时才把文件放进 images-dir。可补图（未改）只留 shots。
        do_write = (want_write and len(placed) > 0) or (want_replace and placed_all)
        if want_write or want_replace:
            for inspected in image_inspected:
                if inspected is None:
                    continue
                if inspected["entry"]["action"] == "would_copy" and not do_write:
                    continue
                self.commit_transfer(inspected, copy=do_write)
        for rel in plan:
            inspected = inspect_transfer(self.fetch, rel, self.shots_dir, rank, "shots", True)
            if inspected is not None:
                self.commit_transfer(inspected, copy=True)
        if content_type == "视频":
            for rel in extra_shot_rels(item):
                self.consider_extra_shot(row, rel)

        if want_write and placed:
            self.record_fill(row, "images", placed, fields)
        elif want_replace and placed_all:
            self.record_overwrite(row, "images", manual_list, placed, fields)
        elif supplement:
            self.image_supplements.append({
                "rank": rank,
                "video_id": video_id_of(row),
                "manual_count": len(manual_list),
                "script_count": len(plan),
                "placed": placed,
                "applied": False,
                "note": "可补图（未改）",
            })
        if want_write and placed and len(placed) < len(plan):
            self.image_supplements.append({
                "rank": rank,
                "video_id": video_id_of(row),
                "manual_count": len(manual_list),
                "script_count": len(plan),
                "placed": placed,
                "applied": True,
                "note": "部分图片未放入（缺失或同名内容不同），data.images 只写入已放入的文件",
            })
        self.apply_counts(row, item, fields, content_type)

    def apply_counts(self, row: dict, item: dict, fields: dict, content_type: str) -> None:
        if content_type == "图文":
            status, _reason = field_meta(fields, "images")
            if status == "ok":
                count = item.get("image_count")
                if not is_number(count):
                    images = item.get("images")
                    count = len(images) if isinstance(images, list) else None
                if is_number(count):
                    self.apply_value(row, "image_count", count, fields)
        if content_type == "视频":
            status, _reason = field_meta(fields, "frames")
            frames = item.get("frames")
            if status == "ok" and isinstance(frames, list) and len(frames) > 0:
                self.apply_value(row, "frame_count", len(frames), fields)

    def apply_fetch(self, row: dict, item: dict, fields: dict) -> None:
        desc = reliable_text(item, fields, "original_desc", "desc")
        self.apply_value(row, "original_desc", desc, fields)
        self.apply_value(row, "post_desc", desc, fields)
        text_fields = (
            ("account", "account", "account"),
            ("account_name", "account_name", "account"),
            ("publish_date", "publish_date", "publish_time"),
        )
        for data_key, item_key, status_key in text_fields:
            if data_key == "publish_date":
                value = reliable_text(item, fields, item_key, status_key)
                if is_yyyy_mm_dd(value):
                    self.apply_value(row, data_key, value, fields)
                continue
            self.apply_value(row, data_key, reliable_text(item, fields, item_key, status_key), fields)
        self.apply_value(row, "hashtags", reliable_tags(item, fields), fields)
        for key in ("follower_count", "digg_count", "collect_count", "share_count", "comment_count", "duration_sec"):
            self.apply_value(row, key, reliable_count(item, fields, key), fields)
        content_type = reliable_content_type(item, fields)
        action = self.apply_value(
            row,
            "content_type",
            content_type,
            fields,
            allow_overwrite=False,
            note="content_type 只在人工为空时填，未覆盖",
        )
        if action == "fill" and content_type == "视频":
            self.content_type_notes.append({
                "rank": as_rank(row.get("rank")),
                "video_id": video_id_of(row),
                "note": "content_type 填了「视频」，需人工细分口播/混剪",
            })
        transcript = reliable_transcript(item, fields)
        transcript_action = self.apply_value(row, "transcript", transcript, fields)
        if transcript_action in ("fill", "overwrite"):
            current = row.get("transcript_status") if "transcript_status" in row else None
            if "transcript_status" not in row or is_empty(current) or current != "pending":
                if "transcript_status" not in row or is_empty(current):
                    self.record_fill(row, "transcript_status", "pending", fields)
                elif self.allows_overwrite("transcript_status") and current != "pending":
                    self.record_overwrite(row, "transcript_status", current, "pending", fields)
                elif current != "pending":
                    self.record_conflict(
                        row,
                        "transcript_status",
                        current,
                        "pending",
                        note="新写入的转写未经核对，状态应为 pending",
                    )
        self.apply_images(row, item, fields, content_type)
        title, source = reliable_post_title(item, fields)
        title_action = self.apply_value(row, "post_title", title, fields)
        if source and title_action in ("fill", "overwrite", "same"):
            self.apply_value(row, "post_title_source", source, fields)

    def backfill_transcript_status(self, row: dict) -> None:
        if is_empty(row.get("transcript")):
            return
        if "transcript_status" in row and not is_empty(row.get("transcript_status")):
            return
        self.record_fill(row, "transcript_status", "pending", None)
        self.backfill_ids.append(video_id_of(row))

    def apply_citation(self, row: dict, titles: dict | None) -> None:
        if titles is None:
            return
        title = titles.get(video_id_of(row))
        if not title:
            return
        self.apply_value(row, "citation_title", title, {})


def citation_title_desc_entries(rows: list) -> list:
    """original_desc 与 citation_title 相同、且 post_desc 不同的行。预览各取前 40 字。"""
    found = []
    for row in rows:
        original = row.get("original_desc")
        citation = row.get("citation_title")
        post = row.get("post_desc")
        if not isinstance(original, str) or not isinstance(citation, str) or not isinstance(post, str):
            continue
        if is_empty(original) or is_empty(citation) or is_empty(post):
            continue
        if not values_equal(original, citation):
            continue
        if values_equal(post, original):
            continue
        found.append({
            "rank": as_rank(row.get("rank")),
            "video_id": video_id_of(row),
            "original_desc": original[:40],
            "post_desc": post[:40],
        })
    return found


def needs_video_fields(row: dict, item: dict | None) -> bool:
    content_type = row.get("content_type")
    if is_empty(content_type) and item is not None:
        content_type = item.get("content_type")
    return content_type in VIDEO_TYPES


def still_missing_for(row: dict, item: dict | None, fields: dict | None, fetch_status) -> dict | None:
    names = list(KEY_FIELDS)
    if needs_video_fields(row, item):
        names.extend(["duration_sec", "transcript"])
    missing = []
    for name in names:
        if name in row and not is_empty(row.get(name)):
            continue
        if name not in row or is_empty(row.get(name)):
            status_key = STATUS_KEY.get(name, name)
            status, reason = (None, "")
            if fields:
                status, reason = field_meta(fields, status_key)
            if not reason:
                if item is None:
                    reason = "fetch 中没有该 video_id"
                elif fetch_status in ("blocked", "missing"):
                    reason = f"fetch status={fetch_status}"
                    error = item.get("error") if isinstance(item, dict) else None
                    if error:
                        reason = f"{reason}；{error}"
                elif status is None:
                    reason = "无可靠脚本值"
                else:
                    reason = f"field_status={status}，无可靠脚本值"
            missing.append({
                "field": name,
                "field_status": status,
                "reason": reason,
                "status_key": status_key,
            })
    if not missing:
        return None
    return {
        "rank": as_rank(row.get("rank")),
        "video_id": video_id_of(row),
        "fetch_status": fetch_status,
        "fields": missing,
    }


def pick_fetch(cands: list, row: dict) -> dict | None:
    if not cands:
        return None
    rank = as_rank(row.get("rank"))
    for item in cands:
        if as_rank(item.get("rank")) == rank:
            return item
    return cands[0]


def desc_date_stats_of(merger: Merger) -> dict:
    stats = {name: 0 for name in DESC_DATE_FIELDS}
    for row in merger.desc_date_overwritten:
        name = row["field"]
        if name in stats:
            stats[name] += 1
    stats["whitespace_unchanged"] = merger.whitespace_unchanged
    return stats


def alias_report(merger: Merger, remaining: list) -> dict:
    """original_desc 被默认覆盖或被点名覆盖时只报条数。
    只有 --keep-manual-desc-date、且没有点名覆盖 original_desc 时，才保留原列表。
    --overwrite-fields 没点 original_desc 时仍走默认覆盖，按默认覆盖计数。
    """
    explicit_original = merger.overwrite_all or (
        merger.overwrite_field_list is not None and "original_desc" in merger.overwrite_field_set
    )
    if (not explicit_original) and merger.keep_manual_desc_date:
        return {
            "title": DESC_ALIAS_TITLE,
            "note": DESC_ALIAS_NOTE,
            "count": len(remaining),
            "entries": remaining,
            "presentation": "list",
        }
    if explicit_original:
        note = DESC_ALIAS_FLAG_NOTE
        summary = f"共 {len(merger.citation_alias_overwritten)} 条。"
    else:
        note = DESC_ALIAS_DEFAULT_NOTE
        summary = f"共 {len(merger.citation_alias_overwritten)} 条已被默认覆盖。"
    return {
        "title": DESC_ALIAS_TITLE,
        "note": note,
        "count": len(merger.citation_alias_overwritten),
        "entries": [],
        "presentation": "count",
        "summary": summary,
    }


def build_report(merger: Merger, alignment: dict, still_missing: list, citation_note: str, desc_alias: list, title_source: dict, wrote_data: bool, backup_name: str | None, report_dir: Path) -> dict:
    if merger.overwrite_all:
        mode = "overwrite"
    elif merger.overwrite_field_list:
        mode = "overwrite-fields"
    else:
        mode = "fill"
    notes = [
        TEMPLATE_NOTE,
        "title / title_short 不修改。",
        DEFAULT_DESC_NOTE,
        PRIORITY_NOTE,
        "其他字段只填空（null、空字符串、空列表、「暂未抓取到」、「暂未获取」），不覆盖已有人工值。",
        WS_NOTE,
        "脚本缺失不写成 0。脚本值为 0 时，只有 field_status 对应字段 status=ok 才写入。",
        "content_type 只在人工为空时填写。脚本只有「图文 / 视频」；填成「视频」的条目需要再细分口播 / 混剪。人工已是口播或混剪时，脚本的「视频」不视为冲突，也不覆盖。",
        BACKFILL_NOTE,
        "post_desc 取 items.original_desc，且 field_status.desc 为 ok 才写。模板不读 post_desc。",
        PREV_NOTE,
        "citation_title 只取诊断包 top.json，在覆盖文案之前写入，不从脚本取值。已有值与 top.json 不同时，默认不覆盖、记冲突。",
        citation_note,
    ]
    if merger.keep_manual_desc_date and not merger.overwrite_all and not merger.overwrite_field_list:
        notes.append(KEEP_NOTE)
    if merger.both_overwrite:
        notes.append(BOTH_OVERWRITE_NOTE)
    elif merger.overwrite_field_list:
        listed = "、".join(merger.overwrite_field_list)
        if merger.keep_manual_desc_date:
            notes.append(
                "本次按 --overwrite-fields 覆盖："
                + listed
                + "。已给 --keep-manual-desc-date：未列出的发布文案和发布日期按只填空，差异记入冲突（未覆盖）。其他字段只填空。"
            )
        else:
            notes.append(
                "本次按 --overwrite-fields 覆盖："
                + listed
                + "。未列出的发布文案和发布日期仍按默认覆盖。其他字段只填空。"
            )
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": mode,
        "dry_run": merger.dry_run,
        "wrote_data": wrote_data,
        "backup": backup_name,
        "params": {
            "package": str(merger.package),
            "fetch": str(merger.fetch),
            "data": str(merger.data_path),
            "images_dir": str(merger.images_dir),
            "shots_dir": str(merger.shots_dir),
            "shots_video": merger.shots_video,
            "report_dir": str(report_dir),
            "dry_run": merger.dry_run,
            "overwrite": merger.overwrite_all,
            "overwrite_fields": merger.overwrite_field_list,
            "keep_manual_desc_date": merger.keep_manual_desc_date,
            "ranks": sorted(merger.args.ranks) if merger.args.ranks else None,
        },
        "notes": notes,
        "alignment": alignment,
        "field_stats": merger.field_stats,
        "keep_manual_desc_date": merger.keep_manual_desc_date,
        "desc_date_overwritten": merger.desc_date_overwritten,
        "desc_date_stats": desc_date_stats_of(merger),
        "original_desc_prev_saved": merger.original_desc_prev_saved,
        "title_source": title_source,
        "transcript_status_backfill": {
            "count": len(merger.backfill_ids),
            "video_ids": merger.backfill_ids,
            "note": BACKFILL_NOTE,
        },
        "filled": merger.filled,
        "overwritten": merger.overwritten,
        "conflicts": merger.conflicts,
        "original_desc_is_citation_title": alias_report(merger, desc_alias),
        "image_supplements": merger.image_supplements,
        "zeros_written": merger.zeros_written,
        "file_ops": merger.file_ops,
        "videos_not_copied": merger.videos_not_copied,
        "still_missing": still_missing,
        "content_type_notes": merger.content_type_notes,
    }


def mode_label(report: dict) -> str:
    mode = report["mode"]
    dry = report["dry_run"]
    fields = "、".join(report["params"].get("overwrite_fields") or [])
    if mode == "overwrite":
        if dry:
            return "dry-run + overwrite（未写盘）"
        return "overwrite（脚本可靠值覆盖人工值）"
    if mode == "overwrite-fields":
        if report.get("keep_manual_desc_date"):
            tail = "未列出的文案和日期只填空"
        else:
            tail = "未列出的文案和日期仍默认覆盖"
        if dry:
            return f"dry-run + overwrite-fields（未写盘，覆盖 {fields}；{tail}）"
        return f"overwrite-fields（覆盖 {fields}；{tail}）"
    if report.get("keep_manual_desc_date"):
        if dry:
            return "dry-run + keep-manual-desc-date（未写盘，文案和日期也只填空）"
        return "keep-manual-desc-date（文案和日期也只填空）"
    if dry:
        return "dry-run（未写盘，默认覆盖文案和日期）"
    return "默认覆盖文案和日期，其他只填空"


def render_desc_date_section(report: dict) -> list:
    stats = report.get("desc_date_stats") or {}
    ws = stats.get("whitespace_unchanged", 0)
    lines = ["", "## 默认覆盖：发布文案 / 日期（旧值 → 新值）", ""]
    mode = report.get("mode")
    keep = bool(report.get("keep_manual_desc_date"))
    if mode == "overwrite":
        lines.append("本次使用 --overwrite，发布文案和日期随可写字段覆盖，见「覆盖（旧值 → 新值）」。默认覆盖未单独计。")
    elif mode == "overwrite-fields" and keep:
        lines.append("已给 --keep-manual-desc-date：未列出的发布文案和发布日期按只填空，差异记在「冲突（未覆盖）」。列出的字段见「覆盖（旧值 → 新值）」。")
    elif mode == "overwrite-fields":
        lines.append("未列出的发布文案和发布日期仍按默认覆盖。列出的字段见「覆盖（旧值 → 新值）」，不记入下面的条数。")
        parts = "、".join(f"{name} {stats.get(name, 0)}" for name in DESC_DATE_FIELDS)
        lines.append(f"各字段覆盖条数：{parts}。")
        rows = report.get("desc_date_overwritten") or []
        if not rows:
            lines.append("无")
        else:
            for row in rows:
                extra = f"（{row['note']}）" if row.get("note") else ""
                lines.append(
                    f"- rank {row['rank']} video_id {row['video_id']} {row['field']}：{show(row['old'])} → {show(row['new'])}{extra}"
                )
    elif keep:
        lines.append("已关闭，按只填空。这些差异记在「冲突（未覆盖）」。")
    else:
        parts = "、".join(f"{name} {stats.get(name, 0)}" for name in DESC_DATE_FIELDS)
        lines.append(f"各字段覆盖条数：{parts}。")
        rows = report.get("desc_date_overwritten") or []
        if not rows:
            lines.append("无")
        else:
            for row in rows:
                extra = f"（{row['note']}）" if row.get("note") else ""
                lines.append(
                    f"- rank {row['rank']} video_id {row['video_id']} {row['field']}：{show(row['old'])} → {show(row['new'])}{extra}"
                )
    lines.append(f"只差空白，未改：{ws}")
    saved = report.get("original_desc_prev_saved") or []
    lines.append("")
    lines.append("存进 original_desc_prev：")
    if not saved:
        lines.append("无")
    else:
        for row in saved:
            lines.append(f"- rank {row['rank']} video_id {row['video_id']}：{show(row['value'])}")
    return lines


def render_markdown(report: dict) -> str:
    params = report["params"]
    mode_text = mode_label(report)
    ranks = "全部" if not params["ranks"] else ",".join(str(rank) for rank in params["ranks"])
    lines = [
        "# merge_fetch 合并报告",
        "",
        f"- 模式：{mode_text}",
        f"- 时间：{report['generated_at']}",
        f"- package：{params['package']}",
        f"- fetch：{params['fetch']}",
        f"- data：{params['data']}",
        f"- images-dir：{params['images_dir']}",
        f"- shots-dir：{params['shots_dir']}",
        f"- shots-video：{'是' if params.get('shots_video') else '否'}",
        f"- keep-manual-desc-date：{'是' if params.get('keep_manual_desc_date') else '否'}",
        f"- report-dir：{params['report_dir']}",
        f"- ranks：{ranks}",
    ]
    if params.get("overwrite_fields"):
        shown = "、".join(params["overwrite_fields"])
        if report["mode"] == "overwrite":
            shown += "（同时给出 --overwrite，以全部字段为准）"
        lines.append(f"- overwrite-fields：{shown}")
    lines += [
        f"- 写入 data.json：{'是' if report['wrote_data'] else '否'}",
        f"- 备份：{report['backup'] or '无'}",
        "",
        "## 说明",
        "",
    ]
    for note in report["notes"]:
        lines.append(f"- {note}")
    alignment = report["alignment"]
    lines += [
        "",
        "## 对齐",
        "",
        f"- matched：{len(alignment['matched'])}",
    ]
    for row in alignment["matched"]:
        lines.append(f"  - rank {row['data_rank']} video_id {row['video_id']}（fetch rank {row['fetch_rank']}，status {row['fetch_status']}）")
    lines.append(f"- rank 不一致：{len(alignment['rank_mismatch'])}")
    for row in alignment["rank_mismatch"]:
        lines.append(f"  - video_id {row['video_id']}：data rank {row['data_rank']} / fetch rank {row['fetch_rank']}")
    lines.append(f"- 仅 data：{len(alignment['only_data'])}")
    for row in alignment["only_data"]:
        lines.append(f"  - rank {row['rank']} video_id {row['video_id']}")
    lines.append(f"- 仅 fetch：{len(alignment['only_fetch'])}")
    for row in alignment["only_fetch"]:
        lines.append(f"  - rank {row['rank']} video_id {row['video_id']}（status {row['status']}）")
    lines += ["", "## 字段统计", "", "| 字段 | 填空 | 默认覆盖 | --overwrite 覆盖 |", "|---|---:|---:|---:|"]
    any_stat = False
    for name, counts in report["field_stats"].items():
        filled = counts.get("filled", 0)
        default_over = counts.get("default_overwritten", 0)
        flag_over = counts.get("overwritten", 0)
        if filled or default_over or flag_over:
            any_stat = True
            lines.append(f"| {name} | {filled} | {default_over} | {flag_over} |")
    if not any_stat:
        lines.append("| （无） | 0 | 0 | 0 |")
    lines += render_desc_date_section(report)
    backfill = report["transcript_status_backfill"]
    lines += [
        "",
        "## transcript_status 补齐",
        "",
        f"补了 {backfill['count']} 行：人工已有 transcript 但没有 transcript_status，补成 pending。{backfill['note']}。",
        "",
        "## 填入的字段",
        "",
    ]
    fills = report["filled"]
    if not fills:
        lines.append("无")
    else:
        grouped = {}
        for row in fills:
            grouped.setdefault((row["rank"], row["video_id"]), []).append(row)
        for (rank, vid), rows in grouped.items():
            body = "；".join(f"{row['field']}={show(row['value'])}" for row in rows)
            lines.append(f"- rank {rank} video_id {vid}：{body}")
    notes = report.get("content_type_notes") or []
    if notes:
        lines += ["", "content_type 填了「视频」的条目（需人工细分口播/混剪）："]
        for row in notes:
            lines.append(f"- rank {row['rank']} video_id {row['video_id']}：{row['note']}")
    lines += ["", "## 覆盖（旧值 → 新值）", ""]
    if not report["overwritten"]:
        lines.append("无")
    else:
        for row in report["overwritten"]:
            extra = f"（{row['note']}）" if row.get("note") else ""
            lines.append(f"- rank {row['rank']} video_id {row['video_id']} {row['field']}：{show(row['old'])} → {show(row['new'])}{extra}")
    lines += ["", "## 冲突（未覆盖）", ""]
    if not report["conflicts"]:
        lines.append("无")
    else:
        for row in report["conflicts"]:
            mark = "（人工 0 可疑）" if row.get("suspect_zero") else ""
            extra = f"（{row['note']}）" if row.get("note") else ""
            lines.append(
                f"- rank {row['rank']} video_id {row['video_id']} {row['field']}：人工 {show(row['manual'])} / 脚本 {show(row['script'])}{mark}{extra}"
            )
    alias = report["original_desc_is_citation_title"]
    lines += ["", f"## {alias['title']}", "", alias["note"], ""]
    if alias.get("presentation") == "count":
        lines.append(alias.get("summary") or f"共 {alias['count']} 条。")
    elif not alias["entries"]:
        lines.append("无")
    else:
        lines.append(f"共 {alias['count']} 条。original_desc 与 citation_title 相同，post_desc 与之不同。")
        for row in alias["entries"]:
            left = row["original_desc"].replace("\r\n", "\n").replace("\n", "\\n")
            right = row["post_desc"].replace("\r\n", "\n").replace("\n", "\\n")
            lines.append(
                f"- rank {row['rank']} video_id {row['video_id']}："
                f"original_desc「{left}」 / post_desc「{right}」"
            )
    src = report.get("title_source") or {}
    lines += ["", "## title 来源", "", (src.get("note") or "title 本轮不改") + "。", ""]
    lines.append(
        f"「{src.get('label_citation', '诊断包引用标题')}」{src.get('citation_title_count', 0)} 条"
        "（title、citation_title 先做空白归一；title 去掉末尾「…」或「...」后，非空且是 citation_title 的前缀，含完全相等。"
        "占位「（无短标题）」和空标题算其他来源）。"
    )
    lines.append(f"「{src.get('label_other', '其他来源')}」{src.get('other_count', 0)} 条。")
    other_ranks = src.get("other_ranks") or []
    if other_ranks:
        lines.append("其他来源 rank：" + "、".join(str(rank) for rank in other_ranks))
    else:
        lines.append("其他来源 rank：无")
    lines += ["", "## 可补图（未改）", ""]
    supplements = [row for row in report["image_supplements"] if not row.get("applied")]
    partials = [row for row in report["image_supplements"] if row.get("applied")]
    if not supplements:
        lines.append("无")
    else:
        for row in supplements:
            lines.append(
                f"- rank {row['rank']} video_id {row['video_id']}：人工 {row['manual_count']} 张 / 脚本 {row['script_count']} 张，可补图（未改）"
            )
    if partials:
        lines.append("")
        lines.append("部分放入：")
        for row in partials:
            lines.append(f"- rank {row['rank']} video_id {row['video_id']}：{row['note']}")
    lines += ["", "## 写入的 0", ""]
    if not report["zeros_written"]:
        lines.append("无")
    else:
        for row in report["zeros_written"]:
            lines.append(
                f"- rank {row['rank']} video_id {row['video_id']} {row['field']}=0"
                f"（field_status.{row['status_key']} status={row['field_status']}，{row['reason'] or '无 reason'}）"
            )
    lines += ["", "## 文件", ""]
    videos = report.get("videos_not_copied") or []
    present_videos = [row for row in videos if row.get("exists")]
    absent_videos = [row for row in videos if not row.get("exists")]
    if not report["file_ops"] and not videos:
        lines.append("无")
    else:
        if report["file_ops"]:
            counts = {}
            for row in report["file_ops"]:
                counts[row["action"]] = counts.get(row["action"], 0) + 1
            summary = "，".join(f"{key} {counts[key]}" for key in ("copied", "would_copy", "same", "diff", "missing") if counts.get(key))
            lines.append(summary or "无")
            for row in report["file_ops"]:
                if row["action"] == "diff":
                    lines.append(f"- 同名文件内容不同，未覆盖：{row['where']}/{row['dest']}（来源 {row['src']}）")
                elif row["action"] == "missing":
                    lines.append(f"- 来源缺失：{row['where']}/{row['dest']}（来源 {row['src']}）")
        if present_videos:
            lines.append(f"视频未复制 {len(present_videos)} 个：{VIDEO_SKIP_NOTE}")
            for row in present_videos:
                lines.append(f"- rank {row['rank']} video_id {row['video_id']}：{row['src']}")
        if absent_videos:
            lines.append("视频未复制，且 fetch 输出目录里找不到来源文件：")
            for row in absent_videos:
                lines.append(f"- rank {row['rank']} video_id {row['video_id']}：{row['src']}")
    lines += ["", "## 仍缺失需走兜底", ""]
    if not report["still_missing"]:
        lines.append("无")
    else:
        for row in report["still_missing"]:
            lines.append(f"- rank {row['rank']} video_id {row['video_id']}（fetch status {row['fetch_status']}）")
            for field in row["fields"]:
                lines.append(
                    f"  - {field['field']}：field_status={field['field_status']}，{field['reason']}"
                )
    lines.append("")
    return "\n".join(lines)


def backup_path(data_path: Path, stamp: str) -> Path:
    candidate = data_path.parent / f"{data_path.name}.bak-merge-{stamp}"
    if not candidate.exists():
        return candidate
    index = 2
    while True:
        nxt = data_path.parent / f"{data_path.name}.bak-merge-{stamp}-{index}"
        if not nxt.exists():
            return nxt
        index += 1


def write_data(data_path: Path, obj, raw: bytes, text: str) -> tuple[bool, str | None]:
    suffix_len = len(text) - len(text.rstrip("\n"))
    new_text = json.dumps(obj, ensure_ascii=False, indent=2) + ("\n" * suffix_len)
    if new_text == text:
        return False, None
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    backup = backup_path(data_path, stamp)
    backup.write_bytes(raw)
    tmp = data_path.with_name(data_path.name + ".tmp-merge")
    try:
        tmp.write_text(new_text, encoding="utf-8")
        os.replace(tmp, data_path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return True, backup.name


def write_reports(report_dir: Path, report: dict, markdown: str) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    md_path = report_dir / f"merge-report-{stamp}.md"
    json_path = report_dir / f"merge-report-{stamp}.json"
    if md_path.exists() or json_path.exists():
        stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        md_path = report_dir / f"merge-report-{stamp}.md"
        json_path = report_dir / f"merge-report-{stamp}.json"
    md_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def merge(args) -> dict:
    package = Path(args.package).expanduser()
    fetch = Path(args.fetch).expanduser()
    if not package.is_absolute():
        package = Path.cwd() / package
    if not fetch.is_absolute():
        fetch = Path.cwd() / fetch
    if not package.is_dir():
        die(f"分析包不是目录：{package}")
    if not fetch.is_dir():
        die(f"fetch 输出不是目录：{fetch}")
    data_path = under(package, args.data)
    images_dir = under(package, args.images_dir)
    shots_dir = under(package, args.shots_dir)
    report_dir = under(package, args.report_dir) if args.report_dir else package / "work" / "merge_fetch"
    obj, raw, text = load_json(data_path)
    rows, _container = split_rows(obj)
    for row in rows:
        if not isinstance(row, dict):
            die("data 列表里有非对象行")
    items = load_items(fetch)
    status_by_id = load_field_status(fetch)
    citation_titles = load_citation_titles(package)
    if citation_titles is None:
        citation_note = "未找到 _机器可读/top.json，未写 citation_title"
    elif not citation_titles:
        citation_note = "top.json 里没有可用的 videos[].title，未写 citation_title"
    else:
        citation_note = "citation_title 取自 _机器可读/top.json 同 video_id 的 title"

    fetch_by_id = {}
    for item in items:
        fetch_by_id.setdefault(video_id_of(item), []).append(item)
    ranks = args.ranks
    considered = []
    for row in rows:
        rank = as_rank(row.get("rank"))
        if ranks is not None and rank not in ranks:
            continue
        considered.append(row)
    considered_ids = {video_id_of(row) for row in considered if video_id_of(row)}
    all_ids = {video_id_of(row) for row in rows if video_id_of(row)}

    merger = Merger(args, package, fetch, data_path, images_dir, shots_dir)
    matched = []
    rank_mismatch = []
    only_data = []
    used_fetch = set()

    for row in considered:
        vid = video_id_of(row)
        # citation_title 先写好，后面覆盖 original_desc 时才能判断旧文案是不是诊断包标题。
        merger.apply_citation(row, citation_titles)
        if not vid:
            only_data.append({"rank": as_rank(row.get("rank")), "video_id": "", "reason": "缺少 video_id"})
            merger.backfill_transcript_status(row)
            continue
        item = pick_fetch(fetch_by_id.get(vid, []), row)
        if item is None:
            only_data.append({"rank": as_rank(row.get("rank")), "video_id": vid})
            merger.backfill_transcript_status(row)
            continue
        used_fetch.add(id(item))
        data_rank = as_rank(row.get("rank"))
        fetch_rank = as_rank(item.get("rank"))
        fetch_status = item.get("status")
        matched.append({
            "video_id": vid,
            "data_rank": data_rank,
            "fetch_rank": fetch_rank,
            "fetch_status": fetch_status,
        })
        if data_rank is not None and fetch_rank is not None and data_rank != fetch_rank:
            rank_mismatch.append({
                "video_id": vid,
                "data_rank": data_rank,
                "fetch_rank": fetch_rank,
            })
        # blocked / missing：不写任何脚本值。citation_title 与 transcript_status 补齐不来自抓取字段。
        if fetch_status not in ("blocked", "missing"):
            fields_row = status_by_id.get(vid)
            fields = fields_row.get("fields") if isinstance(fields_row, dict) else None
            if fetch_status in ("ok", "partial") and isinstance(fields, dict):
                merger.apply_fetch(row, item, fields)
            # 其他状态或缺少 field_status：不确定，不写脚本值。
        merger.backfill_transcript_status(row)

    only_fetch = []
    for item in items:
        if id(item) in used_fetch:
            continue
        rank = as_rank(item.get("rank"))
        if ranks is not None and rank not in ranks:
            continue
        vid = video_id_of(item)
        if vid and vid in all_ids and vid not in considered_ids:
            continue
        if vid and vid in considered_ids:
            continue
        only_fetch.append({
            "rank": rank,
            "video_id": vid,
            "status": item.get("status"),
        })

    still_missing = []
    for row in considered:
        vid = video_id_of(row)
        item = pick_fetch(fetch_by_id.get(vid, []), row) if vid else None
        fields_row = status_by_id.get(vid) if vid else None
        fields = fields_row.get("fields") if isinstance(fields_row, dict) else None
        status = item.get("status") if isinstance(item, dict) else None
        gap = still_missing_for(row, item if isinstance(item, dict) else None, fields if isinstance(fields, dict) else None, status)
        if gap:
            still_missing.append(gap)

    alignment = {
        "matched": matched,
        "rank_mismatch": rank_mismatch,
        "only_data": only_data,
        "only_fetch": only_fetch,
    }
    wrote_data = False
    backup_name = None
    if not merger.dry_run:
        wrote_data, backup_name = write_data(data_path, obj, raw, text)
    desc_alias = citation_title_desc_entries(considered)
    title_source = summarize_title_source(considered)
    report = build_report(
        merger, alignment, still_missing, citation_note, desc_alias, title_source, wrote_data, backup_name, report_dir
    )
    markdown = render_markdown(report)
    print(markdown, end="" if markdown.endswith("\n") else "\n")
    if not merger.dry_run:
        write_reports(report_dir, report, markdown)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="把 douyin_fetch.py 的产出合并进分析包 data.json。默认用抖音原文覆盖发布文案和发布日期（field_status=ok），其他字段只填空。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "默认覆盖 original_desc、post_desc、post_title、post_title_source、publish_date。"
            "可靠才覆盖：对应 field_status=ok，值非空；publish_date 还必须是 YYYY-MM-DD。"
            "抓不到、null 或非 ok 时保留旧值。其他字段只填空。\n"
            "优先级：--overwrite > --overwrite-fields > 默认文案日期覆盖（除非 --keep-manual-desc-date）> 只填空。\n"
            "citation_title 只取诊断包 top.json，不从脚本取值。title / title_short 不改。\n"
            "content_type 只在人工为空时填，不能覆盖。"
        ),
    )
    parser.add_argument("--package", required=True, help="分析包目录")
    parser.add_argument("--fetch", required=True, help="douyin_fetch.py 的输出目录（含 items.json、field_status.json、media/）")
    parser.add_argument("--data", default="gallery/data.json", help="相对分析包的 data.json 路径，默认 gallery/data.json")
    parser.add_argument("--images-dir", default="gallery/images", help="相对分析包的图片目录，默认 gallery/images")
    parser.add_argument("--shots-dir", default="shots", help="相对分析包的 shots 目录，默认 shots")
    parser.add_argument(
        "--shots-video",
        action="store_true",
        help="把 mp4 / m4a 也复制进 shots-dir。默认不复制，文件留在 fetch 输出目录",
    )
    parser.add_argument("--report-dir", default=None, help="报告目录，默认 <分析包>/work/merge_fetch")
    parser.add_argument("--dry-run", action="store_true", help="只打印差异摘要，不备份、不复制、不写 data.json、不写报告")
    parser.add_argument("--overwrite", action="store_true", help="脚本值可靠时覆盖全部可写字段（content_type 除外），并在报告里列出旧值 → 新值。优先于默认文案日期覆盖和 --keep-manual-desc-date")
    parser.add_argument(
        "--overwrite-fields",
        type=parse_overwrite_fields,
        default=None,
        help="覆盖列出的 data 字段，逗号分隔，例如 original_desc。未知字段报错。content_type 不支持覆盖。与默认文案日期覆盖叠加：未列出的发布文案和发布日期仍按默认覆盖，除非同时给了 --keep-manual-desc-date。与 --overwrite 同时给出时以 --overwrite 为准",
    )
    parser.add_argument(
        "--keep-manual-desc-date",
        action="store_true",
        help="发布文案和发布日期也只填空，不用抖音原文覆盖。--overwrite 和 --overwrite-fields 仍优先",
    )
    parser.add_argument("--ranks", type=parse_ranks, default=None, help="只处理这些 data rank，例如 1,2,5")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    merge(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
