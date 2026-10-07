# 抓画面执行手册（推荐其他 AI 打开）

> **给 Activity / ChatGPT / Antigravity / 其它执行 AI 的操作手册。** 按本文件 + `scripts/` 即可独立完成抓画面，不必猜协议。 可运行脚本在 [`scripts/`](../scripts/)：`douyin_fetch.py`、`capture_server.py`、`page_hook.example.js`、`download_one.py`。
> 主流程摘要见 [`SKILL.md`](../SKILL.md)；标签细则见 [`hashtags.md`](hashtags.md)。

目标：在**尽量免账号登录**的前提下，拿到详情卡用的画面帧与可选互动元数据。**成品图来自脚本下载，不是浏览器截屏。** 成功率不保证；失败标缺口，禁止编造。

## 默认：无头脚本 douyin_fetch.py

在技能根目录执行：

```bash
python3 scripts/douyin_fetch.py --package <分析包> --out <包>/work/douyin_fetch [--limit N]
```

常用参数：`--ranks 1,2,5`、`--no-asr`、`--no-video`、`--asr-model small`（模型名或本地目录）、`--asr-allow-download`（缓存没有模型时才联网下载）、`--frames 4`、`--sleep 4-8`、`--retries 2`、`--video-quality lowest|highest`、`--force`、`--headed`、`--chrome`、`--whisper-python`。环境变量：`GEO_CHROME`、`GEO_WHISPER_PYTHON`、`GEO_ASR_MODEL`。

依赖：`playwright`，以及 chromium 或本机 Chrome（没有就用 Playwright 自带 chromium）；`Pillow`；`ffmpeg` / `ffprobe`。转写可选：`pip install faster-whisper`。繁转简可选：`pip install opencc-python-reimplemented`。找不到 faster-whisper 时，视频 transcript 记 `skipped_no_asr`，其余抓取照常，不因此退出。

原理：无头打开公开页 `jingxuan?modal_id=` / `note/`，读服务端 HTML 里的作品数据；不登录、不带 cookie、不点击、不处理验证码。

产出与画廊文件的映射：

| 脚本产出 | 画廊 / 工作区 |
|---|---|
| `items.json` 的 `title`、`original_desc`、`hashtags`、`account` / `account_name`、`follower_count`、`digg_count`、`collect_count`、`share_count`、`comment_count`、`content_type`、`duration_sec`、`image_count`、`images`、`publish_date`、`transcript` | `gallery/data.json` 同名字段。`content_type` 脚本只分「图文 / 视频」；视频要细分口播 / 混剪，需人工或分析阶段判断。`duration_sec` 图文为 null，背景音乐时长在 `music_duration_sec` |
| `media/NN/NN_k.jpg`（图文原图，按发帖顺序）、`NN_cover.jpg`、`NN_fK.jpg`（视频抽帧，带 `timestamp_sec`） | `shots/` 和 `gallery/images/`（需要时转 PNG 或改名） |
| `engagement.json` | `work/engagement.json`（字段同名） |
| `transcripts.jsonl` | `work/transcripts.jsonl`（字段同名，`transcriptReviewStatus=pending`） |
| `field_status.json`、`coverage.json` | `capture-ledger.json`、`coverage.json` 的素材。字段不完全相同：缺 per-field 的 `value` / `source_url` / `observed_at` / `attempts`。系统 v3 回传前仍需转换 |

### 合并进分析包

抓取完成后用 `scripts/merge_fetch.py` 把产出合并进分析包，不要手改 `data.json`。

```bash
# 在技能根目录。先看差异，确认后再写入。
python3 scripts/merge_fetch.py --package <分析包> --fetch <douyin_fetch 输出目录> --dry-run
python3 scripts/merge_fetch.py --package <分析包> --fetch <douyin_fetch 输出目录>
```

