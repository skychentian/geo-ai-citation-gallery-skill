---
name: geo-ai-citation-gallery
description: >-
  用户要做「AI 高引用短视频客户画廊 / GEO 证据页」时立刻使用：
  从诊断包筛样本、抓画面与互动、套晨光陶瓷模板出 HTML 并发布。
  触发词：高引用画廊、GEO 画廊、豆包引用视频分析、客户证据页、套 geo-ai-citation-gallery。
---

# GEO AI 高引用视频画廊

按需加载：本文件只给主流程与硬规则。细节进 `references/`，可执行代码进 `scripts/`，模板进 `assets/`。**不要把整份 references 一次性读进上下文。**

## 硬规则（全程）

1. 指标用词：**引用次数 / 引用率**（禁止「应用次数 / 应用率」）。
2. 抖音标签：**每条 ≤5**；超额截断后再展示/分析。细则 → 做标签时再读 `references/hashtags.md`。
3. 抓画面：浏览器只捞媒体 URL；本机脚本下载/抽帧；禁止整页截屏当成品；缺数据标「暂未抓取到」。
4. 文字三字段：短标题 ≠ 发布文案 ≠ 口播文案；禁止用发布文案冒充口播。
5. 禁止编造帧图/互动数；失败不要写成 `0`。

## 启动句

> 按 @geo-ai-citation-gallery，用这份诊断包做客户高引用画廊，赛道是 XX。

附诊断包路径/zip。

## 主流程（按序；缺一步就标缺口）

| 步 | 做什么 | 需要细节时再读 / 再跑 |
|----|--------|------------------------|
| 1 | 诊断包筛抖音 URL → 聚合引用次数 / 引用率 → TopN 清单 | 字段约定：`references/feature-stats.schema.md` |
| 2 | 补元数据（发布文案、口播、短标题、标签≤5、账号等） | `references/hashtags.md` |
| 3 | 抓画面：启本机服务 + 浏览器捞 CDN URL | **必读** `references/capture-pipeline.md`；跑 `scripts/capture_server.py` + `scripts/page_hook.example.js` |
| 4 | 抓互动（赞/藏/转/粉/时长或页数） | 同上；空值用「暂未抓取到」 |
| 5 | 分析（约 4 类互斥、图文vs口播、特征与脚本规律） | 出页前扫 `references/qa-checklist.md` |
| 6 | 套 `assets/template.html` → `index.html` + `images/` | Hero/指标文案用「引用*」；标签只渲染 ≤5 |
| 7 | 按 QA 清单自检 | `references/qa-checklist.md` |
| 8 | 发布（可选，保留 slug）；客户页用晨光陶瓷，勿套学习「纸感」 | here.now 等 |

### 抓画面最短命令（详情在 capture-pipeline）

```bash
# 在 skill 根目录（含本 SKILL.md 的目录）
pip install pillow   # 口播还要 PATH 里有 ffmpeg
CAPTURE_PROJECT=/path/to/<PROJECT> python scripts/capture_server.py
# 浏览器打开公开分享页后执行 scripts/page_hook.example.js（改 RANK/KIND）
# 排障：python scripts/download_one.py '<cdn-url>' --png /tmp/t.png
# 标签截断：python scripts/normalize_hashtags.py meta.json
```

协议摘要：`/meta` → 多次 `/media` → `/finish`（仅 `127.0.0.1`，勿对公网暴露）。

## 交付物

清单 CSV/JSON · `shots/` · metadata/engagement · `index.html` · 可选线上 URL

版式参考（仅交互）：[still-mill-xbe8.here.now](https://still-mill-xbe8.here.now/) · [news.skygeoapp.com/tubao-top50/](https://news.skygeoapp.com/tubao-top50/)
