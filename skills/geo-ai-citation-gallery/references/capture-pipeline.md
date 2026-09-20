# 抓画面执行手册（推荐其他 AI 打开）

> **给 Activity / ChatGPT / Antigravity / 其它执行 AI 的操作手册。** 按本文件 + `scripts/` 即可独立完成抓画面，不必猜协议。 可运行脚本在 [`scripts/`](scripts/)：`capture_server.py`、`page_hook.example.js`、`download_one.py`。  
> 主流程摘要见 [`SKILL.md`](../SKILL.md)；标签细则见 [`hashtags.md`](hashtags.md)。

目标：在**尽量免账号登录**的前提下，拿到详情卡用的画面帧与可选互动元数据。**成品图来自脚本下载，不是浏览器截屏。** 成功率不保证；失败标缺口，禁止编造。

## 与交付物的分工

| 步骤 | 产物 | 谁做 | 登录抖音？ |
|------|------|------|------------|
| A. 引用清单 | TopN URL、引用次数 / 引用率 | 读 GEO 诊断包（xlsx/csv） | **否** |
| A2. 标签 | `hashtags` ≤ **5**（抖音上限）；超额截断 | 公开页或已有字段 | 否 |
| B. 画面 + 部分 meta | `shots/`、metadata JSONL、`capture_progress` | **A** `scripts/capture_server.py` + **B** 浏览器捞 URL（见 SKILL 步骤 3） | 多数公开分享页可未登录；遇墙则停 |
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

## 有头 / 无头 + 抓取方式（说人话）

- **下图片/视频本身**：不是浏览器整页截屏。打开公开页后把图床/视频地址捞出来，用 HTTP 下载（口播再 ffmpeg 抽帧）。这一步无所谓有头无头。
- **打开抖音页**：需要浏览器自动化；有头可看、遇登录/验证码方便人接手；无头在公开页能开且能捞到媒体 URL 时往往够用。
- **不绑死**：有浏览器自动化即可；**无头优先**；遇墙再转有头或人工。
- **主路径**是「进页抽媒体 URL」，不是纯无头截整页。

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

## 可运行脚本（不要再抄伪代码）

路径均相对 **skill 根**（本文件所在目录的上一级）：

| 文件 | 作用 |
|------|------|
| [`scripts/capture_server.py`](scripts/capture_server.py) | 本机 `127.0.0.1:8765`：`/meta` `/media` `/finish`；Referer+UA 下载；图文 PNG；口播 ffmpeg 抽帧；写 `shots/`、`work/capture_progress.txt`、`work/metadata.jsonl` |
| [`scripts/page_hook.example.js`](scripts/page_hook.example.js) | 浏览器控制台/注入：从 `<img>`、背景、`video`、performance、常见 CDN 提示捞 URL，再 fetch 本机 |
| [`scripts/download_one.py`](scripts/download_one.py) | 单条 URL 带 Referer 试下载（可选） |
| [`scripts/fetch_engagement.py`](scripts/fetch_engagement.py) | **互动补全**：Playwright 公开页读 `data-e2e` 赞/藏/转/粉/时长 → `work/engagement.json` |

### 启动

```bash
pip install pillow
# 确认 ffmpeg 在 PATH
CAPTURE_PROJECT=/path/to/<PROJECT> python scripts/capture_server.py
```

`CAPTURE_PROJECT` 默认 = `cwd/capture_out`。仅绑回环，勿对公网暴露。

### 浏览器侧（每条公开页）

1. 打开公开分享页（无头优先；遇墙停）。
2. 改 `page_hook.example.js` 里的 `RANK` / `KIND`（图文=`image`，口播=`video`+可选 poster）后运行，或由 Antigravity `/browser` 等价执行。
3. 钩子会：`/meta` → 多条 `/media` → `/finish`。
4. 看 `shots/NN_*.png` 与 `work/capture_progress.txt`。

meta 用 urlsafe-base64 JSON（与现网一致）；下载头：`User-Agent` + `Referer: https://www.douyin.com/`（缺 Referer 易 403）。

依赖：`ffmpeg`（口播）、可选 `Pillow`。**不要**把 cookie、账号、API key 写进仓库或页面。


## C. 互动补全（赞 / 藏 / 转 / 粉 / 时长）

> 2026-09-19 康丽根 Top50 验证：digg **45/50**、collect **43/50**、share **41/50**、duration **47/50**；公开页 Playwright，**不登录、不编造数字**。

### 何时跑

画廊 `gallery/data.json` 已有 `rank` + `video_id`（封面可先空）后跑。封面补抓与互动可分开。

### 命令

```bash
# 在 skill 根目录；--package 指向分析包根（含 gallery/data.json）
pip install playwright && playwright install chromium   # 首次
python scripts/fetch_engagement.py --package /path/to/<PROJECT>
# 遇墙观察：加 --headed
# 只重试 digg 仍为 null：加 --retry-failed
```

产物：

- `work/engagement.json` / `engagement.jsonl` / `engagement_progress.txt`
- 合并进 `gallery/data.json` 的 `likes` / `favorites` / `shares` / `followers` / `duration`（字段名以模板为准）后重出 `index.html`

### URL 试探顺序（同一 video_id）