- `--dry-run` 只把差异摘要打到标准输出，不写盘。确认后再去掉它真跑。
- 默认只填空（`null`、空字符串、空列表、「暂未抓取到」、「暂未获取」），不覆盖已有人工值。两边都有值且不同记「冲突（未覆盖）」。字符串只差空白（换行、连续空格、首尾空格）视为相同，不记冲突，`--overwrite` 也不改。
- `--overwrite`：脚本有可靠值时覆盖人工值，报告列出旧值 → 新值。`content_type` 只在人工为空时填，不覆盖。
- `--overwrite-fields`：只覆盖列出的字段，其他字段仍只填空。例如 `--overwrite-fields original_desc`。未知字段名报错退出。与 `--overwrite` 同时给出时，以 `--overwrite`（全部可写字段）为准，并在报告里写明。
- 写入前把 `gallery/data.json` 备份为同目录 `data.json.bak-merge-YYYYMMDDHHMMSS`。
- 报告写到 `<分析包>/work/merge_fetch/merge-report-YYYYMMDDHHMMSS.md` 和同名 `.json`。
- 新增 `post_title`（平台发布标题，附 `post_title_source`）和 `citation_title`（包内 `_机器可读/top.json` 里同 `video_id` 的 AI 引用标题）。`title` / `title_short` 原样保留。当前模板不读这两个新字段，页面不变；以后要显示再改模板。
- 新增 `post_desc`：平台发布文案全文，取 `items.json` 的 `original_desc`，且 `field_status.desc` 为 ok 才写，默认只填空。`original_desc` 仍按填空 / 覆盖规则处理，不因写入 `post_desc` 而被改掉。模板和 `build_report` 的「发布文案全文」读 `original_desc`。若它与 `citation_title` 相同而 `post_desc` 不同，报告会列出「original_desc 实为诊断包引用标题」；要让页面显示平台真实文案，跑 `--overwrite-fields original_desc`。
- 人工已有 `transcript` 但没有 `transcript_status` 时，补 `transcript_status=pending`。
- 图片复制到 `shots/douyin_fetch/NN/` 留证据。只有 `data.images` 真被写入（空才填，或按覆盖规则替换）时，才同时复制进 `gallery/images/douyin_fetch/NN/`。可补图（未改）只进 shots，不进 images。已有同名文件不覆盖。`--dry-run` 不复制任何文件。视频（mp4 / m4a）默认不复制，仍留在 fetch 输出目录；要复制进 shots 再加 `--shots-video`。

实测（某客户 Top50，2026-10-07）：全部 50 条成功、0 条被挡。全程约 34 分钟（2061 秒，平均约 41 秒/条），不转写约 25 秒/条（含 4–8 秒限速）；前 10 条 535 秒。赞 / 藏 / 转 / 评 / 粉 / 发布日期 50/50。图文 76 张原图。视频 30/30，含 mp4、抽帧、转写。

已知缺口：拿不到播放量。转写是 faster-whisper small 自动转写，同音错字多，必须标「自动转写，待核对」并人工校对。图文 OCR（`image_text`）、`talking_head` / `montage` 细分没做。大批量要分批跑、保持限速，`/video/{id}` 路由易出滑块。

何时退回原手动流程：某条 `status=blocked`（验证码 / 登录墙 / 风控）、关键字段 missing、下载失败、条数不足时，**只对这些失败条目**走下面的兜底流程（`capture_server` + `page_hook`、`fetch_engagement.py`、有头或人工）。已成功的条目不重抓。

对比工具：`python3 scripts/compare_manual.py --package <包> --out <输出目录>`。只读脚本输出和分析包里的手动结果，写出 `compare.json` 和 `compare.md`。

> 以下为兜底流程（原手动浏览器流程，2026-10-08 前的默认方式）：默认脚本失败的条目按下面执行。

## 与交付物的分工

| 步骤 | 产物 | 谁做 | 登录抖音？ |
|------|------|------|------------|
| A. 引用清单 | TopN URL、引用次数 / 引用率 | 读 GEO 诊断包（xlsx/csv） | **否** |
| A2. 标签 | 原始标签完整保留，规范化后完整统计 | 公开页或已有字段 | 否 |
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
    tmp_<rank>.mp4       # 口播过程材料（默认保留）
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
| [`scripts/douyin_fetch.py`](scripts/douyin_fetch.py) | 无头只读抓取公开页：画面、互动、时长、口播；产出 `items.json`、`field_status.json`、`media/` |
| [`scripts/asr_worker.py`](scripts/asr_worker.py) | faster-whisper 批量转写，由 douyin_fetch 拉起或单独跑；默认离线加载模型 |
| [`scripts/compare_manual.py`](scripts/compare_manual.py) | 只读对比脚本产出与分析包里的手动结果，写出 `compare.json`、`compare.md` |
| [`scripts/merge_fetch.py`](scripts/merge_fetch.py) | 把 douyin_fetch 产出合并进 `gallery/data.json` 与 images / shots（默认只填空，`--dry-run` / `--overwrite` / `--overwrite-fields`，先备份再写报告） |

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

