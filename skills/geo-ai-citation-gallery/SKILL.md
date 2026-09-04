---
name: geo-ai-citation-gallery
description: >-
  用户要做「AI 高引用短视频客户画廊 / GEO 证据页」时立刻使用：
  从诊断包筛样本、抓画面与互动、套晨光陶瓷模板出 HTML 并发布。
  触发词：高引用画廊、GEO 画廊、豆包引用视频分析、客户证据页、套 geo-ai-citation-gallery。
---

# GEO AI 高引用视频画廊

### 0. 给执行 AI 的一句话

你装了本 skill 就按下面步骤做完整交付；缺数据就标「暂未抓取到」，禁止编造。

### 1. 用户怎么启动（写给队友看的）

装好后对 AI 说类似：

> 按 @geo-ai-citation-gallery，用这份诊断包做客户高引用画廊，赛道是 XX。

然后附上诊断包路径/zip。**队友不用读 capture 文档。**

### 2. 端到端步骤（合并抓取+出页）

按顺序做；缺一步就标缺口，不要跳过也不要假数据。

1. **读诊断包**  
   从 xlsx/csv 抽抖音信源 URL + 应用次数；按应用次数筛 TopN（默认 50，用户可改）。→ 清单 CSV/JSON。**不需要登录抖音。**

2. **补元数据**  
   账号、图文/口播、发布时间、标签，以及下面三类**不要混名**的文字字段（打开公开页或已有字段）：

   | 字段 | 含义 |
   |------|------|
   | **发布文案** / `caption`（或 `original_desc`） | 作者写在作品下的文字（图文/口播都有） |
   | **口播文案** / `transcript` | 口播视频里**说出来的话**（页面字幕/口播稿优先，否则 ASR）；与发布文案经常不同 |
   | **短标题** / `title` / `title_short` | 列表或卡片用的短标题，≠ 上面两者 |

   - **图文**：通常只要发布文案 + 标签；画面上的字若关键可另记，但别叫成「口播文案」。
   - **口播**：尽量单独提取口播文案；抓不到标「暂未抓取到」，**禁止用发布文案冒充口播文案**。
   - 长发布文案不要塞进标题字段。

3. **抓画面（脚本 + 浏览器，已验证）**  
   **成品图来自脚本 HTTP 下载，不是浏览器截屏文件。** 主路径：浏览器只负责**捞媒体 URL**，本机 `capture_server.py` 负责下载落盘 / ffmpeg 抽帧。

   | 角色 | 工具 | 做什么 |
   |------|------|--------|
   | **A 本机脚本** | `assets/scripts/capture_server.py` | 接收 URL，带 Referer+UA 下载落盘；图文存 PNG；口播 ffmpeg 抽帧；写 `shots/`、`work/capture_progress.txt`、`work/metadata.jsonl` |
   | **B 浏览器代理** | Chrome / Antigravity `/browser` / 无头均可 | 打开每条**公开分享页**，用 `page_hook.example.js` 或等价逻辑**捞媒体 URL**，再 `fetch` 本机 `127.0.0.1:8765`；**不是**靠整页截图当成品 |

   **逐步清单（执行 AI 照做）：**

   1. 依赖：`pip install pillow`（若需）；确认 `ffmpeg` 在 PATH（口播抽帧）。单 URL 可先：`python assets/scripts/download_one.py '<cdn-url>' --png /tmp/t.png`。
   2. 启动接收服务（绑 `127.0.0.1:8765`，勿对公网暴露）：
      ```bash
      CAPTURE_PROJECT=/path/to/<PROJECT> python assets/scripts/capture_server.py
      ```
      默认 `CAPTURE_PROJECT` = `./capture_out`。会建 `<PROJECT>/shots/` 与 `<PROJECT>/work/`。
   3. 对清单**每条**公开分享 URL：
      - B 打开页面（**无头优先**；遇登录墙/验证码 → 停该条，转有头或人工，禁止绕过、禁止假图）。
      - 运行 `assets/scripts/page_hook.example.js`（改 `RANK` / `KIND`）或等价逻辑：从 `<img>`、背景图、`video`/`source`、`performance.getEntries`、网络里常见 `douyincdn` / `*.byteicdn` 等收集 URL（通用提示，勿写死易失效私有 API）。
      - 图文：`kind=image`；口播：`kind=video` + 可选 `poster`。
      - 依次打本机：`/meta` → 多条 `/media` → `/finish`（协议见脚本头注释；与现网一致）。
   4. 检查 `<PROJECT>/shots/NN_*.png` 与 `work/capture_progress.txt`（成功/失败原因）。部分帧 / 仅封面也写 progress，已有帧照常展示。
   5. 拷到画廊：`shots/*.png` → `gallery/images/`（或模板约定路径）。

   **强调**：Antigravity 等有浏览器的 AI 按上表分工即可——浏览器捞 URL，脚本出 PNG。无浏览器/脚本时不要硬编截图，一律「暂未抓取到」。细节与失败表见 `assets/capture-pipeline.md`。

4. **抓互动**  
   尽量抓：粉丝、赞、藏、转、评、时长秒（口播）或图文页数。  
   - 页面明确为 0 → 显示 `0`  
   - 没抓到 → `null` /「暂未抓取到」  
   - **禁止**把失败写成 0；可疑全 0 可从散点图排除并脚注。

