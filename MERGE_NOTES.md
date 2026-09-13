# MERGE_NOTES — 统一 geo-ai-citation-gallery + geo-high-citation-video-analysis

日期：2026-09-13（Asia/Shanghai）

## 决策

- **源真**：GitHub `skychentian/geo-ai-citation-gallery-skill` → `skills/geo-ai-citation-gallery/`
- **文件夹名不变**：`geo-ai-citation-gallery`（减少安装/指针断裂）
- **客户主交付**：晨光陶瓷五 Tab `assets/template.html` → `gallery/index.html` + `images/`
- **官方绿头 KPI HTML**：迁入 `assets/legacy/preference-kpi-template.html`，标注 deprecated for customer
- **偏好分析.md**：保留为可选内部/归档；洞察写入画廊 Tab

## 从官方技能并入

| 来源 | 落点 | 备注 |
|------|------|------|
| scripts/extract_top_videos.py | scripts/ | 原样 |
| scripts/fetch_video_scripts.py | scripts/ | 原样 |
| scripts/finalize_package.py | scripts/ | **已适配**：要求画廊主交付；偏好 md 默认可选 |
| references/runbook.md | references/extract-fetch-runbook.md | 路径统一为 scripts/ |
| references/package-spec.md | references/package-spec.md | 主交付改为 gallery |
| references/analysis-phase.md | references/analysis-phase.md | 写进画廊 Tab，禁绿头主页 |
| references/video-preference-template.md | 同名 | 增加与五 Tab 映射 |
| references/stage-guidance.md | 同名 | 原样 |
| assets/template.html（绿 KPI） | assets/legacy/… | 非对客主模板 |

## 画廊侧保留

- scripts：capture_server.py、page_hook.example.js、download_one.py、normalize_hashtags.py
- references：capture-pipeline.md、hashtags.md、feature-stats.schema.md、qa-checklist.md（已加 B8–B11 文案留档 P1）
- assets/template.html（晨光陶瓷）

## Nutstore

本合并**未删除** Nutstore `01-官方技能/geo-high-citation-video-analysis/`；由父代理改为指向本 GitHub 包的薄指针。

## 建议 Nutstore 薄指针文案

见本仓库报告 / 父代理交付说明（指向 `skills/geo-ai-citation-gallery/`）。