> 2026-09-19 某客户 Top50 验证：digg **45/50**、collect **43/50**、share **41/50**、duration **47/50**；公开页 Playwright，**不登录、不编造数字**。

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

解析：`12.3万` / `1.2千` → 整数；纯文案「赞」「收藏」「分享」无数字时记缺失，不能推断为 0。

### pick_best 规则（易踩坑）

- 优先序：note > video > modal > share
- **有 digg/collect 时不要因 `error-page` 标记整条丢弃**（常见误标，会把好数据扔掉）
- 登录墙：整条 `login_wall`，字段保持 `null` → 页面「暂未抓取到」
- 通用标题「记录美好生活」降权，避免 modal 串号

### 数字口径（与 SKILL 一致，补一条）

| 情况 | 写入 | 页面文案 |
|------|------|----------|
| DOM 读到数字（含真实 0） | 整数 | 数字 |
| 仅图标文案「赞｜收藏｜分享」、旁无位数 | `null` + source 注明「仅图标无数字」 | `暂未抓取到` |
| 登录墙 / 未打开详情 / 选择器全空 | `null` | **暂未抓取到**（禁止填假 0） |
| 散点/相关分析 | 只计入有真实数字的点；脚注排除未抓到的 | — |

### 合并回画廊

把 `engagement.json` 按 `rank` / `video_id` merge 进 `data.json`，再套模板或刷新已有 `index.html`。缺字段保持「暂未抓取到」。合并后重新检查本地报告；系统模式由执行器回传，不自动对外发布。

### 封面补抓（顺带）

诊断包里的小图标（如 32×32）不能当封面。应用抖音 CDN 大图重下；交付前检查 **min(宽,高) ≥ 360**。缺封面 →「暂未抓取到」，禁止用占位假图充数。

### 发布与团队域名挂载（仅技术参考）

本工作台默认不对外发布；以下说明不构成授权，必须服从工作台与本次用户明确范围。

1. here.now：用既有 `publish.sh --slug <slug>` 更新同一 slug（使用本次已授权客户的 slug，不复用其他客户）。
2. `news.skygeoapp.com`：`POST /api/v1/mounts`，`mount_path` + `slug` + `domain=news.skygeoapp.com`（使用本次已授权的路径）。挂载后核对 **200**；若短暂 404，再发一次 slug 或确认 mount 生效。


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
3. 套 [`../assets/template.html`](../assets/template.html)，过 [`qa-checklist.md`](qa-checklist.md) 后本地交付；不能自动发布。

字段细节见 [`feature-stats.schema.md`](feature-stats.schema.md)。

## 给其他 AI 的最短决策树

```text
先跑 scripts/douyin_fetch.py（默认）
  ├─ 全部 ok → 用 scripts/merge_fetch.py 合并进 gallery/data.json 与 images / shots（先 --dry-run 再真跑），再套模板出页
  └─ 有 blocked / missing / 下载失败的条目 → 只对这些条目进入下面原有分支（兜底）

有现成 shots/ + engagement？
  ├─ 是 → 只套模板出页
  └─ 否 → 有浏览器 / Antigravity / Computer Use + 能跑 scripts/？
        ├─ 是 → 启 capture_server + page_hook 捞画面；
        │       再跑 fetch_engagement.py 补赞/藏；失败标缺口
        └─ 否 → 不要编截图/互动数；页面一律「暂未抓取到」，并注明需补抓
```


## 标签（与 SKILL 一致）

抓 meta 时完整保存 hashtags_raw；hashtags 仅做规范化去重，分析不截断。展示摘要与分析列表分开。


## 标签规范化

细则见 [`hashtags.md`](hashtags.md)。可执行：

```bash
python scripts/normalize_hashtags.py path/to/meta.json -i
```

## D. 全量补抓与停止条件（2026-09-24，所有执行模型适用）

