# GEO AI 高引用视频画廊 Skill（含分析 / 文案留档）

一句话：装好后让 AI 从诊断包做出「晨光陶瓷」风格客户高引用证据页——提取 TopN、拉取文案/逐字稿、抓画面、子 Agent 偏好洞察、出 HTML、发布。

结构遵循 [Agent Skills / Cursor 官方实践](https://cursor.com/docs/skills) 的**渐进式加载**：

```text
skills/geo-ai-citation-gallery/
├── SKILL.md          # 硬规则 + 步骤0 + 主流程（先读这个）
├── scripts/          # 提取 / 拉文案 / 抓画面 / 收尾（需要时再跑）
├── references/       # 手册与 schema（需要时再读）
└── assets/           # 晨光陶瓷模板；legacy/ 为废弃绿头 KPI 壳
```

## 安装

```bash
npx skills add skychentian/geo-ai-citation-gallery-skill --skill geo-ai-citation-gallery
```

技能文件夹名保持 `geo-ai-citation-gallery`（兼容旧安装）；能力已覆盖原「高引用视频分析」包。

## 怎么跟 AI 说话

```text
按 @geo-ai-citation-gallery，用这份诊断包做客户高引用画廊，赛道是 XX。
```

或：

```text
按 @geo-ai-citation-gallery，分析高引用视频并留档文案，再出晨光陶瓷证据页。
```

AI 应先读 `SKILL.md` 并完成**步骤 0 选择题**；提取/拉文案再打开 `references/extract-fetch-runbook.md`；抓画面再打开 `references/capture-pipeline.md`；写偏好再打开 `references/analysis-phase.md`。**不要**把 references 整包塞进上下文。

## 硬规则摘要

- 指标展示用「引用次数 / 引用率」，不要写「应用次数 / 应用率」。
- 抖音话题标签每条最多 **5** 个（`scripts/normalize_hashtags.py`）。
- 步骤 0 选完前禁止提取/拉取；偏好只分析 `analysis_eligible=true`；写偏好拆子 Agent。
- **客户主交付 = 晨光陶瓷五 Tab 画廊**；`偏好分析.md` 可选归档；不要用绿头 KPI HTML 当主页。
