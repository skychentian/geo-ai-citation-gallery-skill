---
name: geo-ai-citation-gallery
description: >-
  用户要做「AI 高引用短视频客户画廊 / GEO 证据页」时立刻使用：
  从诊断包筛样本、核对引用与内容证据、抓画面与互动，交付本地 HTML。
  触发词：高引用视频分析、高引用画廊、GEO 画廊、豆包引用视频分析、客户证据页、套 geo-ai-citation-gallery。
---

# GEO AI 高引用视频画廊

按需加载：本文件只给主流程与硬规则。细节进 `references/`，可执行代码进 `scripts/`，模板进 `assets/`。**不要把整份 references 一次性读进上下文。**

## 硬规则（全程）

1. 指标用词：**引用次数 / 引用率**（禁止「应用次数 / 应用率」）。
2. 原始标签完整留存；规范化去重后用于分析，不能先截断或挑选再统计。展示摘要可折叠，不改变分析数据。细则见 `references/hashtags.md`。
3. 抓画面：默认用无头脚本 `scripts/douyin_fetch.py`；兜底时浏览器只捞媒体 URL，本机脚本下载/抽帧；禁止整页截屏当成品；缺数据标「暂未抓取到」。
4. 文字三字段：短标题 ≠ 发布文案 ≠ 口播文案；禁止用发布文案冒充口播。
5. 禁止编造帧图/互动数；失败用「暂未抓取到」，不要写成假 `0`。仅当来源明确返回数字 0 才写 `0`；只有图标、没有数字时仍记缺失。
6. 交付前过 `references/qa-checklist.md`：**任一 P0 不通过 = 验收不通过**。

## 统一入口与本轮范围

这是工作台高引用视频分析与证据画廊的唯一执行入口。`geo-high-citation-video-analysis` 和 `AI 高引用视频分析报告` 均转交本技能；绿色 KPI 模板只作历史参考。

HTML 以 2026-09-24 确认版为准，具体执行必读 `references/approved-report-contract.md`；`assets/preview.html` 用于查看示例。交付须连同 `assets/vendor/` 复制，不能仅复制 HTML。生成新报告仍须检查数据兼容与样本口径，不得把覆盖问题数塞进引用次数，也不得直接发布旧示例。

## 系统任务模式

收到 GEO 冻结 input.json 时先读 `references/system-mode.md`，使用指定 executionId/客户/范围；不再询问默认选择、不重新导出监测。不把本地示例当证据。系统回传使用仓库 scripts/bot 适配器和安全快照。系统 v2 直接使用 input.videoCandidates 的完整冻结集合，不能自行删样本或重新选 TopN；逐项提交 16 字段（含 image_text）、真实图片散列、全文与报告节点绑定。只用批准模板样式，不新增或改写 CSS。

## 启动句

> 按 @geo-ai-citation-gallery，用这份诊断包做客户高引用画廊，赛道是 XX。

附诊断包路径/zip。

## 主流程（按序；缺一步就标缺口）

| 步 | 做什么 | 需要细节时再读 / 再跑 |
|----|--------|------------------------|
| 1 | 确认范围 → 按视频身份归并 → 区分引用回答数与覆盖问题数 → TopN | 必读 `references/package-spec.md`、`references/extract-fetch-runbook.md`、`references/feature-stats.schema.md` |
| 2 | 补元数据（发布文案、口播、短标题、完整原始标签、账号等） | `references/hashtags.md` |
| 3 | 抓画面 + 互动 + 时长 + 口播：默认跑 `scripts/douyin_fetch.py`；失败条目兜底：启本机服务 + 浏览器捞 CDN URL。跑完用 `scripts/merge_fetch.py` 合并进 gallery/data.json（先 --dry-run）。发布文案和日期默认用抖音原文覆盖，其他只填空 | **必读** `references/capture-pipeline.md`（默认一节）；兜底跑 `scripts/capture_server.py` + `scripts/page_hook.example.js` |
| 4 | 抓互动（赞/藏/转/粉/时长）：默认已由第 3 步 douyin_fetch 产出 engagement.json；缺的条目兜底 | **必读** capture-pipeline §C；兜底跑 `scripts/fetch_engagement.py --package <包>`；空值「暂未抓取到」 |
| 5 | 按证据维度分析，主类按需求划分，每项发现关联样本和引用问题 | 必读 `references/analysis-phase.md`、`references/stage-guidance.md` |
| 6 | 按版式约定写 report.json，运行 `scripts/build_report.py --input <report.json> --out <新目录>` | 必读 `references/approved-report-contract.md`；模板禁止直接保留旧客户案例 |
| 7 | **验收门禁**（P0 全过才能交付） | **必读** `references/qa-checklist.md` |
| 8 | 本地交付与打包检查；不自动发布或清理 | `scripts/finalize_package.py` 仅确认文件打包，不代替数据、页面和人工验收 |