1. `https://www.douyin.com/note/{id}`（图文/笔记优先）
2. `https://www.douyin.com/video/{id}`
3. `https://www.douyin.com/jingxuan?modal_id={id}`（modal）
4. `https://www.iesdouyin.com/share/video/{id}`（分享页兜底）

note/video 已拿到 digg+collect 且标题非「记录美好生活」→ 可提前停。遇登录墙 → **停该条**，UI 写「暂未抓取到」，禁止绕过。

### DOM（`data-e2e`）

在 `note-detail` / `feed-active-video` / `modal-video-container` 作用域内读：

| 选择器 | 字段 |
|--------|------|
| `video-player-digg` | 赞 |
| `video-player-collect` | 收藏 |
| `video-player-share` | 分享 |
| `feed-comment-icon` | 评论（可选） |
| `user-info` / `feed-video-nickname` | 账号名、粉丝文案 |
| `video` 元素 `duration` 或 `mm:ss / mm:ss` | 时长（秒） |

解析：`12.3万` / `1.2千` → 整数；纯文案「赞」「收藏」「分享」**无数字** → 不是缺失，按**平台零互动展示**可记 `0`（见下）。

### pick_best 规则（易踩坑）

- 优先序：note > video > modal > share
- **有 digg/collect 时不要因 `error-page` 标记整条丢弃**（常见误标，会把好数据扔掉）
- 登录墙：整条 `login_wall`，字段保持 `null` → 页面「暂未抓取到」
- 通用标题「记录美好生活」降权，避免 modal 串号

### 数字口径（与 SKILL 一致，补一条）

| 情况 | 写入 | 页面文案 |
|------|------|----------|
| DOM 读到数字（含真实 0） | 整数 | 数字 |
| 仅图标文案「赞｜收藏｜分享」、旁无位数 | `0` + source 注明「平台零互动展示」 | `0` |
| 登录墙 / 未打开详情 / 选择器全空 | `null` | **暂未抓取到**（禁止填假 0） |
| 散点/相关分析 | 只计入有真实数字的点；脚注排除未抓到的 | — |

### 合并回画廊

把 `engagement.json` 按 `rank` / `video_id` merge 进 `data.json`，再套模板或刷新已有 `index.html`。缺字段保持「暂未抓取到」。合并后重发 here.now / 团队域名挂载。

### 封面补抓（顺带）

诊断包里的小图标（如 32×32）不能当封面。应用抖音 CDN 大图重下；交付前检查 **min(宽,高) ≥ 360**。缺封面 →「暂未抓取到」，禁止用占位假图充数。

### 发布与团队域名挂载（可选）

1. here.now：用既有 `publish.sh --slug <slug>` 更新同一 slug（如兔宝宝 `still-mill-xbe8`、康丽根 `lilac-riddle-e652`）。
2. `news.skygeoapp.com`：`POST /api/v1/mounts`，`mount_path` + `slug` + `domain=news.skygeoapp.com`（例：`tubao-top50` → still-mill；`kangligeng-douyin-top50` → lilac-riddle）。挂载后核对 **200**；若短暂 404，再发一次 slug 或确认 mount 生效。


## 已知失败模式 → 怎么处理

| 现象 | 处理 |
|------|------|
| CDN 403 | 换 URL / 补 Referer；仍失败则 partial + 缺口 |
| 页面不暴露可下载视频地址 | `fail` + 原因；可试封面；或转人工 |
| 只抓到部分帧 / 仅 poster | progress 注明；页面照常展示已有帧 |
| 互动空或假全 0 | 跑 `fetch_engagement.py --retry-failed`；仍空保持「暂未抓取到」；散点排除并脚注 |
| 登录墙 / 验证码 | **停**；标缺口或转人工，勿绕过 |

## 与 template 的衔接

1. 将 `shots/NN_k.png` 拷到画廊 `images/`（或按模板相对路径约定）。
2. 在 `data` / `STATS` 里为每条样本填：
   - `images`: `["images/01_1.png", ...]`；无则空数组 + 文案「暂未抓取到」
   - 互动字段：有则填数字；无则 `null` / 缺省，UI 显示「暂未抓取到」（不是 `0`，除非页面确认是 0）
3. 套 [`../assets/template.html`](../assets/template.html)，过 [`qa-checklist.md`](qa-checklist.md) 后发布。

字段细节见 [`feature-stats.schema.md`](feature-stats.schema.md)。

## 给其他 AI 的最短决策树

```text
有现成 shots/ + engagement？
  ├─ 是 → 只套模板出页
  └─ 否 → 有浏览器 / Antigravity / Computer Use + 能跑 scripts/？
        ├─ 是 → 启 capture_server + page_hook 捞画面；
        │       再跑 fetch_engagement.py 补赞/藏；失败标缺口
        └─ 否 → 不要编截图/互动数；页面一律「暂未抓取到」，并注明需补抓
```


## 标签（与 SKILL 一致）

抖音单条最多 **5** 个话题标签。抓 meta 时 `hashtags` 截断到 5；超额保留可选 `hashtags_raw`，并设 `hashtags_truncated: true`。


## 标签截断

细则见 [`hashtags.md`](hashtags.md)。可执行：

```bash
python scripts/normalize_hashtags.py path/to/meta.json -i
```
