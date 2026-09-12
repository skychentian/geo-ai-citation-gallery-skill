---
name: geo-ai-citation-gallery
description: >-
  用户要做「AI 高引用短视频客户画廊 / GEO 证据页」时立刻使用：
  从诊断包筛样本、抓画面与互动、套晨光陶瓷模板出 HTML 并发布。
  触发词：高引用画廊、GEO 画廊、豆包引用视频分析、客户证据页、套 geo-ai-citation-gallery。
---

# GEO AI 高引用视频画廊

### 0. 给执行 AI（含 Activity / ChatGPT / Cursor）的一句话

按下面步骤做完整交付；缺数据标「暂未抓取到」，**禁止编造**。  
抓画面必须走「浏览器捞媒体 URL + 本机脚本下载」，**不要**把整页截屏当成品图。  
抖音**标签最多 5 个**；指标口语与页面文案一律用 **「引用次数 / 引用率」**，禁止写「应用次数 / 应用率」。

### 1. 用户怎么启动

装好后对 AI 说：

> 按 @geo-ai-citation-gallery，用这份诊断包做客户高引用画廊，赛道是 XX。

附诊断包路径/zip。正常不必另开 capture 文档；抓取细节已写在本文件第 2.3 步与 `assets/capture-pipeline.md`。

### 2. 端到端步骤

按顺序做；缺一步就标缺口，不要跳过也不要假数据。

#### 2.1 读诊断包 → 引用清单

1. 打开诊断包里的 `source_urls`（或等价表），筛抖音域名：`iesdouyin.com` / `douyin.com` / `v.douyin.com`。
2. 按 **视频 URL（或 video_id）聚合引用次数** = 该 URL 在回答信源中出现的次数。
3. 计算 **引用率** = 引用次数 ÷ 本批总回答数（用 `manifest` / `meta.total_answers`，勿自造分母）。
4. 按引用次数降序取 TopN（默认 50）。输出清单 CSV/JSON，至少含：`rank, video_id, url, cite_count, app_rate`  
   - 字段名可保留 `cite_count` / `app_rate`（兼容旧模板），但**展示文案必须写「引用次数 / 引用率」**。
5. **不需要登录抖音**。

#### 2.2 补元数据（含标签硬规则）

打开每条公开分享页（或已有抓取字段），补：

| 字段 | 含义 |
|------|------|
| **发布文案** / `caption`（或 `original_desc`） | 作者写在作品下的文字 |
| **口播文案** / `transcript` | 口播里说出来的话；≠ 发布文案 |
| **短标题** / `title` / `title_short` | 卡片短标题；≠ 上面两者 |
| **标签** / `hashtags` | 见下方硬规则 |
| 账号、图文/口播、发布时间 | 能抓则抓 |

**抖音标签硬规则（必须遵守）：**

1. 抖音单条作品**最多 5 个话题标签**。入库 / 展示 / 分析用的 `hashtags` **长度 ≤ 5**。
2. 页面上若扫到 >5 个：按下方优先级**截断到 5**，并在 metadata 记 `hashtags_truncated: true` 与原始列表（可选 `hashtags_raw`）。
3. 优先级（从高到低）：赛道/品类词 → 场景词 → 方法/避坑词 → 地域词 → 品牌/账号营销词。  
   客户画廊里监测品牌标签可保留，但**不要为了品牌把标签撑破 5 个**。
4. 规范化：统一带 `#` 前缀；去重（大小写/全半角视为同一）；去掉空标签；不要把整句发布文案拆成伪标签。
5. 详情卡、词频图、案例引用都只用截断后的 ≤5 个标签；分析里不要声称「本条打了 12 个标签」除非注明「原始页超额，已截断」。

文字字段纪律：

- 图文：通常只要发布文案 + 标签；画面字别叫「口播文案」。
- 口播：尽量单独抽 transcript；抓不到标「暂未抓取到」，**禁止用发布文案冒充口播**。
- 长发布文案不要塞进标题字段。