“尽量抓到”不是只访问前几条：TopN 每条均尝试采集原链/视频ID、账号、发布时间、完整标题、完整发布文案、全部标签、内容类型、点赞、收藏、评论、分享、作者粉丝量、视频实际秒数或图文页数、封面/原图/关键帧。播放量仅在公开来源确实可见时采集，不要求访问创作者私有后台。

对每个字段记 status（ok/partial/missing/not_applicable）、value、source_url、observed_at、attempts、reason；每次尝试记渠道、时间、结果。互动数保留平台原始显示值与规范数值，“1.2万”保留其近似精度。粉丝数来自对应作者主页，不从点赞推算。实际视频秒数来自媒体元数据或播放器，图文页数不能塞入 duration_sec。

优先已有同批证据 → 公开分享页结构化信息/DOM/播放器 → 对应原视频页或作者公开主页 → 下载真实媒体并 ffprobe/抽帧/转写。失败后换可行渠道；同一方法失败两次先查证，禁止无限重试。登录、验证码交给用户，禁止绕过；付费工具须明确批准。渠道不可用时记具体原因，不能假装已尝试。

图文保存可获取的全部原图及顺序；视频尽量下载原媒体，抽取开场、核心信息、转折、结尾的不同关键帧，精选案例通常至少 4 张有效画面。短视频可少于 4 张，但须说明并确保覆盖内容。仅封面不算完整视频证据；视频下载失败可保留封面并记录缺口，不能据此分析整段镜头与脚本。去掉黑帧、重复帧、加载页，核对画面与视频身份。

图文全文来自完整发布文案或逐页 OCR 校对；混剪/口播有音频则尽量做全程转写，保留带时间戳的原始 ASR 与校对稿。人工核对精选案例时逐句核对音频和关键字幕；尚未核对的完整自动转写可按系统v3通路显示“自动转写，待核对”，保留来源及未核对说明。转写无法取得时换同类型可核对案例；无替代时标为缺少该类深度拆解，不编写“原文”。

交付提供 capture-ledger.json（逐视频逐字段）及 coverage.json（各字段 applicable/ok/partial/missing、覆盖率、未完成视频、原因、下一步）。覆盖率=ok/applicable；partial 单列不冒充完整。100%尝试并记录是必需，100%成功不作虚假承诺。样本库可以如实保留受限条目；精选案例缺画面或缺完整来源全文不得验收通过；自动转写待核对须满足v3明确状态与可见提示要求，不冒充已核对。

### v3 系统模式补充

系统任务的完整口径以 system-mode.md 为准。本地 index.html 只用于预览和浏览器验收；回传页必须是静态导出。

- 时间：observed_at、attempts[].at 写 `Z` 或 `+08:00`（冒号不可省，`+0800` 拒收），如 `2026-09-29T04:00:35+08:00`。published_at 为 `YYYY-MM-DD` 或同样格式的 ISO 时间。Python 用 `datetime.now().astimezone().isoformat(timespec="seconds")`，不要用 `strftime("%z")`。
- 画面时点：混剪/口播抽帧时记录 timestamp_sec（≥0 且不超过 duration_sec），须能按该时点重新抽帧得到同一图片字节，否则该帧不计入 ok；图文用 page_index（从 1 起）。
- 自动转写：音轨时长与视频时长相差不超过 max(2 秒, 5%) 且有有效中文口播，transcript 记 ok，并写 transcriptReviewStatus=pending 与 verificationEvidence（来源、记录文件及散列、音轨时长、段数、未核对原因），报告显示「自动转写，待核对」；不得记 partial。未覆盖整轨才是 partial；无有效口播为 missing。人工逐句核对后才可 verified。
- 图文 image_text 必须是图片中的文字（逐页 OCR 并校对）；页面只有发布文案时记 missing 并写原因，不得把 caption 复制为 image_text。
- content_type 按该条证据判断：静态图文=image，单人对镜讲解=talking_head，剪辑拼接/字幕配乐等=montage。不得一律写 montage；无法判断记 missing 并写原因，不猜。
- A1–A21 的 evidence 写本次实际检查结果（计数、文件、节点 ID、命令输出摘要），不能用套话或统一写 passed；未通过写 failed。
