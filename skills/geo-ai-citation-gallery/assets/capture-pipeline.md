# 画面与媒体抓取流水线（抖音 / 短视频）

> **可选深读 / 仅调试用。** 正常交付按主 `SKILL.md` 第 2 节步骤即可；队友不用先读本文。下文是画面抓取伪代码与本机小服务细节。


本文是主 [`SKILL.md`](../SKILL.md) 第 2 节第 3 步「抓画面」的展开说明。目标：在**尽量免账号登录**的前提下，拿到详情卡用的画面帧与可选互动元数据。成功率不保证；失败标缺口，禁止编造。

## 与交付物的分工

| 步骤 | 产物 | 谁做 | 登录抖音？ |
|------|------|------|------------|
| A. 引用清单 | TopN URL、应用次数 / 应用率 | 读 GEO 诊断包（xlsx/csv） | **否** |
| B. 画面 + 部分 meta | `shots/`、metadata JSONL、`capture_progress` | 浏览器 + 本机小服务 / 脚本 | 多数公开分享页可未登录；遇墙则停 |
| C. 互动补全 | `engagement.json`（赞/藏/转/粉/时长等） | 同 B，或人工补 | 同上；空 / 假 0 需重试或排除出图 |
| D. 出页 | 套 `template.html` → `index.html` | 任意能读 skill 的 AI | 不需要 |

**优先推荐**：人 / 专用脚本先把 B+C 出齐，再让模型只做 D。纯无浏览器的编码模型不要硬编截图。

## 目录约定

以项目根为 `<PROJECT>`（占位，勿写死客户路径）：

```text
<PROJECT>/
  shots/                 # 画面帧 PNG
    01_1.png             # 排名 01，第 1 帧
    01_2.png
    02_1.png
    ...
  work/                  # 抓取工作区
    capture_progress.txt # 每行：rank status kind note
    metadata.jsonl       # 每行一条样本 meta（可追加）
    engagement.json      # 互动汇总（可选）
    tmp_<rank>.mp4       # 口播临时视频（用完删）
  gallery/
    images/              # 交付时从 shots/ 拷贝或软链
    index.html
```

- 文件名：`NN_k.png` —— `NN` 两位排名，`k` 从 1 起的帧序号。
- 图文：尽量多帧（页面露出几张下几张）。
- 口播：至少前几帧；抓不到视频时可回退 poster / 封面为 `_1.png`，并在 progress 注明。

## 已验证链路（免账号）

```text
诊断包 TopN
  → 浏览器打开公开分享页
  → DOM / 网络捞出图床或视频 media URL（非创作者后台）
  → 本机小服务：rank + meta + media URL
  → 图文：直接下载图片 → shots/NN_k.png
     口播：下载 mp4 → ffmpeg 抽帧 → 可回退 poster
  → 写 capture_progress + metadata.jsonl
```

### 下载头

请求媒体 CDN 时带：

- 常见浏览器 `User-Agent`
- `Referer: https://www.douyin.com/`

缺 Referer 时常见 **403**。

### 进度与失败写法

`capture_progress.txt` 示例：

```text
1 ok image files=8
7 ok image files=4 (partial; remaining URLs 403)
8 fail video source unavailable; page JS exposes no downloadable media URL
16 fail video source unavailable in DOM; no target cover URL exposed
37 ok video poster plus 2 frames
```

页面展示：

- 有帧 → 正常缩略图
- 无帧 / 失败 → **「暂未抓取到」** 或缺口标注
- **禁止**编造帧图、假互动数；真实 `0` 与缺失必须分开（见 SKILL 数字口径）

## 本机接收服务（简化思路 / 伪代码）

实操可用本机 `127.0.0.1` HTTP 小服务：浏览器书签 / 控制台把 meta 与 media URL POST/GET 过来，服务端下载并抽帧。以下为**通用占位版**，无密钥、无客户路径。

