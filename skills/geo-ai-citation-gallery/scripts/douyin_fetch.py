#!/usr/bin/env python3
"""无头、只读抓取抖音公开作品页。

从 jingxuan / note / video 的服务端 HTML 读取 SSR RSC（self.__pace_f）。
不登录、不带 cookie、不点击、不处理验证码。分析包只读，结果只写 --out。

用法（在技能根目录，即本文件所在 scripts/ 的上一级）:
  python3 scripts/douyin_fetch.py --package <分析包> --out <输出目录> [--limit N]

常用参数:
  --ranks 1,2,5          只抓这些 rank
  --no-asr / --no-video  跳过转写 / 跳过视频下载与抽帧
  --asr-model small      模型名或本地目录；也可用环境变量 GEO_ASR_MODEL
  --asr-allow-download   缓存没有模型时才联网下载（默认只离线加载）
  --frames 4 --sleep 4-8 --retries 2
  --video-quality lowest|highest
  --force --headed
  --chrome PATH          也可用环境变量 GEO_CHROME
  --whisper-python PATH  也可用环境变量 GEO_WHISPER_PYTHON

依赖:
  playwright，以及 Chrome / Chromium（或 Playwright 自带 chromium）
  Pillow
  ffmpeg、ffprobe
可选:
  faster-whisper                 pip install faster-whisper
  opencc-python-reimplemented    pip install opencc-python-reimplemented
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SH = ZoneInfo("Asia/Shanghai")
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
ASR_WORKER = Path(__file__).resolve().parent / "asr_worker.py"
CHROME_CANDIDATES = (
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)
ASR_MISSING_REASON = (
    "未找到 faster-whisper：pip install faster-whisper，或用 --whisper-python / GEO_WHISPER_PYTHON 指定"
)


def resolve_chrome(explicit: str | None) -> str | None:
    """Chrome/Chromium binary, or None so Playwright uses its own chromium.

    --chrome wins, then GEO_CHROME. An explicit path must exist. With neither
    set, probe the usual locations; if none exist, return None.
    """
    if explicit and explicit.strip():
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise SystemExit(f"--chrome 不存在或不是文件: {explicit}")
        return str(path)
    env = os.environ.get("GEO_CHROME", "").strip()
    if env:
        path = Path(env).expanduser()
        if not path.is_file():
            raise SystemExit(f"GEO_CHROME 不存在或不是文件: {env}")
        return str(path)
    for candidate in CHROME_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    return None


def interpreter_has_faster_whisper(python: str) -> bool:
    try:
        proc = subprocess.run(
            [python, "-c", "import faster_whisper"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def resolve_whisper_python(explicit: str | None) -> str | None:
    """Interpreter that can import faster_whisper, or None.

    --whisper-python, else GEO_WHISPER_PYTHON, else this process. An explicit
    interpreter that cannot import the package is not replaced by another one.
    """
    if explicit and explicit.strip():
        candidate = explicit.strip()
    else:
        env = os.environ.get("GEO_WHISPER_PYTHON", "").strip()
        candidate = env or sys.executable
    if interpreter_has_faster_whisper(candidate):
        return candidate
    return None


ROUTES = (
    ("jingxuan", "https://www.douyin.com/jingxuan?modal_id={vid}"),
    ("note", "https://www.douyin.com/note/{vid}"),
    ("video", "https://www.douyin.com/video/{vid}"),
)

CAPTCHA_URL = "verify.zijieapi.com/captcha/get"
LOGIN_PANEL_PHRASES = ("验证码登录", "请输入验证码", "获取验证码")

FIELD_NAMES = (
    "title",
    "desc",
    "hashtags",
    "account",
    "follower_count",
    "digg_count",
    "collect_count",
    "share_count",
    "comment_count",
    "play_count",
    "content_type",
    "duration_sec",
    "publish_time",
    "cover",
    "images",
    "video_file",
    "frames",
    "transcript",
)

ITEM_DEFAULTS = {
    "rank": None,
    "video_id": None,
    "url": None,
    "page_url": None,
    "route": None,
    "title": None,
    "title_source": None,
    "title_short": None,
    "original_desc": None,
    "caption": None,
    "hashtags": None,
    "hashtags_raw_from_desc": None,
    "hashtags_from_textExtra": None,
    "account": None,
    "account_name": None,
    "author_uid": None,
    "author_sec_uid": None,
    "follower_count": None,
    "author_total_favorited": None,
    "digg_count": None,
    "collect_count": None,
    "share_count": None,
    "comment_count": None,
    "play_count": None,
    "content_type": None,
    "aweme_type": None,
    "media_type": None,
    "duration_sec": None,
    "media_duration_sec": None,
    "music_title": None,
    "music_duration_sec": None,
    "image_count": None,
    "images": None,
    "image_urls": None,
    "cover": None,
    "cover_url": None,
    "cover_size": None,
    "video_file": None,
    "audio_file": None,
    "frames": None,
    "publish_time": None,
    "publish_date": None,
    "platform_tags": None,
    "transcript": None,
    "transcript_status": None,
    "fetched_at": None,
    "elapsed_sec": None,
    "status": None,
    "error": None,
}


class Log:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.fh = path.open("a", encoding="utf-8")

    def info(self, msg: str) -> None:
        line = f"{datetime.now(SH).isoformat(timespec='seconds')} {scrub(msg)}"
        self.fh.write(line + "\n")
        self.fh.flush()
        print(line, flush=True)

    def close(self) -> None:
        self.fh.close()


def url_for_log(url: str) -> str:
    """Keep short page URLs. Drop the query on long signed CDN URLs."""
    url = str(url)
    lower = url.lower()
    signed = "x-signature" in lower or "x-expires" in lower or "token=" in lower
    if len(url) <= 120 and not signed:
        return url
    try:
        parts = urllib.parse.urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}{parts.path}"
    except Exception:
        base = url.split("?")[0]
    return base if len(base) <= 120 else base[:117] + "..."


def scrub(msg: str) -> str:
    text = str(msg)
    text = re.sub(r"(?i)(cookie|token|authorization)\s*[:=]\s*\S+", r"\1=<redacted>", text)

    def cut(match: re.Match) -> str:
        return url_for_log(match.group(0))

    return re.sub(r"https?://\S+", cut, text)


def now_iso() -> str:
    return datetime.now(SH).isoformat(timespec="seconds")


def dump_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def write_jsonl(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def relpath(out: Path, path: Path) -> str:
    return path.resolve().relative_to(out.resolve()).as_posix()


def clean_str(value):
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    if value in ("", "$undefined", "undefined", "null"):
        return None
    return value


def as_int(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value:  # NaN
            return None
        return int(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if text in ("", "$undefined", "undefined"):
            return None
        try:
            return int(float(text)) if "." in text else int(text)
        except ValueError:
            return None
    return None


def as_float(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value != value:
            return None
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if text in ("", "$undefined", "undefined"):
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


# --- RSC parse (same approach as out/probe/rsc_reference.py) ---

def iter_payloads(html: str):
    for pushed in re.findall(r"self\.__pace_f\.push\((\[.*?\])\)</script>", html, re.S):
        try:
            arr = json.loads(pushed)
            payload = arr[1]
        except (json.JSONDecodeError, IndexError, TypeError, KeyError):
            continue
        if not isinstance(payload, str):
            continue
        if payload.startswith("%7B"):
            try:
                yield json.loads(urllib.parse.unquote(payload))
            except (json.JSONDecodeError, ValueError):
                pass
            continue
        for line in payload.split("\n"):
            matched = re.match(r"^([0-9a-f]+):(.*)$", line, re.S)
            if not matched:
                continue
            body = matched.group(2)
            if body[:1] in "[{":
                try:
                    yield json.loads(body)
                except json.JSONDecodeError:
                    pass
    rendered = re.search(r'<script id="RENDER_DATA"[^>]*>(.*?)</script>', html, re.S)
    if rendered:
        try:
            yield json.loads(urllib.parse.unquote(rendered.group(1)))
        except (json.JSONDecodeError, ValueError):
            pass


def find_aweme(obj, vid: str):
    best = None
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if str(cur.get("awemeId")) == vid and ("stats" in cur or "video" in cur):
                if best is None or len(cur) > len(best):
                    best = cur
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return best


def extract_detail(html: str, vid: str):
    if not html:
        return None
    best = None
    for payload in iter_payloads(html):
        found = find_aweme(payload, vid)
        if found is not None and (best is None or len(found) > len(best)):
            best = found
    return best


def parse_docs(docs: list, vid: str):
    best = None
    best_len = -1
    for _url, _status, body in docs:
        if not body:
            continue
        html = body.decode("utf-8", "ignore") if isinstance(body, (bytes, bytearray)) else str(body)
        found = extract_detail(html, vid)
        if found is not None and len(found) > best_len:
            best = found
            best_len = len(found)
    return best


# --- package input (read-only) ---

def load_package(package: Path):
    gallery = package / "gallery" / "data.json"
    top = package / "_机器可读" / "top.json"
    if gallery.is_file():
        data = json.loads(gallery.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            rows = data["data"]
        elif isinstance(data, list):
            rows = data
        else:
            raise SystemExit(f"无法识别 {gallery} 的结构")
        source = "gallery/data.json"
    elif top.is_file():
        data = json.loads(top.read_text(encoding="utf-8"))
        rows = data.get("videos") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise SystemExit(f"{top} 没有 videos 列表")
        source = "_机器可读/top.json"
    else:
        raise SystemExit("分析包里没有 gallery/data.json，也没有 _机器可读/top.json")

    items = []
    for row in rows:
        if not isinstance(row, dict) or row.get("rank") is None:
            continue
        vid = row.get("video_id")
        vid = "" if vid is None else str(vid).strip()
        url = row.get("url") or ""
        if not isinstance(url, str):
            url = str(url)
        if not vid:
            matched = re.search(r"(\d{15,22})", url)
            if matched:
                vid = matched.group(1)
        items.append({"rank": int(row["rank"]), "video_id": vid, "url": url})
    items.sort(key=lambda row: row["rank"])
    return items, source


def parse_sleep(text: str) -> tuple[float, float]:
    matched = re.fullmatch(r"(\d+(?:\.\d+)?)(?:-(\d+(?:\.\d+)?))?", text.strip())
    if not matched:
        raise argparse.ArgumentTypeError("sleep 应为 4-8 或单个秒数")
    lo = float(matched.group(1))
    hi = float(matched.group(2)) if matched.group(2) else lo
    if hi < lo:
        lo, hi = hi, lo
    return lo, hi


def parse_ranks(text: str) -> set[int]:
    ranks = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        ranks.add(int(part))
    if not ranks:
        raise argparse.ArgumentTypeError("ranks 为空")
    return ranks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="无头只读抓取抖音公开作品（SSR RSC）。不登录、不加载 cookie、不处理验证码。"
    )
    parser.add_argument("--package", required=True, help="分析包目录（只读）")
    parser.add_argument("--out", required=True, help="输出目录（只写这里）")
    parser.add_argument("--limit", type=int, default=None, help="按 rank 排序后取前 N 条")
    parser.add_argument("--ranks", type=parse_ranks, default=None, help="只抓这些 rank，如 1,2,5")
    parser.add_argument("--no-asr", action="store_true", help="不跑语音转写")
    parser.add_argument("--no-video", action="store_true", help="不下载视频、音频、抽帧")
    parser.add_argument(
        "--asr-model",
        default=os.environ.get("GEO_ASR_MODEL", "small"),
        help="faster-whisper 模型名或本地模型目录。也可用环境变量 GEO_ASR_MODEL。默认 small",
    )
    parser.add_argument(
        "--asr-allow-download",
        action="store_true",
        help="本地缓存没有 ASR 模型时允许联网下载。默认只离线加载",
    )
    parser.add_argument("--frames", type=int, default=4, help="视频抽帧数，默认 4")
    parser.add_argument("--sleep", type=parse_sleep, default=(4.0, 8.0), help="条目间隔秒数，默认 4-8")
    parser.add_argument("--retries", type=int, default=2, help="每个路由失败后的额外重试次数，默认 2")
    parser.add_argument("--video-quality", choices=("lowest", "highest"), default="lowest", help="h264 mp4 档位，默认 lowest")
    parser.add_argument("--force", action="store_true", help="忽略已完成状态，重新打开页面并覆盖")
    parser.add_argument("--headed", action="store_true", help="有头 Chrome（仍不点击、不登录）")
    parser.add_argument(
        "--chrome",
        default=None,
        help=(
            "Chrome/Chromium 可执行文件。也可用环境变量 GEO_CHROME。"
            "默认依次探测 /usr/bin/google-chrome、/usr/bin/chromium、macOS Google Chrome；"
            "都没有则用 Playwright 自带 chromium"
        ),
    )
    parser.add_argument(
        "--whisper-python",
        default=None,
        help=(
            "能 import faster_whisper 的 Python。也可用环境变量 GEO_WHISPER_PYTHON。"
            "默认当前解释器；找不到则视频转写记 skipped_no_asr，不中断抓取"
        ),
    )
    return parser


# --- detail mapping ---

def content_type_of(detail: dict) -> str | None:
    aweme_type = as_int(detail.get("awemeType"))
    media_type = as_int(detail.get("mediaType"))
    if aweme_type == 68:
        return "图文"
    if aweme_type == 0:
        return "视频"
    if media_type == 2:
        return "图文"
    if media_type == 4:
        return "视频"
    images = detail.get("images")
    if isinstance(images, list) and images:
        return "图文"
    return None


def hashtag_fields(desc: str | None, text_extra) -> tuple[list | None, list | None, list | None]:
    if desc is None and not isinstance(text_extra, list):
        return None, None, None
    raw = re.findall(r"#([^#\s]+)", desc or "")
    from_extra = []
    if isinstance(text_extra, list):
        for entry in text_extra:
            if not isinstance(entry, dict):
                continue
            if as_int(entry.get("type")) != 1:
                continue
            name = clean_str(entry.get("hashtagName"))
            if name:
                from_extra.append(name)
    seen = set()
    hashtags = []
    for name in raw:
        tag = "#" + name
        if tag not in seen:
            seen.add(tag)
            hashtags.append(tag)
    return hashtags, raw, from_extra


def title_from_desc(desc: str) -> str:
    text = re.sub(r"#[^#\s]+", " ", desc)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    first = re.split(r"[。！？!?\n]", text, maxsplit=1)[0].strip()
    if not first:
        first = text
    if len(first) > 60:
        return first[:60]
    return first


def title_short_of(title: str | None) -> str | None:
    if not title:
        return None
    if len(title) <= 60:
        return title
    return title[:60] + "…"


def platform_tags_of(detail: dict) -> list:
    tags = []
    raw = detail.get("videoTag")
    if not isinstance(raw, list):
        return tags
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = clean_str(entry.get("tagName"))
        if not name:
            continue
        tags.append({"tagName": name, "level": entry.get("level")})
    return tags


def blank_item(src: dict) -> dict:
    item = dict(ITEM_DEFAULTS)
    item["rank"] = src["rank"]
    item["video_id"] = src["video_id"]
    item["url"] = src["url"]
    item["play_count"] = None
    return item


def map_detail(detail: dict, src: dict, route: str, page_url: str) -> dict:
    item = blank_item(src)
    item["page_url"] = page_url
    item["route"] = route
    item["fetched_at"] = now_iso()
    desc = detail.get("desc")
    if not isinstance(desc, str) or desc.strip() in ("", "$undefined"):
        desc_text = None
    else:
        desc_text = desc
    item["original_desc"] = desc_text
    caption = clean_str(detail.get("caption")) if isinstance(detail.get("caption"), str) else clean_str(detail.get("caption"))
    item["caption"] = caption
    item_title = clean_str(detail.get("itemTitle"))
    if item_title:
        item["title"] = item_title
        item["title_source"] = "itemTitle"
    elif desc_text:
        made = title_from_desc(desc_text)
        item["title"] = made or None
        item["title_source"] = "desc" if made else None
    item["title_short"] = title_short_of(item["title"])
    tags, raw_tags, extra_tags = hashtag_fields(desc_text, detail.get("textExtra"))
    item["hashtags"] = tags
    item["hashtags_raw_from_desc"] = raw_tags
    item["hashtags_from_textExtra"] = extra_tags

    author = detail.get("authorInfo") if isinstance(detail.get("authorInfo"), dict) else {}
    nickname = clean_str(author.get("nickname"))
    item["account"] = nickname
    item["account_name"] = nickname
    uid = author.get("uid")
    item["author_uid"] = None if uid in (None, "", "$undefined") else str(uid)
    item["author_sec_uid"] = clean_str(author.get("secUid"))
    item["follower_count"] = as_int(author.get("followerCount"))
    item["author_total_favorited"] = as_int(author.get("totalFavorited"))

    stats = detail.get("stats") if isinstance(detail.get("stats"), dict) else {}
    item["digg_count"] = as_int(stats.get("diggCount"))
    item["collect_count"] = as_int(stats.get("collectCount"))
    item["share_count"] = as_int(stats.get("shareCount"))
    item["comment_count"] = as_int(stats.get("commentCount"))
    # 公开页 playCount 恒为 0，不可信
    item["play_count"] = None

    item["aweme_type"] = as_int(detail.get("awemeType"))
    item["media_type"] = as_int(detail.get("mediaType"))
    content_type = content_type_of(detail)
    item["content_type"] = content_type
    video = detail.get("video") if isinstance(detail.get("video"), dict) else {}
    if content_type == "视频":
        duration_ms = as_float(video.get("duration"))
        item["duration_sec"] = None if duration_ms is None else round(duration_ms / 1000.0, 1)
    else:
        item["duration_sec"] = None

    music = detail.get("music") if isinstance(detail.get("music"), dict) else {}
    item["music_title"] = clean_str(music.get("title")) or clean_str(music.get("musicName"))
    music_dur = as_float(music.get("duration"))
    item["music_duration_sec"] = None if music_dur is None else round(music_dur, 3)

    images = detail.get("images") if isinstance(detail.get("images"), list) else []
    item["image_count"] = len(images) if content_type else None
    created = as_int(detail.get("createTime"))
    if created is not None and created > 0:
        published = datetime.fromtimestamp(created, SH)
        item["publish_time"] = published.isoformat()
        item["publish_date"] = published.strftime("%Y-%m-%d")
    item["platform_tags"] = platform_tags_of(detail)
    if content_type == "图文":
        item["transcript"] = None
        item["transcript_status"] = "skipped_tuwen"
        item["video_file"] = None
        item["audio_file"] = None
        item["frames"] = None
    return item


def stat_reason(value, present: bool) -> tuple[str, str]:
    if not present or value is None:
        return "missing", "字段缺失或为 $undefined"
    if value == 0:
        return "ok", "平台返回 0"
    return "ok", ""


def judge_fields(item: dict, detail_ok: bool, stage_notes: dict) -> dict:
    content_type = item.get("content_type")
    fields = {}

    def put(name, status, reason):
        fields[name] = {"status": status, "reason": reason or ""}

    if not detail_ok:
        reason = stage_notes.get("detail") or "未解析到作品 detail"
        for name in FIELD_NAMES:
            if name == "play_count":
                put(name, "missing", "未解析到作品 detail；公开页也不提供播放量")
            else:
                put(name, "missing", reason)
        return fields

    # title / desc
    if item.get("title"):
        put("title", "ok", item.get("title_source") or "")
    else:
        put("title", "missing", "itemTitle 与 desc 都为空")
    if item.get("original_desc"):
        put("desc", "ok", "")
    else:
        put("desc", "missing", "desc 为空或缺失")

    if item.get("hashtags") is None and item.get("hashtags_from_textExtra") is None:
        put("hashtags", "missing", "desc 与 textExtra 都没有")
    elif item.get("hashtags"):
        put("hashtags", "ok", "")
    elif item.get("hashtags_from_textExtra"):
        put("hashtags", "ok", "desc 无 #，textExtra 有标签")
    else:
        put("hashtags", "ok", "无标签")

    if item.get("account"):
        put("account", "ok", "")
    else:
        put("account", "missing", "authorInfo.nickname 为空")

    for key, label in (
        ("follower_count", "authorInfo.followerCount"),
        ("digg_count", "stats.diggCount"),
        ("collect_count", "stats.collectCount"),
        ("share_count", "stats.shareCount"),
        ("comment_count", "stats.commentCount"),
    ):
        status, reason = stat_reason(item.get(key), item.get(key) is not None)
        if status == "missing":
            reason = f"{label} 缺失"
        put(key, status, reason)

    put("play_count", "missing", "公开页不提供播放量")

    if content_type in ("图文", "视频"):
        put("content_type", "ok", f"awemeType={item.get('aweme_type')} mediaType={item.get('media_type')}")
    else:
        put("content_type", "missing", "awemeType/mediaType 无法判定图文或视频")

    if content_type == "图文":
        put("duration_sec", "not_applicable", "图文无视频时长；背景音乐见 music_duration_sec")
        put("video_file", "not_applicable", "图文无视频文件")
        put("frames", "not_applicable", "图文不抽帧")
        put("transcript", "not_applicable", "图文不做语音转写")
    elif content_type == "视频":
        if item.get("duration_sec") is None:
            put("duration_sec", "missing", "video.duration 缺失")
        elif item.get("duration_sec") == 0:
            put("duration_sec", "ok", "平台返回 0")
        else:
            put("duration_sec", "ok", "")
        note = stage_notes.get("video_file")
        if item.get("video_file"):
            put("video_file", "ok", note or "")
        else:
            put("video_file", "missing", note or "视频文件未下载")
        note = stage_notes.get("frames") or ""
        incomplete = note.startswith("只抽到") or note.startswith("抽帧失败")
        if note.startswith("--frames 0") or note.startswith("命令行 --no-video"):
            put("frames", "not_applicable", note)
        elif item.get("frames") and not incomplete:
            put("frames", "ok", note)
        else:
            put("frames", "missing", note or "抽帧失败或未执行")
        t_status = item.get("transcript_status")
        if t_status == "ok" and item.get("transcript"):
            put("transcript", "ok", "")
        elif t_status == "no_speech":
            put("transcript", "missing", "ASR 未识别到语音")
        elif t_status == "skipped_no_audio":
            put("transcript", "missing", "无音频，未转写")
        elif t_status == "skipped_no_asr":
            put("transcript", "missing", "未运行 ASR（--no-asr）")
        elif t_status == "fail":
            put("transcript", "missing", stage_notes.get("transcript") or "ASR 失败")
        elif t_status in (None, "", "pending"):
            # 抓取已结束、ASR 批处理还没跑。不要写成 missing，否则中途汇总看起来像失败。
            put("transcript", "pending", "等待 ASR 批处理")
        else:
            put("transcript", "missing", stage_notes.get("transcript") or "转写结果缺失")
    else:
        put("duration_sec", "missing", "内容类型未判定")
        put("video_file", "missing", "内容类型未判定")
        put("frames", "missing", "内容类型未判定")
        put("transcript", "missing", "内容类型未判定")

    if item.get("publish_time"):
        put("publish_time", "ok", "")
    else:
        put("publish_time", "missing", "createTime 缺失")

    if item.get("cover"):
        reason = ""
        size = item.get("cover_size")
        if isinstance(size, (list, tuple)) and len(size) >= 2:
            try:
                short = min(int(size[0]), int(size[1]))
            except (TypeError, ValueError):
                short = None
            if short is not None and short < 360:
                reason = "封面短边<360"
        put("cover", "ok", reason)
    else:
        put("cover", "missing", stage_notes.get("cover") or "封面未下载")

    if content_type == "视频" and not item.get("image_count"):
        put("images", "not_applicable", "视频作品无图集")
    elif item.get("images"):
        expected = item.get("image_count") or 0
        if expected and len(item["images"]) < expected:
            put("images", "missing", stage_notes.get("images") or f"只下到 {len(item['images'])}/{expected}")
        else:
            put("images", "ok", "")
    elif content_type == "图文":
        put("images", "missing", stage_notes.get("images") or "图文 images 为空或下载失败")
    else:
        put("images", "missing", stage_notes.get("images") or "无图片")

    return fields


def transcript_row_for(item: dict, model: str) -> dict | None:
    status = item.get("transcript_status")
    if status == "skipped_tuwen":
        return {
            "rank": item["rank"],
            "video_id": item["video_id"],
            "status": "skipped_tuwen",
            "duration_audio": None,
            "chars": 0,
            "text": "",
            "source": f"faster-whisper-{model}",
            "segments_file": None,
            "transcriptReviewStatus": "pending",
        }
    if status in ("ok", "no_speech", "fail", "skipped_no_audio"):
        return {
            "rank": item["rank"],
            "video_id": item["video_id"],
            "status": status,
            "duration_audio": item.get("duration_audio"),
            "chars": len(item.get("transcript") or "") if status == "ok" else 0,
            "text": item.get("transcript") or "",
            "source": f"faster-whisper-{model}",
            "segments_file": item.get("segments_file"),
            "transcriptReviewStatus": "pending",
        }
    return None


def engagement_of(item: dict, attempts: list, blocked_reason: str | None) -> dict:
    route = item.get("route")
    if item.get("status") == "blocked":
        status = "blocked"
    elif not item.get("route"):
        status = "missing"
    elif item.get("digg_count") is None and item.get("collect_count") is None:
        status = "partial"
    else:
        status = "ok"
    return {
        "rank": item["rank"],
        "video_id": item["video_id"],
        "url": item["url"],
        "status": status,
        "source": f"douyin SSR RSC via {route}" if route else "douyin SSR RSC",
        "digg_count": item.get("digg_count"),
        "collect_count": item.get("collect_count"),
        "share_count": item.get("share_count"),
        "comment_count": item.get("comment_count"),
        "follower_count": item.get("follower_count"),
        "duration_sec": item.get("duration_sec"),
        "account_name": item.get("account_name"),
        "publish_date": item.get("publish_date"),
        "content_type_hint": item.get("content_type"),
        "page_url": item.get("page_url"),
        "attempts": attempts,
        "blocked_reason": blocked_reason,
    }


def decide_item_status(item: dict, fields: dict, no_video: bool, no_asr: bool) -> str:
    if item.get("status") == "blocked":
        return "blocked"
    if not item.get("route"):
        return "missing"
    required = ["title", "desc", "account", "content_type", "publish_time", "cover"]
    content_type = item.get("content_type")
    if content_type == "图文":
        required.append("images")
    elif content_type == "视频":
        required.append("duration_sec")
        if not no_video:
            required.append("video_file")
            if item.get("frames") is not None and fields.get("frames", {}).get("status") != "not_applicable":
                required.append("frames")
            if not item.get("audio_file"):
                return "partial"
        if not no_asr:
            required.append("transcript")
    for name in required:
        meta = fields.get(name) or {}
        if meta.get("status") != "ok":
            return "partial"
    # counts: missing follower/digg does not drop the row, but the item is partial
    for name in ("digg_count", "collect_count", "share_count", "comment_count", "follower_count"):
        if (fields.get(name) or {}).get("status") == "missing":
            return "partial"
    return "ok"


# --- downloads ---

def http_read(url: str, timeout: int) -> tuple[int, str, bytes]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Referer": "https://www.douyin.com/",
            "Accept": "*/*",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        status = getattr(resp, "status", 200) or 200
        ctype = resp.headers.get("Content-Type", "") or ""
        return status, ctype, resp.read()


def looks_like_html(data: bytes) -> bool:
    head = data[:64].lstrip().lower()
    return head.startswith(b"<") or head.startswith(b"<!doctype") or head.startswith(b"{")


def is_mp4(data: bytes) -> bool:
    return b"ftyp" in data[:64]


def save_image_bytes(data: bytes, dest: Path) -> tuple[int, int]:
    from PIL import Image
    import io

    dest.parent.mkdir(parents=True, exist_ok=True)
    header = data[:16]
    is_webp = header[:4] == b"RIFF" and b"WEBP" in data[:16]
    is_jpeg = header[:2] == b"\xff\xd8"
    if is_jpeg and not is_webp:
        tmp = dest.with_suffix(".part")
        tmp.write_bytes(data)
        os.replace(tmp, dest)
    else:
        with Image.open(io.BytesIO(data)) as im:
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            elif im.mode == "L":
                im = im.convert("RGB")
            tmp = dest.with_suffix(".part")
            im.save(tmp, "JPEG", quality=90)
            os.replace(tmp, dest)
    with Image.open(dest) as im:
        return im.size


def image_size(path: Path) -> tuple[int, int] | None:
    try:
        from PIL import Image

        with Image.open(path) as im:
            return int(im.size[0]), int(im.size[1])
    except Exception:
        return None


def image_file_ok(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size <= 0:
        return False
    try:
        from PIL import Image

        with Image.open(path) as im:
            im.verify()
        return True
    except Exception:
        return False


def media_file_ok(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size <= 0:
        return False
    head = path.read_bytes()[:64]
    return b"ftyp" in head or head[:3] == b"ID3"


def prefer_urls(urls) -> list[str]:
    found = []
    if isinstance(urls, str):
        urls = [urls]
    for entry in urls or []:
        if isinstance(entry, dict):
            entry = entry.get("src") or entry.get("url")
        if isinstance(entry, str) and entry.startswith("http"):
            found.append(entry)
    seen = set()
    ordered = []
    for url in found:
        if url not in seen:
            seen.add(url)
            ordered.append(url)
    jpeg = [url for url in ordered if ".jpeg" in url.lower() or ".jpg" in url.lower()]
    rest = [url for url in ordered if url not in jpeg]
    return jpeg + rest


def download_with_retries(urls: list[str], dest: Path, kind: str, log: Log, attempts: int = 3) -> tuple[bool, str, str | None]:
    last_err = "没有可下载的 URL"
    timeout = 120 if kind == "media" else 40
    for url in urls:
        for attempt in range(1, attempts + 1):
            try:
                status, ctype, data = http_read(url, timeout)
            except Exception as exc:  # noqa: BLE001
                last_err = f"HTTP {type(exc).__name__}"
                log.info(f"download fail kind={kind} attempt={attempt} err={last_err} url={url}")
                time.sleep(min(2 * attempt, 6))
                continue
            if status != 200 or not data:
                last_err = f"HTTP {status} 空正文" if status == 200 else f"HTTP {status}"
                log.info(f"download fail kind={kind} attempt={attempt} err={last_err} url={url}")
                time.sleep(min(2 * attempt, 6))
                continue
            if "text/html" in ctype.lower() or looks_like_html(data):
                last_err = "响应像 HTML/JSON 而不是媒体"
                log.info(f"download fail kind={kind} attempt={attempt} err={last_err} url={url}")
                time.sleep(min(2 * attempt, 6))
                continue
            try:
                if kind == "image":
                    save_image_bytes(data, dest)
                    if not image_file_ok(dest):
                        raise RuntimeError("保存后无法用 Pillow 打开")
                else:
                    if not is_mp4(data) and kind == "media":
                        raise RuntimeError("没有 ftyp，不像 mp4/m4a")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    tmp = dest.with_suffix(dest.suffix + ".part")
                    tmp.write_bytes(data)
                    os.replace(tmp, dest)
            except Exception as exc:  # noqa: BLE001
                last_err = f"保存失败 {type(exc).__name__}: {exc}"
                log.info(f"download fail kind={kind} attempt={attempt} err={scrub(last_err)}")
                if dest.exists():
                    dest.unlink(missing_ok=True)
                time.sleep(min(2 * attempt, 6))
                continue
            return True, "", url
    return False, last_err, None


def cover_urls(detail: dict) -> list[str]:
    """图文封面：仍按 cover、coverUrlList、originCoverUrlList，jpeg 优先。"""
    video = detail.get("video") if isinstance(detail.get("video"), dict) else {}
    pool = []
    if video.get("cover"):
        pool.append(video.get("cover"))
    pool.extend(video.get("coverUrlList") or [])
    pool.extend(video.get("originCoverUrlList") or [])
    return prefer_urls(pool)


_COVER_NAMED_KEYS = ("originCoverUrlList", "coverUrlList", "cover", "originCover")
_COVER_SKIP_KEYS = {
    "dynamicCover",
    "bigThumbs",
    "bitRateList",
    "bitRateAudioList",
    "playAddr",
    "playAddrH265",
    "meta",
    "videoModel",
    "coverUri",
}


def _http_urls(value) -> list[str]:
    found = []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return found
    for entry in value:
        if isinstance(entry, dict):
            entry = entry.get("src") or entry.get("url")
        if not isinstance(entry, str) or not entry.startswith("http"):
            continue
        low = entry.lower()
        path = low.split("?", 1)[0]
        if "dynamic_cover" in low or "dynamiccover" in low or path.endswith(".gif"):
            continue
        found.append(entry)
    return found


def video_cover_candidates(detail: dict) -> list[str]:
    """Still cover URLs in try order. Skips dynamicCover and motion URLs."""
    video = detail.get("video") if isinstance(detail.get("video"), dict) else {}
    ordered: list[str] = []
    for key in _COVER_NAMED_KEYS:
        ordered.extend(_http_urls(video.get(key)))
    named = set(_COVER_NAMED_KEYS)
    for key, value in video.items():
        if key in named or key in _COVER_SKIP_KEYS or "dynamic" in key.lower():
            continue
        if "cover" not in key.lower():
            continue
        ordered.extend(_http_urls(value))
    seen = set()
    unique = []
    for url in ordered:
        if url in seen:
            continue
        seen.add(url)
        unique.append(url)
    return unique


def download_best_static_cover(detail: dict, dest: Path, log: Log, rank: int) -> tuple[bool, str, str | None, list | None]:
    """Try up to 4 still URLs. Keep the largest short side. Stop at short side >= 720."""
    urls = video_cover_candidates(detail)
    best = None
    last_err = "封面 URL 为空" if not urls else "封面下载失败"
    tried = 0
    temps: list[Path] = []
    try:
        for url in urls:
            if tried >= 4:
                break
            tried += 1
            tmp = dest.with_name(f"{dest.stem}.try{tried}.jpg")
            temps.append(tmp)
            ok, err, used = download_with_retries([url], tmp, "image", log)
            if not ok:
                last_err = err or "封面下载失败"
                tmp.unlink(missing_ok=True)
                continue
            size = image_size(tmp)
            if not size:
                last_err = "封面无法读取尺寸"
                tmp.unlink(missing_ok=True)
                continue
            width, height = size
            short = min(width, height)
            log.info(f"cover candidate rank={rank:02d} try={tried} size={width}x{height} short={short}")
            if best is None or short > best["short"]:
                if best is not None:
                    best["path"].unlink(missing_ok=True)
                best = {"short": short, "size": [width, height], "url": used or url, "path": tmp}
            else:
                tmp.unlink(missing_ok=True)
            if short >= 720:
                break
        if best is None:
            return False, last_err, None, None
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.unlink(missing_ok=True)
        os.replace(best["path"], dest)
        best["path"] = dest
        log.info(
            f"cover pick rank={rank:02d} size={best['size'][0]}x{best['size'][1]} "
            f"short={best['short']} tried={tried}"
        )
        return True, "", best["url"], best["size"]
    finally:
        kept = best["path"] if best else None
        for tmp in temps:
            if tmp != kept and tmp.exists():
                tmp.unlink(missing_ok=True)


def image_entries(detail: dict) -> list[list[str]]:
    images = detail.get("images") if isinstance(detail.get("images"), list) else []
    groups = []
    for image in images:
        if not isinstance(image, dict):
            groups.append([])
            continue
        groups.append(prefer_urls(image.get("urlList") or []))
    return groups


def select_video_tier(detail: dict, quality: str):
    video = detail.get("video") if isinstance(detail.get("video"), dict) else {}
    tiers = []
    for entry in video.get("bitRateList") or []:
        if not isinstance(entry, dict):
            continue
        fmt = str(entry.get("format") or entry.get("videoFormat") or "")
        if fmt != "mp4":
            continue
        if str(entry.get("isH265")) != "0":
            continue
        size = as_int(entry.get("dataSize"))
        tiers.append((size, entry))
    if not tiers:
        return None
    known = [pair for pair in tiers if pair[0] is not None]
    unknown = [pair for pair in tiers if pair[0] is None]
    known.sort(key=lambda pair: pair[0], reverse=(quality == "highest"))
    ordered = known + unknown
    return ordered[0][1] if ordered else None


def audio_urls(detail: dict) -> list[str]:
    video = detail.get("video") if isinstance(detail.get("video"), dict) else {}
    tracks = video.get("bitRateAudioList") or []
    if not tracks or not isinstance(tracks[0], dict):
        return []
    urls = prefer_urls(tracks[0].get("urlList") or [])
    direct = [url for url in urls if "/aweme/v1/play" not in url]
    dash = [url for url in urls if url not in direct]
    return direct + dash


def run_ffmpeg(args: list[str], timeout: int = 90) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)


def ffprobe_duration(path: Path) -> float | None:
    try:
        proc = run_ffmpeg(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    text = (proc.stdout or "").strip()
    try:
        value = float(text)
    except ValueError:
        return None
    if value <= 0:
        return None
    return round(value, 3)


def extract_audio(mp4: Path, dest: Path) -> tuple[bool, str]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    proc = run_ffmpeg(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4), "-vn", "-c:a", "copy", str(dest)])
    if proc.returncode == 0 and media_file_ok(dest):
        return True, "ffmpeg copy"
    if dest.exists():
        dest.unlink()
    proc = run_ffmpeg(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4), "-vn", "-c:a", "aac", "-b:a", "96k", str(dest)]
    )
    if proc.returncode == 0 and media_file_ok(dest):
        return True, "ffmpeg aac"
    err = (proc.stderr or "")[-180:]
    return False, f"ffmpeg 抽音轨失败 {err}"


def frame_times(duration: float, count: int) -> list[float]:
    if count <= 0 or duration is None or duration <= 0:
        return []
    hi = max(duration - 0.05, 0.0)
    if count == 4:
        raw = [0.5, duration / 3.0, duration * 2.0 / 3.0, max(duration - 1.5, 0.0)]
    elif count == 1:
        raw = [min(0.5, hi)]
    else:
        start = min(0.5, hi)
        end = hi
        if count == 1:
            raw = [start]
        else:
            step = (end - start) / (count - 1) if end > start else 0
            raw = [start + step * i for i in range(count)]
    times = []
    for value in raw:
        times.append(round(min(max(value, 0.0), hi), 3))
    return times


def extract_frames(mp4: Path, dest_dir: Path, rank: int, duration: float, count: int) -> tuple[list, str]:
    times = frame_times(duration, count)
    frames = []
    errors = []
    for index, stamp in enumerate(times, start=1):
        dest = dest_dir / f"{rank:02d}_f{index}.jpg"
        if image_file_ok(dest):
            frames.append({"file": None, "timestamp_sec": stamp, "path": dest})
            continue
        proc = run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-ss",
                f"{stamp:.3f}",
                "-i",
                str(mp4),
                "-frames:v",
                "1",
                str(dest),
            ]
        )
        if proc.returncode == 0 and image_file_ok(dest):
            frames.append({"file": None, "timestamp_sec": stamp, "path": dest})
        else:
            errors.append(f"f{index}@{stamp}")
            if dest.exists() and not image_file_ok(dest):
                dest.unlink(missing_ok=True)
    return frames, ("抽帧失败 " + ",".join(errors) if errors else "")


# --- browser ---

def classify_wall(texts: list[str], captcha_url: bool) -> tuple[str | None, str]:
    if captcha_url:
        return "captcha", "响应 URL 含 verify.zijieapi.com/captcha/get"
    blob = "\n".join(texts)
    if "请完成下列验证" in blob:
        return "captcha", "页面文本含「请完成下列验证」"
    if "滑动验证" in blob:
        return "captcha", "页面文本含「滑动验证」"
    stripped = blob
    for phrase in LOGIN_PANEL_PHRASES:
        stripped = stripped.replace(phrase, "")
    if "验证码" in stripped:
        return "captcha", "页面文本含「验证码」"
    if "请先登录" in blob or "登录后观看" in blob:
        return "login_wall", "页面文本含「请先登录」或「登录后观看」"
    return None, ""


def fetch_route(context, vid: str, route: str, page_url: str, log: Log) -> dict:
    """Open one route. Read document bodies inside the response callback."""
    docs = []
    captcha_hit = {"value": False}
    t0 = time.perf_counter()

    def on_response(resp):
        try:
            url = resp.url or ""
        except Exception:
            return
        if CAPTCHA_URL in url:
            captcha_hit["value"] = True
        try:
            if resp.request.resource_type != "document":
                return
            base = page_url.split("?")[0]
            if not (url.startswith(page_url) or (url.startswith(base) and vid in url)):
                return
        except Exception:
            return
        # Body is discarded after the navigation callback returns.
        try:
            body = resp.body()
        except Exception:
            body = b""
        docs.append((url, getattr(resp, "status", 0), body))

    page = context.new_page()
    page.on("response", on_response)
    error = None
    try:
        try:
            page.goto(page_url, wait_until="domcontentloaded", timeout=40000)
        except Exception as exc:  # noqa: BLE001
            error = f"goto {type(exc).__name__}"
            log.info(f"route={route} goto error={error} url={page_url}")
        deadline = time.monotonic() + 8
        detail = parse_docs(docs, vid)
        while detail is None and time.monotonic() < deadline:
            page.wait_for_timeout(300)
            detail = parse_docs(docs, vid)
        visible = ""
        content_html = ""
        if detail is None:
            try:
                content_html = page.content()
            except Exception:
                content_html = ""
            if content_html:
                detail = extract_detail(content_html, vid)
            if detail is None:
                try:
                    visible = page.inner_text("body", timeout=2000)
                except Exception:
                    visible = ""
        elapsed = round(time.perf_counter() - t0, 3)
        if detail is not None:
            # Dismissible login toast is not a wall. Do not click it.
            sizes = [len(body) if body else 0 for _url, _status, body in docs]
            log.info(
                f"route={route} detail ok awemeType={detail.get('awemeType')} "
                f"docs={len(docs)} sizes={sizes} elapsed={elapsed}s url={page_url}"
            )
            return {
                "ok": True,
                "detail": detail,
                "blocked": None,
                "reason": "ok",
                "elapsed": elapsed,
                "error": None,
            }
        texts = []
        for _url, _status, body in docs:
            if body:
                texts.append(body.decode("utf-8", "ignore")[:200000])
        if content_html:
            texts.append(content_html[:200000])
        if visible:
            texts.append(visible[:50000])
        kind, why = classify_wall(texts, captcha_hit["value"])
        if kind:
            log.info(f"route={route} blocked={kind} why={why} docs={len(docs)} elapsed={elapsed}s")
            return {
                "ok": False,
                "detail": None,
                "blocked": kind,
                "reason": why,
                "elapsed": elapsed,
                "error": error,
            }
        reason = error or "no detail"
        log.info(f"route={route} no detail docs={len(docs)} reason={reason} elapsed={elapsed}s url={page_url}")
        return {
            "ok": False,
            "detail": None,
            "blocked": None,
            "reason": reason,
            "elapsed": elapsed,
            "error": error,
        }
    finally:
        try:
            page.close()
        except Exception:
            pass


def launch_browser(playwright, headed: bool, chrome: str | None):
    launch_kwargs = {
        "headless": not headed,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    }
    if chrome:
        launch_kwargs["executable_path"] = chrome
    browser = playwright.chromium.launch(**launch_kwargs)
    context = browser.new_context(
        user_agent=UA,
        viewport={"width": 1280, "height": 900},
        locale="zh-CN",
    )

    def route_handler(route):
        try:
            if route.request.resource_type in ("image", "media", "font"):
                route.abort()
            else:
                route.continue_()
        except Exception:
            try:
                route.continue_()
            except Exception:
                pass

    context.route("**/*", route_handler)
    return browser, context


def fetch_detail_routes(context, vid: str, retries: int, log: Log) -> dict:
    attempts = []
    for route, template in ROUTES:
        page_url = template.format(vid=vid)
        for attempt in range(retries + 1):
            result = fetch_route(context, vid, route, page_url, log)
            attempts.append(
                {
                    "strategy": route,
                    "ok": bool(result["ok"]),
                    "reason": result["blocked"] or result["reason"],
                    "elapsed": result["elapsed"],
                    "attempt": attempt + 1,
                }
            )
            if result["ok"]:
                return {
                    "detail": result["detail"],
                    "route": route,
                    "page_url": page_url,
                    "attempts": attempts,
                    "blocked": None,
                    "blocked_reason": None,
                }
            if result["blocked"]:
                return {
                    "detail": None,
                    "route": route,
                    "page_url": page_url,
                    "attempts": attempts,
                    "blocked": result["blocked"],
                    "blocked_reason": f"{result['blocked']}@{route}: {result['reason']}",
                }
            if attempt < retries:
                delay = min(2 ** (attempt + 1), 8)
                log.info(f"route={route} retry in {delay}s attempt={attempt + 1}/{retries}")
                time.sleep(delay)
    return {
        "detail": None,
        "route": None,
        "page_url": None,
        "attempts": attempts,
        "blocked": None,
        "blocked_reason": None,
    }


# --- per item files ---

def raw_path(out: Path, rank: int, vid: str) -> Path:
    safe = re.sub(r"[^\w.-]", "_", vid or "unknown")
    return out / "raw" / f"{rank:02d}_{safe}.detail.json"


def state_path(out: Path, rank: int) -> Path:
    return out / "state" / f"{rank:02d}.json"


def media_dir(out: Path, rank: int) -> Path:
    return out / "media" / f"{rank:02d}"


def current_flags(args) -> dict:
    return {
        "no_video": bool(args.no_video),
        "no_asr": bool(args.no_asr),
        "frames": int(args.frames),
        "video_quality": args.video_quality,
        "asr_model": args.asr_model,
    }


def required_files(item: dict, args) -> list[str]:
    files = []
    if item.get("cover"):
        files.append(item["cover"])
    for path in item.get("images") or []:
        files.append(path)
    if item.get("content_type") == "视频" and not args.no_video:
        if item.get("video_file"):
            files.append(item["video_file"])
        if item.get("audio_file"):
            files.append(item["audio_file"])
        for frame in item.get("frames") or []:
            if isinstance(frame, dict) and frame.get("file"):
                files.append(frame["file"])
    return files


def files_exist(out: Path, rels: list[str]) -> bool:
    for rel in rels:
        path = out / rel
        if not path.is_file() or path.stat().st_size <= 0:
            return False
    return True


def can_full_skip(state: dict | None, out: Path, args, src: dict) -> bool:
    if not state or args.force:
        return False
    if not state.get("detail_ok") or state.get("status") != "ok":
        return False
    if state.get("flags") != current_flags(args):
        return False
    item = state.get("item") or {}
    if str(item.get("video_id")) != str(src["video_id"]):
        return False
    raw = raw_path(out, src["rank"], src["video_id"])
    if not raw.is_file() or raw.stat().st_size <= 0:
        return False
    return files_exist(out, required_files(item, args))


def load_cached_detail(out: Path, rank: int, vid: str, force: bool) -> dict | None:
    if force:
        return None
    path = raw_path(out, rank, vid)
    if not path.is_file() or path.stat().st_size <= 0:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if str(data.get("awemeId")) != str(vid):
        return None
    return data


def download_media(detail: dict, item: dict, out: Path, args, log: Log, force: bool) -> dict:
    """Fill local media fields. Return stage notes for field_status."""
    notes = {}
    rank = item["rank"]
    folder = media_dir(out, rank)
    folder.mkdir(parents=True, exist_ok=True)
    content_type = item.get("content_type")

    cover_dest = folder / f"{rank:02d}_cover.jpg"
    if content_type == "视频":
        if not force and image_file_ok(cover_dest):
            item["cover"] = relpath(out, cover_dest)
            size = image_size(cover_dest)
            item["cover_size"] = [size[0], size[1]] if size else None
            log.info(f"skip cover rank={rank:02d} file exists")
        else:
            ok, err, used, size = download_best_static_cover(detail, cover_dest, log, rank)
            if ok:
                item["cover"] = relpath(out, cover_dest)
                item["cover_url"] = used
                item["cover_size"] = size
            else:
                item["cover"] = None
                item["cover_size"] = None
                notes["cover"] = err or "封面 URL 为空"
    else:
        urls = cover_urls(detail)
        if not item.get("cover_url"):
            item["cover_url"] = urls[0] if urls else None
        if not force and image_file_ok(cover_dest):
            item["cover"] = relpath(out, cover_dest)
            size = image_size(cover_dest)
            item["cover_size"] = [size[0], size[1]] if size else None
            log.info(f"skip cover rank={rank:02d} file exists")
        else:
            ok, err, used = download_with_retries(urls, cover_dest, "image", log)
            if ok:
                item["cover"] = relpath(out, cover_dest)
                item["cover_url"] = used
                size = image_size(cover_dest)
                item["cover_size"] = [size[0], size[1]] if size else None
            else:
                item["cover"] = None
                item["cover_size"] = None
                notes["cover"] = err or "封面 URL 为空"

    if content_type == "图文" or (item.get("image_count") or 0) > 0:
        groups = image_entries(detail)
        saved = []
        used_urls = []
        fail_notes = []
        for index, urls in enumerate(groups, start=1):
            dest = folder / f"{rank:02d}_{index}.jpg"
            if not force and image_file_ok(dest):
                saved.append(relpath(out, dest))
                used_urls.append(urls[0] if urls else None)
                log.info(f"skip image rank={rank:02d} k={index} file exists")
                continue
            ok, err, used = download_with_retries(urls, dest, "image", log)
            if ok:
                saved.append(relpath(out, dest))
                used_urls.append(used)
            else:
                fail_notes.append(f"{index}:{err}")
        item["images"] = saved
        item["image_urls"] = used_urls
        if fail_notes:
            notes["images"] = "部分图片下载失败 " + "; ".join(fail_notes)
        elif not groups:
            notes["images"] = "detail.images 为空"
            item["images"] = []
    elif content_type == "视频":
        item["images"] = []
        item["image_urls"] = []

    if content_type != "视频":
        return notes

    if args.no_video:
        notes["video_file"] = "命令行 --no-video，跳过视频、音频和抽帧"
        notes["frames"] = "命令行 --no-video，跳过抽帧"
        item["video_file"] = None
        item["audio_file"] = None
        item["frames"] = []
        return notes

    mp4 = folder / f"{rank:02d}.mp4"
    tier = select_video_tier(detail, args.video_quality)
    if tier is None:
        notes["video_file"] = "没有 format=mp4 且 isH265=0 的档位"
    else:
        gear = tier.get("gearName")
        log.info(
            f"video tier rank={rank:02d} quality={args.video_quality} "
            f"gear={gear} dataSize={tier.get('dataSize')}"
        )
        urls = prefer_urls(tier.get("playAddr") or [])
        if not force and media_file_ok(mp4):
            item["video_file"] = relpath(out, mp4)
            log.info(f"skip video rank={rank:02d} file exists")
        else:
            ok, err, _used = download_with_retries(urls, mp4, "media", log)
            if ok:
                item["video_file"] = relpath(out, mp4)
            else:
                notes["video_file"] = err or "mp4 下载失败"
                item["video_file"] = None

    if item.get("video_file") and media_file_ok(mp4):
        probed = ffprobe_duration(mp4)
        item["media_duration_sec"] = probed

    m4a = folder / f"{rank:02d}.m4a"
    if not force and media_file_ok(m4a):
        item["audio_file"] = relpath(out, m4a)
        log.info(f"skip audio rank={rank:02d} file exists")
    else:
        urls = audio_urls(detail)
        ok = False
        err = ""
        if urls:
            ok, err, _used = download_with_retries(urls, m4a, "media", log)
        if not ok and item.get("video_file"):
            ok, err = extract_audio(mp4, m4a)
            if ok:
                log.info(f"audio extracted rank={rank:02d} via {err}")
        if ok:
            item["audio_file"] = relpath(out, m4a)
        else:
            item["audio_file"] = None
            notes["audio"] = err or "没有音频 URL，也没有 mp4 可抽轨"

    duration = item.get("media_duration_sec") or item.get("duration_sec")
    if item.get("video_file") and duration:
        frames, err = extract_frames(mp4, folder, rank, float(duration), args.frames)
        item["frames"] = [
            {"file": relpath(out, frame["path"]), "timestamp_sec": frame["timestamp_sec"]} for frame in frames
        ]
        if err:
            notes["frames"] = err
        if args.frames > 0 and len(item["frames"]) < args.frames:
            notes["frames"] = notes.get("frames") or f"只抽到 {len(item['frames'])}/{args.frames} 帧"
    elif args.frames <= 0:
        item["frames"] = []
        notes["frames"] = "--frames 0，跳过抽帧"
    else:
        item["frames"] = []
        notes["frames"] = "没有视频文件或时长，无法抽帧"
    return notes


def apply_transcript_placeholder(item: dict, no_asr: bool) -> None:
    if item.get("content_type") == "图文":
        item["transcript"] = None
        item["transcript_status"] = "skipped_tuwen"
        return
    if item.get("content_type") != "视频":
        item["transcript"] = None
        item["transcript_status"] = None
        return
    if item.get("transcript_status") in ("ok", "no_speech", "fail", "skipped_no_audio"):
        return
    if no_asr:
        item["transcript"] = None
        item["transcript_status"] = "skipped_no_asr"
    elif not item.get("audio_file"):
        item["transcript"] = None
        item["transcript_status"] = "skipped_no_audio"


def collect_errors(item: dict, notes: dict, blocked_reason: str | None) -> str | None:
    parts = []
    if blocked_reason:
        parts.append(blocked_reason)
    for key in ("cover", "images", "video_file", "frames", "audio", "transcript", "detail"):
        if notes.get(key):
            parts.append(f"{key}: {notes[key]}")
    if not parts:
        return None
    return "; ".join(parts)


def bundle_from_state(state: dict) -> dict:
    return {
        "item": state["item"],
        "engagement": state["engagement"],
        "field_status": state["field_status"],
        "attempts": state.get("attempts") or [],
        "blocked_reason": state.get("blocked_reason"),
        "detail_ok": bool(state.get("detail_ok")),
        "stages": state.get("stages") or {},
        "segments_file": state.get("segments_file") or (state.get("item") or {}).get("segments_file"),
        "duration_audio": state.get("duration_audio"),
        "opened": False,
    }


def save_bundle(out: Path, bundle: dict, args, detail_ok: bool) -> None:
    item = bundle["item"]
    state = {
        "rank": item["rank"],
        "video_id": item["video_id"],
        "detail_ok": detail_ok,
        "status": item.get("status"),
        "route": item.get("route"),
        "page_url": item.get("page_url"),
        "blocked_reason": bundle.get("blocked_reason"),
        "flags": current_flags(args),
        "stages": bundle.get("stages") or {},
        "attempts": bundle.get("attempts") or [],
        "segments_file": bundle.get("segments_file"),
        "duration_audio": bundle.get("duration_audio"),
        "item": item,
        "engagement": bundle["engagement"],
        "field_status": bundle["field_status"],
    }
    dump_json(state_path(out, item["rank"]), state)


def process_item(src: dict, out: Path, args, log: Log, context) -> dict:
    t0 = time.perf_counter()
    rank = src["rank"]
    vid = src["video_id"]
    log.info(f"ITEM rank={rank:02d} video_id={vid}")
    state = None
    if not args.force:
        path = state_path(out, rank)
        if path.is_file():
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                state = None
    if can_full_skip(state, out, args, src):
        log.info(f"skip rank={rank:02d} video_id={vid} reason=completed state and files exist; not opening page")
        return bundle_from_state(state)

    if not vid:
        item = blank_item(src)
        item["status"] = "missing"
        item["error"] = "缺少 video_id"
        item["fetched_at"] = now_iso()
        item["elapsed_sec"] = round(time.perf_counter() - t0, 3)
        fields = judge_fields(item, False, {"detail": "缺少 video_id"})
        engagement = engagement_of(item, [], None)
        bundle = {
            "item": item,
            "engagement": engagement,
            "field_status": {"rank": rank, "video_id": vid, "fields": fields},
            "attempts": [],
            "blocked_reason": None,
            "detail_ok": False,
            "stages": {"detail": "missing"},
        }
        save_bundle(out, bundle, args, False)
        return bundle

    detail = load_cached_detail(out, rank, vid, args.force)
    attempts = []
    blocked = None
    blocked_reason = None
    route = None
    page_url = None
    opened = False
    if detail is not None and state and state.get("detail_ok"):
        route = state.get("route") or (state.get("item") or {}).get("route")
        page_url = state.get("page_url") or (state.get("item") or {}).get("page_url")
        attempts = state.get("attempts") or []
        log.info(f"skip browser rank={rank:02d} video_id={vid} reason=cached detail, resume files")
    else:
        if context is None:
            raise RuntimeError("browser context missing")
        opened = True
        fetched = fetch_detail_routes(context, vid, args.retries, log)
        attempts = fetched["attempts"]
        blocked = fetched["blocked"]
        blocked_reason = fetched["blocked_reason"]
        route = fetched["route"]
        page_url = fetched["page_url"]
        detail = fetched["detail"]
        if detail is not None:
            dump_json(raw_path(out, rank, vid), detail)

    notes = {}
    if detail is None:
        item = blank_item(src)
        item["page_url"] = page_url
        item["route"] = route if blocked else None
        item["fetched_at"] = now_iso()
        if blocked:
            item["status"] = "blocked"
            notes["detail"] = blocked_reason
        else:
            item["status"] = "missing"
            notes["detail"] = "全部路由都没有解析到 detail"
        item["elapsed_sec"] = round(time.perf_counter() - t0, 3)
        item["error"] = collect_errors(item, notes, blocked_reason if blocked else None)
        if not blocked:
            item["error"] = notes["detail"]
        fields = judge_fields(item, False, notes)
        item["status"] = "blocked" if blocked else "missing"
        engagement = engagement_of(item, attempts, blocked_reason if blocked else None)
        bundle = {
            "item": item,
            "engagement": engagement,
            "field_status": {"rank": rank, "video_id": vid, "fields": fields},
            "attempts": attempts,
            "blocked_reason": blocked_reason if blocked else None,
            "detail_ok": False,
            "stages": {"detail": "blocked" if blocked else "missing"},
            "opened": opened,
        }
        save_bundle(out, bundle, args, False)
        return bundle

    item = map_detail(detail, src, route, page_url)
    # preserve earlier fetch time on pure resume
    if not opened and state and (state.get("item") or {}).get("fetched_at"):
        item["fetched_at"] = state["item"]["fetched_at"]
    if not opened and state and state.get("item") and state["item"].get("transcript_status") in ("ok", "no_speech"):
        prev = state["item"]
        item["transcript"] = prev.get("transcript")
        item["transcript_status"] = prev.get("transcript_status")
        item["segments_file"] = prev.get("segments_file")
        item["duration_audio"] = prev.get("duration_audio")
    notes = download_media(detail, item, out, args, log, args.force)
    if not opened and state and state.get("item"):
        prev_item = state["item"]
        if not item.get("cover_url") and prev_item.get("cover_url"):
            item["cover_url"] = prev_item["cover_url"]
    apply_transcript_placeholder(item, args.no_asr)
    if item.get("transcript_status") == "fail":
        notes["transcript"] = (state.get("item") or {}).get("error") if state else "ASR 失败"
    fields = judge_fields(item, True, notes)
    item["status"] = decide_item_status(item, fields, args.no_video, args.no_asr)
    item["elapsed_sec"] = round(time.perf_counter() - t0, 3)
    # 没重新打开页面就不是一次新的抓取，保留上次写入的耗时（含 partial）。
    if not opened and state and (state.get("item") or {}).get("elapsed_sec") is not None:
        item["elapsed_sec"] = state["item"]["elapsed_sec"]
    item["error"] = collect_errors(item, notes, None)
    # internal keys must not leak into items.json
    segments_file = item.pop("segments_file", None)
    duration_audio = item.pop("duration_audio", None)
    engagement = engagement_of(item, attempts, None)
    stages = {
        "detail": "ok",
        "cover": "ok" if item.get("cover") else "missing",
        "images": "ok" if (fields.get("images") or {}).get("status") in ("ok", "not_applicable") else "missing",
        "video": "not_applicable" if item.get("content_type") == "图文" else ("ok" if item.get("video_file") else "missing"),
        "audio": "not_applicable" if item.get("content_type") != "视频" else ("ok" if item.get("audio_file") else "missing"),
        "frames": "not_applicable" if item.get("content_type") == "图文" else ("ok" if item.get("frames") else "missing"),
        "transcript": item.get("transcript_status"),
    }
    bundle = {
        "item": item,
        "engagement": engagement,
        "field_status": {"rank": rank, "video_id": vid, "fields": fields},
        "attempts": attempts,
        "blocked_reason": None,
        "detail_ok": True,
        "stages": stages,
        "opened": opened,
        "segments_file": segments_file,
        "duration_audio": duration_audio,
    }
    save_bundle(out, bundle, args, True)
    log_status = item["status"]
    if (
        item.get("content_type") == "视频"
        and not args.no_asr
        and item.get("transcript_status") not in ("ok", "no_speech", "fail", "skipped_no_audio", "skipped_no_asr")
    ):
        log_status = "pending_asr"
    log.info(
        f"ITEM done rank={rank:02d} status={log_status} type={item.get('content_type')} "
        f"route={route} elapsed={item['elapsed_sec']}s"
    )
    return bundle


RUN_TIMING_KEYS = (
    "total_elapsed_sec",
    "sum_item_elapsed_sec",
    "avg_item_elapsed_sec",
    "asr_elapsed_sec",
)


def coverage_of(bundles: list, wall_sec: float, started: str, finished: str, aborted: bool, abort_reason: str | None, not_run: list, asr_sec: float | None) -> dict:
    stats = {
        name: {
            "applicable": 0,
            "ok": 0,
            "missing": 0,
            "pending": 0,
            "not_applicable": 0,
            "coverage": None,
        }
        for name in FIELD_NAMES
    }
    status_counts = {"ok": 0, "partial": 0, "blocked": 0, "missing": 0}
    blocked = []
    elapsed_sum = 0.0
    for bundle in bundles:
        item = bundle["item"]
        status_counts[item.get("status") or "missing"] = status_counts.get(item.get("status") or "missing", 0) + 1
        if item.get("elapsed_sec"):
            elapsed_sum += float(item["elapsed_sec"])
        if item.get("status") == "blocked":
            blocked.append(
                {
                    "rank": item["rank"],
                    "video_id": item["video_id"],
                    "reason": bundle.get("blocked_reason") or item.get("error"),
                }
            )
        fields = (bundle.get("field_status") or {}).get("fields") or {}
        for name in FIELD_NAMES:
            meta = fields.get(name) or {"status": "missing", "reason": "无字段状态"}
            slot = stats[name]
            status = meta.get("status")
            if status == "not_applicable":
                slot["not_applicable"] += 1
            elif status == "ok":
                slot["applicable"] += 1
                slot["ok"] += 1
            elif status == "pending":
                slot["applicable"] += 1
                slot["pending"] += 1
            else:
                slot["applicable"] += 1
                slot["missing"] += 1
    for slot in stats.values():
        if slot["applicable"]:
            slot["coverage"] = round(slot["ok"] / slot["applicable"], 4)
    n = len(bundles)
    return {
        "item_count": n,
        "status_counts": status_counts,
        "fields": stats,
        "total_elapsed_sec": round(wall_sec, 3),
        "sum_item_elapsed_sec": round(elapsed_sum, 3),
        "avg_item_elapsed_sec": round(elapsed_sum / n, 3) if n else None,
        "asr_elapsed_sec": None if asr_sec is None else round(asr_sec, 3),
        "blocked": blocked,
        "aborted": aborted,
        "abort_reason": abort_reason,
        "not_run_ranks": not_run,
        "started_at": started,
        "finished_at": finished,
    }


def load_saved_bundles(out: Path) -> list:
    """Item snapshots already stored under state/*.json. Skip ASR job lists."""
    state_dir = out / "state"
    if not state_dir.is_dir():
        return []
    found = []
    for path in state_dir.glob("*.json"):
        if path.name.startswith("_"):
            continue
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(state, dict):
            continue
        item = state.get("item")
        if not isinstance(item, dict) or item.get("rank") is None:
            continue
        found.append(bundle_from_state(state))
    return found


def merge_bundles(saved: list, current: list) -> list:
    """Union by rank. Bundles from this run replace the stored snapshot."""
    by_rank = {}
    for bundle in list(saved) + list(current):
        try:
            rank = int(bundle["item"]["rank"])
        except (KeyError, TypeError, ValueError):
            continue
        by_rank[rank] = bundle
    return [by_rank[rank] for rank in sorted(by_rank)]


def load_prior_runs(path: Path) -> list:
    """History already on disk. An old coverage without runs contributes one timing record."""
    if not path.is_file():
        return []
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(old, dict):
        return []
    runs = old.get("runs")
    if isinstance(runs, list):
        return [row for row in runs if isinstance(row, dict)]
    record = {key: old[key] for key in RUN_TIMING_KEYS if key in old}
    return [record] if record else []


def run_elapsed_sum(bundles: list) -> float:
    total = 0.0
    for bundle in bundles:
        value = (bundle.get("item") or {}).get("elapsed_sec")
        if value:
            total += float(value)
    return total


def publish_outputs(
    out: Path,
    run_bundles: list,
    prior_runs: list,
    ranks: list,
    wall_sec: float,
    started: str,
    finished: str,
    aborted: bool,
    abort_reason: str | None,
    not_run: list,
    asr_sec: float | None,
    model: str,
    extra: dict | None = None,
) -> dict:
    """Write summaries for every finished state entry, and archive this run's timing."""
    merged = merge_bundles(load_saved_bundles(out), run_bundles)
    coverage = coverage_of(merged, wall_sec, started, finished, aborted, abort_reason, not_run, asr_sec)
    elapsed_sum = run_elapsed_sum(run_bundles)
    n_run = len(run_bundles)
    this_run = {
        "ranks": [int(rank) for rank in ranks],
        "total_elapsed_sec": coverage["total_elapsed_sec"],
        "sum_item_elapsed_sec": round(elapsed_sum, 3),
        "avg_item_elapsed_sec": round(elapsed_sum / n_run, 3) if n_run else None,
        "asr_elapsed_sec": coverage["asr_elapsed_sec"],
    }
    # Top-level timing stays "this invocation". Field coverage above is the merged corpus.
    coverage["sum_item_elapsed_sec"] = this_run["sum_item_elapsed_sec"]
    coverage["avg_item_elapsed_sec"] = this_run["avg_item_elapsed_sec"]
    coverage["this_run"] = this_run
    coverage["runs"] = [dict(row) for row in prior_runs] + [this_run]
    if extra:
        coverage.update(extra)
    write_outputs(out, merged, coverage, model)
    return coverage


def write_outputs(out: Path, bundles: list, coverage: dict, model: str) -> None:
    items = [bundle["item"] for bundle in bundles]
    dump_json(out / "items.json", items)
    write_jsonl(out / "items.jsonl", items)
    dump_json(out / "engagement.json", [bundle["engagement"] for bundle in bundles])
    dump_json(out / "field_status.json", [bundle["field_status"] for bundle in bundles])
    dump_json(out / "coverage.json", coverage)
    rows = []
    for bundle in bundles:
        item = dict(bundle["item"])
        if bundle.get("segments_file"):
            item["segments_file"] = bundle["segments_file"]
        if bundle.get("duration_audio") is not None:
            item["duration_audio"] = bundle["duration_audio"]
        row = transcript_row_for(item, model)
        if row:
            if bundle.get("duration_audio") is not None and row["status"] in ("ok", "no_speech"):
                row["duration_audio"] = bundle["duration_audio"]
            rows.append(row)
    # Rebuild from the merged corpus, then keep any richer row already on disk (especially ok).
    existing = out / "transcripts.jsonl"
    merged = merge_transcript_rows(rows, read_jsonl(existing) if existing.is_file() else [])
    write_jsonl(existing, merged)


def read_jsonl(path: Path) -> list:
    rows = []
    if not path.is_file():
        return rows
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def merge_transcript_rows(primary: list, extra: list) -> list:
    """Merge by rank. `extra` is the file on disk; `primary` is rebuilt this run.

    File rows are collapsed first, so a later ok (just appended by ASR) beats an
    earlier one. This run only replaces a rank when its status strictly outranks
    the file. An existing ok is therefore kept.
    """
    priority = {
        "ok": 5,
        "no_speech": 4,
        "skipped_tuwen": 3,
        "skipped_no_audio": 3,
        "skipped_no_asr": 2,
        "fail": 1,
    }

    def rank_of(row: dict):
        try:
            return int(row.get("rank"))
        except (TypeError, ValueError):
            return None

    by_rank = {}
    for row in extra:
        rank = rank_of(row)
        if rank is None:
            continue
        prev = by_rank.get(rank)
        if prev is None or priority.get(row.get("status"), 0) >= priority.get(prev.get("status"), 0):
            by_rank[rank] = row
    for row in primary:
        rank = rank_of(row)
        if rank is None:
            continue
        prev = by_rank.get(rank)
        if prev is not None and priority.get(row.get("status"), 0) <= priority.get(prev.get("status"), 0):
            continue
        by_rank[rank] = row
    return [by_rank[rank] for rank in sorted(by_rank)]


def run_asr(out: Path, bundles: list, args, log: Log) -> float:
    jobs = []
    for bundle in bundles:
        item = bundle["item"]
        if item.get("content_type") != "视频":
            continue
        if item.get("transcript_status") in ("ok", "no_speech") and not args.force:
            log.info(f"skip asr rank={item['rank']:02d} status={item['transcript_status']}")
            continue
        if not item.get("audio_file"):
            item["transcript"] = None
            item["transcript_status"] = "skipped_no_audio"
            continue
        audio = out / item["audio_file"]
        seg_rel = f"transcripts/{item['rank']:02d}_{item['video_id']}.segments.json"
        jobs.append(
            {
                "rank": item["rank"],
                "video_id": item["video_id"],
                "audio": str(audio),
                "segments_path": str(out / seg_rel),
                "segments_file": seg_rel,
            }
        )
    if not jobs:
        log.info("ASR no video jobs")
        return 0.0
    whisper_py = resolve_whisper_python(args.whisper_python)
    if not whisper_py:
        log.info("ASR " + ASR_MISSING_REASON)
        for bundle in bundles:
            item = bundle["item"]
            if item.get("content_type") != "视频":
                continue
            if item.get("transcript_status") in ("ok", "no_speech", "skipped_no_audio", "skipped_tuwen"):
                continue
            item["transcript"] = None
            item["transcript_status"] = "skipped_no_asr"
            prev = item.get("error") or ""
            if ASR_MISSING_REASON not in prev:
                item["error"] = (prev + "; " if prev else "") + ASR_MISSING_REASON
            fields = (bundle.get("field_status") or {}).setdefault("fields", {})
            fields["transcript"] = {"status": "missing", "reason": ASR_MISSING_REASON}
            stages = bundle.setdefault("stages", {})
            stages["transcript"] = "skipped_no_asr"
            if item.get("status") != "blocked":
                item["status"] = decide_item_status(item, fields, args.no_video, args.no_asr)
            save_bundle(out, bundle, args, bool(bundle.get("detail_ok", True)))
        return 0.0
    jobs_path = out / "state" / "_asr_jobs.json"
    dump_json(jobs_path, jobs)
    jsonl = out / "transcripts.jsonl"
    cmd = [
        whisper_py,
        "-u",
        str(ASR_WORKER),
        "--input",
        str(jobs_path),
        "--jsonl",
        str(jsonl),
        "--model",
        args.asr_model,
    ]
    if args.asr_allow_download:
        cmd.append("--asr-allow-download")
    if args.force:
        cmd.append("--force")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    log.info(f"ASR start jobs={len(jobs)} model={args.asr_model} python={whisper_py}")
    t0 = time.perf_counter()
    # Line-buffer the worker so each finished transcript hits run.log immediately.
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        bufsize=1,
    )
    tail: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        text = line.rstrip("\n")
        if not text:
            continue
        log.info("ASR " + text)
        tail.append(text)
    returncode = proc.wait()
    elapsed = time.perf_counter() - t0
    if returncode != 0:
        err = " | ".join(tail)[-500:]
        log.info(f"ASR worker exit={returncode} err={err}")
    by_key = {}
    for row in read_jsonl(jsonl):
        try:
            by_key[(int(row.get("rank")), str(row.get("video_id")))] = row
        except (TypeError, ValueError):
            continue
    for bundle in bundles:
        item = bundle["item"]
        if item.get("content_type") != "视频":
            continue
        row = by_key.get((int(item["rank"]), str(item["video_id"])))
        if not row:
            if item.get("transcript_status") not in ("ok", "no_speech", "skipped_no_audio"):
                item["transcript_status"] = "fail"
            continue
        item["transcript_status"] = row.get("status")
        item["transcript"] = row.get("text") or None
        if row.get("status") != "ok":
            item["transcript"] = row.get("text") or None
        bundle["segments_file"] = row.get("segments_file")
        bundle["duration_audio"] = row.get("duration_audio")
        if row.get("status") == "fail":
            item["error"] = (item.get("error") + "; " if item.get("error") else "") + (row.get("error") or "ASR 失败")
        fields = judge_fields(item, True, {"transcript": row.get("error") or ""})
        # judge_fields replaces every field; keep it, status may change
        bundle["field_status"] = {"rank": item["rank"], "video_id": item["video_id"], "fields": fields}
        if item.get("status") != "blocked":
            item["status"] = decide_item_status(item, fields, args.no_video, args.no_asr)
        save_bundle(out, bundle, args, True)
    log.info(f"ASR done elapsed={elapsed:.1f}s")
    return elapsed


def assert_out_safe(package: Path, out: Path) -> None:
    pkg = package.resolve()
    dest = out.resolve()
    if dest == pkg or pkg in dest.parents or dest in pkg.parents:
        raise SystemExit("输出目录不能是分析包，也不能放在分析包里面或包住分析包")


def main() -> int:
    args = build_parser().parse_args()
    package = Path(args.package).resolve()
    out = Path(args.out).resolve()
    if not package.is_dir():
        raise SystemExit(f"分析包不存在: {package}")
    assert_out_safe(package, out)
    if args.limit is not None and args.limit < 0:
        raise SystemExit("--limit 不能为负")
    if args.retries < 0:
        raise SystemExit("--retries 不能为负")
    if args.frames < 0:
        raise SystemExit("--frames 不能为负")
    out.mkdir(parents=True, exist_ok=True)
    log = Log(out / "run.log")
    started = now_iso()
    wall0 = time.perf_counter()
    try:
        rows, source = load_package(package)
        if args.ranks:
            rows = [row for row in rows if row["rank"] in args.ranks]
        if args.limit is not None:
            rows = rows[: args.limit]
        log.info(
            f"RUN start source={source} n={len(rows)} out={out} "
            f"no_asr={args.no_asr} no_video={args.no_video} frames={args.frames} "
            f"retries={args.retries} quality={args.video_quality} force={args.force}"
        )
        prior_runs = load_prior_runs(out / "coverage.json")
        run_ranks = [int(row["rank"]) for row in rows]
        if not rows:
            publish_outputs(
                out,
                [],
                prior_runs,
                run_ranks,
                0,
                started,
                now_iso(),
                False,
                None,
                [],
                None,
                args.asr_model,
            )
            log.info("RUN empty selection")
            return 0

        bundles = []
        blocked_streak = 0
        aborted = False
        abort_reason = None
        browser = None
        context = None
        playwright = None
        pw_cm = None

        def ensure_browser():
            nonlocal browser, context, playwright, pw_cm
            if context is not None:
                return context
            from playwright.sync_api import sync_playwright

            pw_cm = sync_playwright()
            playwright = pw_cm.__enter__()
            chrome = resolve_chrome(args.chrome)
            browser, context = launch_browser(playwright, args.headed, chrome)
            log.info(
                "browser launched headless=%s chrome=%s"
                % (not args.headed, chrome or "playwright-chromium")
            )
            return context

        try:
            for index, src in enumerate(rows):
                if aborted:
                    break
                need_browser = True
                if not args.force:
                    path = state_path(out, src["rank"])
                    state = None
                    if path.is_file():
                        try:
                            state = json.loads(path.read_text(encoding="utf-8"))
                        except json.JSONDecodeError:
                            state = None
                    if can_full_skip(state, out, args, src) or (
                        load_cached_detail(out, src["rank"], src["video_id"], False) is not None
                        and state
                        and state.get("detail_ok")
                    ):
                        need_browser = False
                ctx = ensure_browser() if need_browser else None
                try:
                    bundle = process_item(src, out, args, log, ctx)
                except Exception as exc:  # noqa: BLE001
                    log.info(f"ITEM crash rank={src['rank']:02d} err={type(exc).__name__}: {exc}")
                    item = blank_item(src)
                    item["status"] = "missing"
                    item["error"] = f"{type(exc).__name__}: {exc}"
                    item["fetched_at"] = now_iso()
                    item["elapsed_sec"] = 0
                    fields = judge_fields(item, False, {"detail": item["error"]})
                    bundle = {
                        "item": item,
                        "engagement": engagement_of(item, [], None),
                        "field_status": {"rank": src["rank"], "video_id": src["video_id"], "fields": fields},
                        "attempts": [],
                        "blocked_reason": None,
                        "detail_ok": False,
                        "stages": {"detail": "error"},
                        "opened": need_browser,
                    }
                    save_bundle(out, bundle, args, False)
                bundles.append(bundle)
                status = bundle["item"].get("status")
                if status == "blocked":
                    blocked_streak += 1
                    if blocked_streak >= 3:
                        aborted = True
                        abort_reason = "连续 3 条 blocked，中止后续条目"
                        log.info(abort_reason)
                else:
                    blocked_streak = 0
                publish_outputs(
                    out,
                    bundles,
                    prior_runs,
                    run_ranks,
                    time.perf_counter() - wall0,
                    started,
                    now_iso(),
                    aborted,
                    abort_reason,
                    [row["rank"] for row in rows[index + 1 :]] if aborted else [],
                    None,
                    args.asr_model,
                )
                opened = bundle.get("opened")
                if opened is None:
                    opened = need_browser and not (status == "ok" and not args.force)
                if index < len(rows) - 1 and not aborted and bundle.get("opened"):
                    delay = random.uniform(*args.sleep)
                    log.info(f"sleep {delay:.1f}s")
                    time.sleep(delay)
        finally:
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass
            if pw_cm is not None:
                try:
                    pw_cm.__exit__(None, None, None)
                except Exception:
                    pass

        asr_sec = None
        if not args.no_asr and not aborted:
            asr_sec = run_asr(out, bundles, args, log)
        elif not args.no_asr and aborted:
            log.info("ASR skipped because run aborted")
            asr_sec = 0.0

        not_run = []
        done_ranks = {bundle["item"]["rank"] for bundle in bundles}
        if aborted:
            not_run = [row["rank"] for row in rows if row["rank"] not in done_ranks]
        coverage = publish_outputs(
            out,
            bundles,
            prior_runs,
            run_ranks,
            time.perf_counter() - wall0,
            started,
            now_iso(),
            aborted,
            abort_reason,
            not_run,
            asr_sec,
            args.asr_model,
            {"package_source": source, "package": str(package)},
        )
        log.info(
            "RUN done "
            + " ".join(f"{key}={value}" for key, value in coverage["status_counts"].items())
            + f" aborted={aborted}"
        )
        return 0
    finally:
        log.close()


if __name__ == "__main__":
    raise SystemExit(main())
