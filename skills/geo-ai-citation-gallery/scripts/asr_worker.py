#!/usr/bin/env python3
"""faster-whisper 批量转写。模型只加载一次，每完成一条就追加一行 jsonl。

由 douyin_fetch.py 拉起，也可以单独跑。输入 JSON 是列表:
  {"rank", "video_id", "audio", "segments_path", "segments_file"}

已有 transcripts.jsonl 里 status 为 ok 或 no_speech 的条目默认跳过，--force 才重跑。

用法（在技能根目录）:
  python3 scripts/asr_worker.py --input <jobs.json> --jsonl <transcripts.jsonl> \\
      [--model small] [--force] [--asr-allow-download]

--model 可以是模型名（默认 small）或本地模型目录，也可用环境变量 GEO_ASR_MODEL。
默认先离线加载（缓存里有就用）。缓存没有时，只有加了 --asr-allow-download 才联网下载。

依赖:
  faster-whisper                 pip install faster-whisper
可选:
  opencc-python-reimplemented    pip install opencc-python-reimplemented
  导入失败则保留简体 initial_prompt，结果里 t2s 为 false。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

DONE_STATUS = {"ok", "no_speech"}
SIMPLIFIED_PROMPT = "以下是普通话的句子，使用简体中文。"


def load_t2s():
    """Return an OpenCC t2s converter, or None if opencc is not installed."""
    try:
        from opencc import OpenCC
    except Exception:
        print(
            "未安装 opencc，转写保留简体 initial_prompt，结果 t2s=false。pip install opencc-python-reimplemented",
            flush=True,
        )
        return None
    try:
        return OpenCC("t2s")
    except Exception as exc:
        print(
            f"opencc 已安装但 t2s 初始化失败：{type(exc).__name__}: {exc}。结果 t2s=false。",
            flush=True,
        )
        return None


def to_simplified(converter, text: str) -> str:
    if converter is None or not text:
        return text
    return converter.convert(text)


def load_done(jsonl: Path) -> set[tuple[int, str]]:
    done: set[tuple[int, str]] = set()
    if not jsonl.is_file():
        return done
    with jsonl.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("status") in DONE_STATUS:
                try:
                    done.add((int(row.get("rank")), str(row.get("video_id"))))
                except (TypeError, ValueError):
                    continue
    return done


def append_row(jsonl: Path, row: dict) -> None:
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    with jsonl.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.flush()


def transcribe_one(model, job: dict, model_name: str, converter) -> dict:
    audio = job["audio"]
    t0 = time.perf_counter()
    segments_iter, info = model.transcribe(
        audio,
        language="zh",
        vad_filter=True,
        beam_size=5,
        condition_on_previous_text=False,
        initial_prompt=SIMPLIFIED_PROMPT,
    )
    t2s = converter is not None
    segs = []
    parts = []
    for seg in segments_iter:
        text = to_simplified(converter, (seg.text or "").strip())
        segs.append(
            {
                "start": round(float(seg.start), 3),
                "end": round(float(seg.end), 3),
                "text": text,
            }
        )
        if text:
            parts.append(text)
    text = to_simplified(converter, "".join(parts))
    duration = getattr(info, "duration", None)
    if duration is not None:
        duration = round(float(duration), 3)
    status = "ok" if text else "no_speech"
    seg_path = Path(job["segments_path"])
    seg_path.parent.mkdir(parents=True, exist_ok=True)
    seg_path.write_text(json.dumps(segs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    row = {
        "rank": int(job["rank"]),
        "video_id": str(job["video_id"]),
        "status": status,
        "duration_audio": duration,
        "chars": len(text),
        "text": text,
        "source": f"faster-whisper-{model_name}",
        "segments_file": job.get("segments_file"),
        "transcriptReviewStatus": "pending",
        "t2s": t2s,
        "elapsed_sec": round(time.perf_counter() - t0, 3),
    }
    return row


class ModelLoadError(Exception):
    pass


def load_whisper_model(model_name: str, allow_download: bool):
    """Load faster-whisper. Try the cache first; download only when allowed."""
    from faster_whisper import WhisperModel

    kwargs = {"device": "cpu", "compute_type": "int8"}
    local = Path(model_name).expanduser()
    if local.is_dir():
        try:
            return WhisperModel(str(local), **kwargs)
        except Exception as exc:
            raise ModelLoadError(
                f"加载本地 ASR 模型目录 {local} 失败（{type(exc).__name__}: {exc}）。"
            ) from exc

    def call(local_files_only: bool):
        try:
            return WhisperModel(model_name, local_files_only=local_files_only, **kwargs)
        except TypeError as exc:
            if "local_files_only" not in str(exc):
                raise
            return WhisperModel(model_name, **kwargs)

    old = os.environ.get("HF_HUB_OFFLINE")
    os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        return call(True)
    except ModelLoadError:
        raise
    except Exception as offline_exc:
        if not allow_download:
            raise ModelLoadError(
                f"离线加载 ASR 模型 {model_name} 失败（{type(offline_exc).__name__}: {offline_exc}）。"
                "缓存里没有该模型。加上 --asr-allow-download 才会联网下载，"
                "或用 --asr-model / GEO_ASR_MODEL 指定本地模型目录。"
            ) from offline_exc
    finally:
        if old is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = old

    os.environ.pop("HF_HUB_OFFLINE", None)
    try:
        return call(False)
    except Exception as exc:
        raise ModelLoadError(
            f"联网下载 ASR 模型 {model_name} 失败（{type(exc).__name__}: {exc}）。"
            "可改用 --asr-model / GEO_ASR_MODEL 指定本地模型目录。"
        ) from exc
    finally:
        if old is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = old


def fail_jobs(jsonl: Path, jobs: list, model_name: str, error: str) -> None:
    for job in jobs:
        rank = int(job["rank"])
        vid = str(job["video_id"])
        row = {
            "rank": rank,
            "video_id": vid,
            "status": "fail",
            "duration_audio": None,
            "chars": 0,
            "text": "",
            "source": f"faster-whisper-{model_name}",
            "segments_file": job.get("segments_file"),
            "transcriptReviewStatus": "pending",
            "t2s": False,
            "error": error,
        }
        append_row(jsonl, row)
        print(f"ASR rank={rank:02d} video_id={vid} status=fail", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="faster-whisper 批量转写（模型只加载一次）")
    parser.add_argument("--input", required=True, help="待转写列表 JSON")
    parser.add_argument("--jsonl", required=True, help="增量结果 jsonl")
    parser.add_argument(
        "--model",
        default=os.environ.get("GEO_ASR_MODEL", "small"),
        help="模型名或本地模型目录。也可用环境变量 GEO_ASR_MODEL。默认 small",
    )
    parser.add_argument("--force", action="store_true", help="已完成的 ok/no_speech 也重跑")
    parser.add_argument(
        "--asr-allow-download",
        action="store_true",
        help="本地缓存没有模型时允许联网下载。默认只离线加载",
    )
    args = parser.parse_args()

    jobs = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if not isinstance(jobs, list):
        print("input 必须是列表", file=sys.stderr, flush=True)
        return 2
    jsonl = Path(args.jsonl)
    done = set() if args.force else load_done(jsonl)
    pending = []
    for job in jobs:
        key = (int(job["rank"]), str(job["video_id"]))
        if key in done:
            print(f"skip asr rank={key[0]:02d} video_id={key[1]} reason=already ok or no_speech", flush=True)
            continue
        audio = Path(job["audio"])
        if not audio.is_file() or audio.stat().st_size <= 0:
            row = {
                "rank": key[0],
                "video_id": key[1],
                "status": "skipped_no_audio",
                "duration_audio": None,
                "chars": 0,
                "text": "",
                "source": f"faster-whisper-{args.model}",
                "segments_file": None,
                "transcriptReviewStatus": "pending",
                "t2s": False,
                "error": "音频文件不存在或为空",
            }
            append_row(jsonl, row)
            print(f"ASR rank={key[0]:02d} status=skipped_no_audio", flush=True)
            continue
        pending.append(job)

    if not pending:
        print("ASR no pending jobs", flush=True)
        return 0

    print(
        f"ASR loading model={args.model} device=cpu compute_type=int8 allow_download={args.asr_allow_download}",
        flush=True,
    )
    try:
        model = load_whisper_model(args.model, args.asr_allow_download)
    except ModelLoadError as exc:
        print(f"ASR model load failed: {exc}", flush=True)
        fail_jobs(jsonl, pending, args.model, str(exc))
        return 1
    except Exception as exc:  # noqa: BLE001 — missing package or unexpected loader error
        text = f"加载 ASR 模型失败（{type(exc).__name__}: {exc}）。"
        print(f"ASR model load failed: {text}", flush=True)
        fail_jobs(jsonl, pending, args.model, text)
        return 1

    converter = load_t2s()
    print(
        f"ASR model ready model={args.model} device=cpu compute_type=int8 "
        f"allow_download={args.asr_allow_download} t2s={converter is not None}",
        flush=True,
    )
    rc = 0
    for job in pending:
        rank = int(job["rank"])
        vid = str(job["video_id"])
        try:
            row = transcribe_one(model, job, args.model, converter)
        except Exception as exc:  # noqa: BLE001 — one bad file must not drop the batch
            row = {
                "rank": rank,
                "video_id": vid,
                "status": "fail",
                "duration_audio": None,
                "chars": 0,
                "text": "",
                "source": f"faster-whisper-{args.model}",
                "segments_file": job.get("segments_file"),
                "transcriptReviewStatus": "pending",
                "t2s": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
            rc = 1
        append_row(jsonl, row)
        print(
            f"ASR rank={rank:02d} video_id={vid} status={row['status']} chars={row['chars']}",
            flush=True,
        )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
