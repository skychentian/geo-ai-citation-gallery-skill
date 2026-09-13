---
name: geo-ai-citation-gallery
description: >-
  用户要做「AI 高引用短视频客户画廊 / GEO 证据页 / 高引用视频分析 / 文案留档」时立刻使用：
  步骤0问清口径 → 提取 TopN → 拉取文案/逐字稿 → 抓画面与互动 → 子 Agent 写偏好洞察 →
  套晨光陶瓷五 Tab 出 HTML 并发布。触发词：高引用画廊、GEO 画廊、高引用视频分析、
  抓取偏好、豆包引用视频、客户证据页、文案留档、套 geo-ai-citation-gallery。
---

# GEO AI 高引用视频画廊（含分析 / 文案留档）

按需加载：本文件只给硬规则与主流程。细节进 `references/`，可执行进 `scripts/`，模板进 `assets/`。**不要把整份 references 一次性读进上下文。**

**客户主交付 = 晨光陶瓷画廊 HTML**（`assets/template.html` → `gallery/index.html` + `images/`）。可选 `偏好分析.md` 作内部归档。绿头 KPI 壳见 `assets/legacy/`，**禁止当对客主页**。

## 硬规则（全程）

1. 指标用词：**引用次数 / 引用率**（禁止「应用次数 / 应用率」）。
2. 抖音标签：**每条 ≤5**；超额截断后再展示/分析。细则 → `references/hashtags.md`。
3. 抓画面：浏览器只捞媒体 URL；本机脚本下载/抽帧；禁止整页截屏当成品；缺数据标「暂未抓取到」。
4. 文字三字段：短标题 ≠ 发布文案 ≠ 口播文案；禁止用发布文案冒充口播。
5. 禁止编造帧图/互动数/播放量；失败不要写成 `0`。
6. 交付前过 `references/qa-checklist.md`：**任一 P0 不通过 = 验收不通过**。
7. **步骤 0 未获选择题回复前，禁止提取 / 拉取 / 抓画面 / 写偏好**。
8. 偏好与画廊分析**只使用 `analysis_eligible=true`**（拉不到口播 / 纯 BGM / 过短排除）。
9. **写偏好必须拆子 Agent**（主会话禁止通读全量文案硬写）→ `references/analysis-phase.md`。
10. 视频与文章分开；本包只装视频。先剔品牌题再做非品牌 Top。

## 步骤 0 —— 选择题确认（硬停）

第一件用户可见动作：用**带说明的选项**问清四题，然后停止等待。禁止盲确认默认口径。

**① 数据包** A 本地最新（推荐，写明日期）/ B 系统更新需导出 / C 指定日期  
**② 平台范围**（必须解释）  
- A **仅抖音**（推荐）：AI 引用基本来自抖音，抓取通道最稳。  
- B **全部视频平台**：抖音+快手+B 站等合并取 Top。  
**③ Top N** 10（推荐）/ 20 / 5 / 其他  
**④ 范围** 探索+评估各一包（推荐）/ 只要探索 / 只要评估 / 全阶段一包 / 自定义题  

选完才进入总控。空范围（剔品牌后无视频）→ 跳过并说明，不造空包。

## 主流程（按序）

| 步 | 做什么 | 需要细节时再读 / 再跑 |
|----|--------|------------------------|
| 0 | 选择题硬停 | 上文 |
| 1 | 提取 TopN → `视频索引.md` + `top.json` | `references/extract-fetch-runbook.md`；`scripts/extract_top_videos.py` |
| 2 | 拉取文案/逐字稿 → `文案/`；回写 `analysis_eligible` | 同上；`scripts/fetch_video_scripts.py` |
| 3 | 抓画面 + 互动（赞/藏/转/粉/时长或页数） | **必读** `references/capture-pipeline.md`；`scripts/capture_server.py` + `page_hook.example.js` |
| 4 | 分析：派子 Agent 写偏好洞察 | **必读** `references/analysis-phase.md`；模板 `video-preference-template.md`；阶段 `stage-guidance.md` |
| 5 | 套 `assets/template.html` → `gallery/index.html` + `images/` | 字段：`feature-stats.schema.md`；标签只渲染 ≤5 |
| 6 | 可选落盘 `偏好分析.md`（归档） | 不要出绿头 KPI 主页 |
| 7 | **验收门禁**（P0 全过） | **必读** `references/qa-checklist.md` |
| 8 | 收尾 / 发布 | `scripts/finalize_package.py`；包规范 `package-spec.md` |

### 最短命令（详情在对应 references）

```bash
# 在 skill 根目录
python scripts/extract_top_videos.py --xlsx <包>/diagnosis-answers.xlsx --brand "…" --top 10 --scope-platform douyin --stages 探索 --out <交付包>/
python scripts/fetch_video_scripts.py --package <交付包> --init   # 再填文案后 --verify
CAPTURE_PROJECT=<PROJECT> python scripts/capture_server.py       # + page_hook
python scripts/normalize_hashtags.py meta.json
python scripts/finalize_package.py --package <交付包>
```


## 何时用 / 边界

- **用**：Top N 高引用视频 + 文案留档 + AI 抓取偏好洞察 + 晨光陶瓷证据画廊。
- **不用**：抓高引用文章、写 GEO 文章正文、审稿、视频分镜/提交、纯出测试题；那些另有技能。
- 不重算正式核心指标；播放/点赞以拉取到的页面元数据为准，拉不到就不写。
- 拉取若走付费通道（如飞书妙记）须先说明；交付物不出现哈希、UUID、机器路径。

## 交付物

- **对客主交付**：`gallery/index.html` + `images/`（晨光陶瓷五 Tab）
- **归档**：`文案/` · `_机器可读/top.json` · `视频索引.md` · 可选 `偏好分析.md` · README
- 可选线上 URL（here.now 等）；客户页用晨光陶瓷，勿套学习「纸感」或绿头 KPI 壳

版式参考（仅交互）：[still-mill-xbe8.here.now](https://still-mill-xbe8.here.now/) · [news.skygeoapp.com/tubao-top50/](https://news.skygeoapp.com/tubao-top50/)
