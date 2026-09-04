# GEO AI 高引用视频画廊 Skill

分析被 AI 搜索 / 大模型高频引用的短视频样本，生成 **GEO Lens「晨光陶瓷」** 风格客户证据画廊（指标说明、五 Tab、图表人话结论、详情卡、拍摄指引）。

通用规范见：[`skills/geo-ai-citation-gallery/SKILL.md`](skills/geo-ai-citation-gallery/SKILL.md)。

## 安装（Cursor / Grok Bot）

```bash
npx skills add skychentian/geo-ai-citation-gallery-skill --skill geo-ai-citation-gallery
```

已实测：`npx skills` 可用，按 frontmatter `name`（`geo-ai-citation-gallery`）匹配；安装后目录一般为 `.agents/skills/geo-ai-citation-gallery/`。展示标题见 SKILL 正文「GEO AI 高引用视频画廊」。

若 `npx skills` 不可用，可直接 clone 本仓库，把 `skills/geo-ai-citation-gallery/` 拷进项目的 skills 目录，或在对话里 `@` 引用 `SKILL.md`。

## 包内路径

| 路径 | 用途 |
|------|------|
| `skills/geo-ai-citation-gallery/SKILL.md` | 通用交付规范 |
| `skills/geo-ai-citation-gallery/assets/template.html` | 可套用的完整画廊模板 |
| `skills/geo-ai-citation-gallery/assets/feature-stats.schema.md` | STATS / data 字段说明 |

## 依赖

- 图表：Chart.js 4.x CDN（模板已引用）
- 样本数据：按 schema 准备 `STATS` + `data`（可内嵌或 `data.json`）
- 画面：相对路径 `images/`（可选）
- 发布：可选 [here.now](https://here.now)（保留 slug 更新）

## 线上版式示例

[https://still-mill-xbe8.here.now/](https://still-mill-xbe8.here.now/) — 仅作版式与交互参考，**不是**本 skill 的默认客户内容。

## 快速开始

1. 复制 `assets/template.html` → 交付目录 `index.html`
2. 替换 `{{SECTOR}}` / `{{MONITOR_DATE}}` / `{{PLATFORM}}` 与内嵌 `STATS` / `data`
3. 按 `SKILL.md` 校验清单过一遍（尤其：0 vs 暂未抓取到、表格字号、品牌仅旁注）
4. 本地打开或发布到 here.now

不要把 API key / credentials 写进页面或提交进仓库。