### 抓画面最短命令（详情在 capture-pipeline）

```bash
# 在 skill 根目录（含本 SKILL.md 的目录）
# 默认：画面、互动、时长、口播一次出
python3 scripts/douyin_fetch.py --package /path/to/<PROJECT> --out /path/to/<PROJECT>/work/douyin_fetch
# 合并进 gallery/data.json（先 --dry-run）
python3 scripts/merge_fetch.py --package /path/to/<PROJECT> --fetch /path/to/<PROJECT>/work/douyin_fetch --dry-run
python3 scripts/merge_fetch.py --package /path/to/<PROJECT> --fetch /path/to/<PROJECT>/work/douyin_fetch

# 兜底（失败条目）
pip install pillow   # 口播还要 PATH 里有 ffmpeg
CAPTURE_PROJECT=/path/to/<PROJECT> python scripts/capture_server.py
# 浏览器打开公开分享页后执行 scripts/page_hook.example.js（改 RANK/KIND）
# 排障：python scripts/download_one.py '<cdn-url>' --png /tmp/t.png
# 标签规范化：python scripts/normalize_hashtags.py meta.json
# 互动补全：python scripts/fetch_engagement.py --package /path/to/<PROJECT>
```

协议摘要：`/meta` → 多次 `/media` → `/finish`（仅 `127.0.0.1`，勿对公网暴露）。

## 权限与完成边界

- 默认只读已有数据包，不重跑已确认报告。提取使用新目录，原始材料不覆盖、不自动删除。
- 抓取失败保留证据和缺口；登录交给用户。计费采集必须按工作台要求取得负责人明确确认。
- 本工作台默认不对外发布。发布说明只是技术参考，不构成发布授权。
- 子 Agent 按样本体量和独立任务需要使用，不以固定样本数强制拆分。
- 结论分为观察事实、解释假设、制作建议；不把高引用样本共性写成算法因果。

## 交付物

清单 CSV/JSON · `shots/` · metadata/engagement · `index.html` · 可选线上 URL

版式参考（仅交互）：[still-mill-xbe8.here.now](https://still-mill-xbe8.here.now/) · [news.skygeoapp.com/tubao-top50/](https://news.skygeoapp.com/tubao-top50/)

## 阅读与画面展示约定

报告分析、统计图表及解读直接展示，不折叠。单条样本的发布文案和口播默认显示四行摘要，长文提供查看全文按钮。真实画面直接展示缩略图并可放大；交付必须带对应 images/，不能把缺图占位作为正常成品。模板示例图片须核对 video_id 后复用，不得跨样本借图。

## 确认版与采集验收（2026-09-24）

- 本次确认适用于官方通用模板，并非兔宝宝专属规则。客户名、行业与结论全部从本批证据填入。
- Grok 执行也须读版式约定、capture-pipeline §D 和 QA A17 至 A21；不依赖本会话记忆。
- 全样本逐字段尝试画面、全文、赞/藏/评/转/粉、时长或页数；交付 capture-ledger.json、coverage.json、qa-report.md；系统模式另按 v3 输出 video-qa.json。失败有来源与原因，不能仅写未获取便结束。
- 系统任务按 references/system-mode.md 的 v3 规则执行（时区 +08:00、画面时点、自动转写 ok+待核对、静态导出、image_text 不用发布文案、A1–A21 真实依据）；本目录另含经批准的本地增强（无 answer_id 时链接出现口径等），不改变系统验收要求。
- 精选案例完整原文直接显示，右侧短批注；样本库才允许长文摘要展开。完整自动转写未经人工核对可按系统v3待核对通路进入精选案例，必须在对应案例显示“自动转写，待核对”并保留来源及未核对说明；不得声明已核对或以此豁免缺原文、缺画面。
- 原 preview.html 是布局示例，其待校对转写和残缺图片不属于通过验收的客户证据；不得复制这些内容到新客户成品。
- 最终交付分开报告结构、数据、媒体、浏览器验证状态；生成脚本通过不等于验收通过。