#### 2.3 抓画面（脚本 + 浏览器）— Activity / ChatGPT 照抄

**成品图 = 本机 HTTP 下载（口播再 ffmpeg 抽帧），不是浏览器截屏文件。**

| 角色 | 工具 | 做什么 |
|------|------|--------|
| A 本机脚本 | `assets/scripts/capture_server.py` | `127.0.0.1:8765` 收 URL，带 Referer+UA 下载；图文→PNG；口播→ffmpeg 抽帧；写 `shots/`、`work/capture_progress.txt`、`work/metadata.jsonl` |
| B 浏览器 | Chrome / Antigravity `/browser` / Playwright 等 | 打开公开分享页，运行 `assets/scripts/page_hook.example.js`（或等价）捞 CDN/video URL，再 `fetch` 本机服务 |

**依赖**

```bash
pip install pillow
# 口播抽帧需要 ffmpeg 在 PATH
which ffmpeg
```

**A. 启动接收服务（仅回环，勿对公网暴露）**

```bash
cd <skill-root>/skills/geo-ai-citation-gallery
CAPTURE_PROJECT=/path/to/<PROJECT> python assets/scripts/capture_server.py
```

默认 `CAPTURE_PROJECT=./capture_out`。会创建：

```text
<PROJECT>/
  shots/                 # NN_k.png
  work/
    capture_progress.txt
    metadata.jsonl
```

**协议（GET + query，与脚本一致）**

1. `/meta?rank=N&d=<urlsafe-base64-json>`  
   meta JSON 至少：`{"kind":"image"|"video"}`；口播可加 `"poster":"<封面URL>"`；其它字段原样进 jsonl。会清空该 rank 已登记的 media 列表。
2. `/media?rank=N&u=<media_url>` — 可多次，追加 CDN URL。
3. `/finish?rank=N` — 开始下载/抽帧并写 progress。

下载头必须带：常见浏览器 `User-Agent` + `Referer: https://www.douyin.com/`（缺 Referer 易 403）。

**B. 每条公开页（循环 TopN）**

1. 无头优先打开分享 URL；遇登录墙/验证码 → **停该条**，标缺口或转有头/人工；禁止绕过、禁止假图。
2. 改 `page_hook.example.js` 的 `RANK` / `KIND`（图文=`image`，口播=`video`）后整段执行；或用自动化注入等价逻辑。
3. 钩子从 `<img>` / 背景图 / `<video>` / `performance.getEntries` / 常见 `douyincdn|byteicdn|...` 提示收集 URL（通用提示，勿写死易失效私有 API）。
4. 依次：`/meta` → 多条 `/media` → `/finish`。
5. 看 `shots/NN_*.png` 与 `capture_progress.txt`。部分帧/仅封面也写 progress；已有帧照常展示。
6. 拷贝：`shots/*.png` → `gallery/images/`。

**单条试下载（可选排障）**

```bash
python assets/scripts/download_one.py '<cdn-url>' --png /tmp/t.png
```

**失败怎么写 progress（示例）**

```text
1 ok image files=8
7 ok image files=4 (partial; remaining URLs 403)
8 fail video source unavailable; page JS exposes no downloadable media URL
37 ok video poster plus 2 frames
```

无浏览器/脚本能力时：不要硬编截图，画面一律「暂未抓取到」。更多失败表见 `assets/capture-pipeline.md`。

#### 2.4 抓互动

尽量抓：粉丝、赞、藏、转、评、时长秒（口播）或图文页数。

- 页面明确为 0 → 显示 `0`
- 没抓到 → `null` /「暂未抓取到」
- **禁止**把失败写成 0；可疑全 0 可从散点图排除并脚注

#### 2.5 分析

