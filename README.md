# GEO AI 高引用视频画廊 Skill

一句话：装好后让 AI 从诊断包做出「晨光陶瓷」风格客户高引用证据页（抓画面、分析、出 HTML、发布）。

结构遵循 [Agent Skills / Cursor 官方实践](https://cursor.com/docs/skills) 的**渐进式加载**：

```text
skills/geo-ai-citation-gallery/
├── SKILL.md          # 主流程 + 硬规则（先读这个）
├── scripts/          # 可执行代码（需要时再跑）
├── references/       # 手册与 schema（需要时再读）
└── assets/           # 模板等静态资源
```

## 安装

```bash
npx skills add skychentian/geo-ai-citation-gallery-skill --skill geo-ai-citation-gallery
```

## 怎么跟 AI 说话

```text
按 @geo-ai-citation-gallery，用这份诊断包做客户高引用画廊，赛道是 XX。
```

AI 应先读 `SKILL.md`；抓画面时再打开 `references/capture-pipeline.md` 并跑 `scripts/`，**不要**把 references 整包塞进上下文。

## 硬规则摘要

- 指标展示用「引用次数 / 引用率」，不要写「应用次数 / 应用率」。
- 抖音话题标签每条最多 **5** 个（`scripts/normalize_hashtags.py`）。