5. **分析**  
   - 互斥主类约 4 类（按赛道归纳，每条只进一类）  
   - 图文 vs 口播占比（总体 + 按类）  
   - 高引用特征（通稿可复用、目录/名单、场景题、对照表等）  
   - 「拍的时候怎么排」白话脚本规律；每类 1 个真实案例  
   - **「标题·正文·标签」**：正文规律要区分 **「发布文案规律」** vs **「口播说辞规律」**；口播样本缺 `transcript` 时注明缺口，勿把发布文案当口播说辞分析  
   - 图表：应用次数 vs 互动、粉丝/赞/藏分桶 vs 条均引用、时长/页数分布；每图一句人话 takeaway  
   - 指标用专业词（应用次数、应用率、条均引用、分桶…）；相关≠因果，Spearman 最多脚注

6. **出页**  
   复制 `assets/template.html` → 交付 `index.html`；灌入 `STATS` / `data` / `images/`（从 `shots/` 拷或链）。  
   - 占位：`{{SECTOR}}` / `{{MONITOR_DATE}}` / `{{PLATFORM}}`  
   - Hero 下可折叠「指标说明」  
   - 五 Tab **固定顺序**：①高引用特征总结 ②内容分类 ③标题·正文·标签 ④互动与时长特征 ⑤详情  
   - 详情卡：`original_desc`/`caption`→发布文案；口播有 `transcript` 则展示口播文案（模板已支持有值就显示）；图文可只显示发布文案  
   - Demo 数据换成当前赛道样本；勿绑定真实客户品牌叙事为默认文案

7. **校验清单**  
   - [ ] 五 Tab 齐全且顺序正确  
   - [ ] 指标说明可折叠；`0` /「暂未抓取到」未混用  
   - [ ] 分类互斥 ≈4 类；含图文 vs 口播；每类 1 案例 + 脚本规律  
   - [ ] 每图有一句人话结论；Spearman 非主结论  
   - [ ] 详情卡：短标题、发布文案可展开、口播条另有口播文案（有则显示；缺则「暂未抓取到」、禁止用发布文案冒充）、字段标明「发布文案/口播文案/标签」、粉丝+赞藏转、画面、原链；监测问题默认隐藏；video id 弱化  
   - [ ] 口播用秒 / 图文用页数；缺口已标注；口播缺 transcript 已注明  
   - [ ] 表格数字字号未被 `.card .num` 撑大（如 `.ctype-table td.num` 显式字号）  
   - [ ] 监测品牌仅旁注；全文非品牌导向  
   - [ ] 无 API key / credentials 进仓库或页面

8. **发布**  
   可发布到 here.now 等，**保留 slug** 便于更新。示例：`bash publish_here.sh ./gallery --slug <your-slug>`

### 3. 硬规矩（短列表）

- **目标**：指导内容生产；监测品牌只旁注，禁止全文品牌导向 / 种草汇报  
- **说人话**：禁 AI 腔；前短后详（Hero/结论短句，细节进折叠与详情）  
- **指标**：正文专业词 + Hero 下「指标说明」白话口径；拍摄指引仍白话  
- **数字**：`0` 显示 `0`；未抓到「暂未抓取到」；禁止用 `—`/`-` 混淆  
- **五 Tab**：顺序固定（见上）  
- **分类**：互斥 ≈4 类 + 图文/口播；每类案例 +「拍的时候怎么排」  
- **文字三字段**：短标题 ≠ 发布文案 ≠ 口播文案；口播禁止用发布文案冒充口播文案；抓不到标「暂未抓取到」  
- **图表**：每图一句 takeaway；相关统计非主结论  
- **详情卡**：短标题；发布文案三行可展开；口播另展示口播文案（有则显示）；粉丝+赞藏转；画面+原链；video id 弱化  
- **时长**：口播秒 / 图文页数；缺数据标缺口  
- **抓画面**：脚本下载成品（`assets/scripts/capture_server.py`）+ 浏览器只捞 URL；无头优先；不是整页截屏当成品  
- **UI**：晨光陶瓷 tokens；`.card .num` 只用于大数字卡，表格须单独控字号  
- **禁止**：编造帧图/互动数；把失败当 0；绕过登录墙；用发布文案冒充口播文案

### 4. 交付物

| 产物 | 说明 |
|------|------|
| 清单 CSV/JSON | TopN URL + 应用次数 |
| `shots/` | `NN_k.png` 画面帧 |
| metadata / engagement | 元数据 + 互动 JSON |
| `index.html` | 套模板后的客户画廊 |
| 线上 URL | 发布后的链接（可选） |

字段约定见 `assets/feature-stats.schema.md`（调试用）。

### 5. 附录（可选）

仅调试 / 深挖时打开，**正常按上面步骤即可，队友不用读**：

- `assets/capture-pipeline.md` — 抓画面执行手册（链到 `assets/scripts/`）
- `assets/scripts/capture_server.py` / `page_hook.example.js` — 可直接跑的接收服务与浏览器钩子示例  
- `assets/feature-stats.schema.md` — STATS / data 字段表  
- 版式示例：[still-mill-xbe8.here.now](https://still-mill-xbe8.here.now/) — 仅交互参考，非默认客户内容