- 互斥主类约 4 类（每条只进一类）
- 图文 vs 口播占比（总体 + 按类）
- 高引用特征（通稿可复用、目录/名单、场景题、对照表等）
- 「拍的时候怎么排」白话脚本规律；每类 1 个真实案例
- 「标题·正文·标签」：区分发布文案规律 vs 口播说辞；标签分析基于 **≤5 截断后** 的列表
- 图表：引用次数 vs 互动、粉丝/赞/藏分桶 vs 条均引用、时长/页数；每图一句人话 takeaway
- 指标用词：引用次数、引用率、条均引用、分桶…；相关≠因果

#### 2.6 出页

复制 `assets/template.html` → `index.html`；灌入 `STATS` / `data` / `images/`。

- 占位：`{{SECTOR}}` / `{{MONITOR_DATE}}` / `{{PLATFORM}}`
- Hero 与指标说明里展示「引用次数 / 引用率」（不要出现「应用」）
- 五 Tab 固定顺序：①高引用特征总结 ②内容分类 ③标题·正文·标签 ④互动与时长特征 ⑤详情
- 详情卡标签只渲染 ≤5 个；口播有 `transcript` 才显示口播文案

#### 2.7 校验清单

- [ ] 五 Tab 齐全且顺序正确
- [ ] 全文无「应用次数/应用率/次应用」等错用词；统一「引用*」
- [ ] 每条 `hashtags.length ≤ 5`；超额已截断并（如有）保留 raw
- [ ] 指标说明可折叠；`0` /「暂未抓取到」未混用
- [ ] 分类互斥 ≈4 类；含图文 vs 口播；每类 1 案例 + 脚本规律
- [ ] 详情卡：短标题、发布文案可展开、口播文案未用发布文案冒充、字段名正确、粉丝+赞藏转、画面、原链
- [ ] 口播用秒 / 图文用页数；缺口已标注
- [ ] 表格数字字号未被 `.card .num` 撑大
- [ ] 监测品牌仅旁注；非品牌导向
- [ ] 无 API key / credentials 进仓库或页面

#### 2.8 发布

可发布到 here.now 等，**保留 slug**。示例：`bash publish_here.sh ./gallery --slug <your-slug>`  
客户交付（B 类）跟晨光陶瓷视觉，不要套学习页「纸感」皮。

### 3. 硬规矩（短列表）

- **用词**：引用次数 / 引用率 / 条均引用；禁止「应用次数/应用率」
- **标签**：抖音最多 5 个；超额截断；展示与分析都用截断后列表
- **目标**：指导内容生产；监测品牌只旁注
- **说人话**：禁 AI 腔；前短后详
- **数字**：`0` 显示 `0`；未抓到「暂未抓取到」
- **五 Tab**：顺序固定
- **文字三字段**：短标题 ≠ 发布文案 ≠ 口播文案
- **抓画面**：脚本下载 + 浏览器捞 URL；无头优先；不是整页截屏当成品
- **UI**：晨光陶瓷 tokens
- **禁止**：编造帧图/互动数；失败当 0；绕过登录墙；发布文案冒充口播

### 4. 交付物

| 产物 | 说明 |
|------|------|
| 清单 CSV/JSON | TopN URL + 引用次数 / 引用率 |
| `shots/` | `NN_k.png` |
| metadata / engagement | 含截断后 hashtags |
| `index.html` | 套模板后的客户画廊 |
| 线上 URL | 可选 |

字段约定见 `assets/feature-stats.schema.md`。

### 5. 附录

- `assets/capture-pipeline.md` — 抓画面手册（失败表、目录约定）
- `assets/scripts/capture_server.py` / `page_hook.example.js` / `download_one.py`
- `assets/feature-stats.schema.md`
- 版式示例：[still-mill-xbe8.here.now](https://still-mill-xbe8.here.now/) / [news.skygeoapp.com/tubao-top50/](https://news.skygeoapp.com/tubao-top50/) — 仅交互参考