```python
# 伪代码：capture_server 思路（勿提交真实客户 BASE 路径）
import http.server, json, os, urllib.request, subprocess

PROJECT = os.environ.get("CAPTURE_PROJECT", "./capture_out")
SHOTS = os.path.join(PROJECT, "shots")
WORK = os.path.join(PROJECT, "work")
os.makedirs(SHOTS, exist_ok=True)
os.makedirs(WORK, exist_ok=True)

pending = {}  # rank -> {kind, media[], poster, ...meta}

def fetch(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.douyin.com/",
        },
    )
    return urllib.request.urlopen(req, timeout=25).read()

def finish(rank: int) -> dict:
    d = pending.pop(rank, {"rank": rank})
    kind = d.get("kind")
    media = d.get("media") or []
    files, errs = [], []

    if kind == "image":
        for i, u in enumerate(dict.fromkeys(media), 1):
            try:
                save_png(fetch(u), f"{SHOTS}/{rank:02d}_{i}.png")
                files.append(f"{rank:02d}_{i}.png")
            except Exception:
                errs.append(f"img{i}")  # 常见：CDN 403

    elif kind == "video":
        v = media[0] if media else ""
        if not v:
            errs.append("no_video")
        else:
            tmp = f"{WORK}/tmp_{rank}.mp4"
            try:
                open(tmp, "wb").write(fetch(v))
                # 抽前几帧；也可 select=eq(n\,0)+eq(n\,1)
                subprocess.run(
                    [
                        "ffmpeg", "-loglevel", "error", "-y", "-i", tmp,
                        "-vf", "select=eq(n\\,0)+eq(n\\,1)",
                        "-vsync", "vfr",
                        f"{SHOTS}/{rank:02d}_%d.png",
                    ],
                    timeout=45,
                    check=False,
                )
                files = sorted(
                    x for x in os.listdir(SHOTS)
                    if x.startswith(f"{rank:02d}_") and x.endswith(".png")
                )
                if len(files) < 2 and d.get("poster"):
                    try:
                        save_png(fetch(d["poster"]), f"{SHOTS}/{rank:02d}_1.png")
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

    status = "ok" if files else "fail"
    append_jsonl(f"{WORK}/metadata.jsonl", {**d, "images_saved": files, "status": status, "errors": errs})
    append_line(
        f"{WORK}/capture_progress.txt",
        f"{rank} {status} {kind or 'unknown'} files={len(files)}"
        + ((" " + ",".join(errs)) if errs else ""),
    )
    return {"rank": rank, "status": status, "files": files, "errors": errs}

# HTTP：/meta?rank=&d=<base64-json>  → 登记 meta
#       /media?rank=&u=<media_url>   → 追加媒体 URL
#       /finish?rank=                → 下载 / 抽帧 / 写进度
# 仅绑 127.0.0.1；不要对公网暴露。
```

浏览器侧（示意）：在公开分享页打开控制台，从 DOM / `performance` / 网络里找出图片 CDN 或 `video`/`source` URL，再：

```javascript
// 示意：把捞到的 URL 交给本机服务（端口自定）
fetch('http://127.0.0.1:8765/meta?rank=3&d=' + btoa(unescape(encodeURIComponent(JSON.stringify(meta)))));
mediaUrls.forEach(u => fetch('http://127.0.0.1:8765/media?rank=3&u=' + encodeURIComponent(u)));
fetch('http://127.0.0.1:8765/finish?rank=3');
```

依赖：`ffmpeg`（口播抽帧）、可选 `Pillow`（统一存 PNG）。**不要**把 cookie、账号、API key 写进仓库或页面。

## 已知失败模式 → 怎么处理

| 现象 | 处理 |
|------|------|
| CDN 403 | 换 URL / 补 Referer；仍失败则 partial + 缺口 |
| 页面不暴露可下载视频地址 | `fail` + 原因；可试封面；或转人工 |
| 只抓到部分帧 / 仅 poster | progress 注明；页面照常展示已有帧 |
| 互动空或假全 0 | 重试；散点图排除并脚注「未计入」 |
| 登录墙 / 验证码 | **停**；标缺口或转人工，勿绕过 |

## 与 template 的衔接

1. 将 `shots/NN_k.png` 拷到画廊 `images/`（或按模板相对路径约定）。
2. 在 `data` / `STATS` 里为每条样本填：
   - `images`: `["images/01_1.png", ...]`；无则空数组 + 文案「暂未抓取到」
   - 互动字段：有则填数字；无则 `null` / 缺省，UI 显示「暂未抓取到」（不是 `0`，除非页面确认是 0）
3. 套 [`template.html`](template.html)，过 SKILL 校验清单后发布。

字段细节见 [`feature-stats.schema.md`](feature-stats.schema.md)。

## 给其他 AI 的最短决策树

```text
有现成 shots/ + engagement？
  ├─ 是 → 只套模板出页
  └─ 否 → 有浏览器 / Computer Use / 本机脚本？
        ├─ 是 → 按本文链路抓；写 progress；失败标缺口
        └─ 否 → 不要编截图；页面一律「暂未抓取到」，并注明需补抓
```
