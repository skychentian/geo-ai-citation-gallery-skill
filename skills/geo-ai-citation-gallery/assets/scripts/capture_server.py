#!/usr/bin/env python3
"""
本机媒体接收服务：浏览器把公开页里捞到的图片/视频 CDN URL 打过来，本机 HTTP 下载落盘。

启动（在项目根或任意目录）：
  pip install pillow          # 图文转 PNG 需要
  # 确认 ffmpeg 在 PATH（口播抽帧需要）
  CAPTURE_PROJECT=/path/to/project python capture_server.py

环境变量：
  CAPTURE_PROJECT  输出根目录，默认 = 当前工作目录下的 capture_out
                   会创建 <PROJECT>/shots/ 与 <PROJECT>/work/

绑定：仅 127.0.0.1:8765（勿对公网暴露）

端点（与现网一致，GET + query）：
  /meta?rank=N&d=<urlsafe-base64-json>   登记 meta（kind/poster/caption 等），清空该 rank 的 media 列表
  /media?rank=N&u=<media_url>            追加一条媒体 URL
  /finish?rank=N                         下载 / 抽帧 / 写 progress + metadata.jsonl

meta JSON 常用字段：
  kind: "image" | "video"
  poster: 可选封面 URL（口播抽帧不足时回退）
  其它字段原样写入 metadata.jsonl

图文：逐 URL 下载 → shots/NN_k.png
口播：下载首条 media 为 mp4 → ffmpeg 抽前两帧 → 不足则试 poster
"""
from __future__ import annotations

import base64
import http.server
import io
import json
import os
import subprocess
import urllib.parse
import urllib.request

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore

PROJECT = os.environ.get("CAPTURE_PROJECT") or os.path.join(os.getcwd(), "capture_out")
SHOTS = os.path.join(PROJECT, "shots")
WORK = os.path.join(PROJECT, "work")
os.makedirs(SHOTS, exist_ok=True)
os.makedirs(WORK, exist_ok=True)

PENDING: dict[int, dict] = {}

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
REFERER = "https://www.douyin.com/"


def fetch(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Referer": REFERER},
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        return resp.read()


def save_png(data: bytes, path: str) -> None:
    if Image is None:
        raise RuntimeError("Pillow not installed; run: pip install pillow")
    Image.open(io.BytesIO(data)).convert("RGB").save(path, "PNG")


def finish(rank: int) -> dict:
    d = PENDING.pop(rank, {"rank": rank})
    kind = d.get("kind")
    media = d.get("media") or []
    files: list[str] = []
    errs: list[str] = []

    if kind == "image":
        for i, u in enumerate(dict.fromkeys(media), 1):
            try:
                out = os.path.join(SHOTS, f"{rank:02d}_{i}.png")
                save_png(fetch(u), out)
                files.append(f"{rank:02d}_{i}.png")
            except Exception:
                errs.append(f"img{i}")

    elif kind == "video":
        v = media[0] if media else ""
        if not v:
            errs.append("no_video")
        else:
            tmp = os.path.join(WORK, f"tmp_{rank}.mp4")
            try:
                with open(tmp, "wb") as f:
                    f.write(fetch(v))
                subprocess.run(
                    [
                        "ffmpeg",
                        "-loglevel",
                        "error",
                        "-y",
                        "-i",
                        tmp,
                        "-vf",
                        r"select=eq(n\,0)+eq(n\,1)",
                        "-vsync",
                        "vfr",
                        os.path.join(SHOTS, f"{rank:02d}_%d.png"),
                    ],
                    timeout=45,
                    check=False,
                )
                files = sorted(
                    x
                    for x in os.listdir(SHOTS)
                    if x.startswith(f"{rank:02d}_") and x.endswith(".png")
                )
                if len(files) < 2 and d.get("poster"):
                    try:
                        save_png(fetch(d["poster"]), os.path.join(SHOTS, f"{rank:02d}_1.png"))
                        files = [f"{rank:02d}_1.png"]
                    except Exception:
                        pass
            except Exception:
                errs.append("video")
            finally:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
    else:
        errs.append("no_media")

    # 有落盘帧即 ok（口播仅 poster 回退也算 ok，细节写在 errors）
    status = "ok" if files else "fail"

    d.update(
        {
            "rank": rank,
            "images": media if kind == "image" else [],
            "images_saved": sorted(files),
            "status": status,
        }
    )
    if errs:
        d["errors"] = errs

    with open(os.path.join(WORK, "metadata.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")
    with open(os.path.join(WORK, "capture_progress.txt"), "a", encoding="utf-8") as f:
        note = f"{rank} {d['status']} {kind or 'unknown'} files={len(files)}"
        if errs:
            note += " " + ",".join(errs)
        f.write(note + "\n")
    return d


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):  # quiet
        pass

    def do_GET(self):
        try:
            parts = urllib.parse.urlsplit(self.path)
            q = urllib.parse.parse_qs(parts.query)
            path = parts.path
            rank = int(q.get("rank", ["0"])[0])

            if path == "/meta":
                raw = base64.urlsafe_b64decode(q["d"][0] + "===")
                PENDING[rank] = json.loads(raw)
                PENDING[rank]["rank"] = rank
                PENDING[rank]["media"] = []
                out = "meta"
            elif path == "/media":
                PENDING.setdefault(rank, {"rank": rank, "media": []})
                PENDING[rank].setdefault("media", []).append(q["u"][0])
                out = "media"
            elif path == "/finish":
                out = json.dumps(finish(rank), ensure_ascii=False)
            else:
                out = "ok"

            body = out.encode("utf-8")
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            msg = str(e).encode("utf-8")
            self.send_response(500)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)


def main() -> None:
    print(f"CAPTURE_PROJECT={PROJECT}")
    print(f"shots -> {SHOTS}")
    print(f"work  -> {WORK}")
    print("listening on http://127.0.0.1:8765  (/meta /media /finish)")
    http.server.ThreadingHTTPServer(("127.0.0.1", 8765), Handler).serve_forever()


if __name__ == "__main__":
    main()
