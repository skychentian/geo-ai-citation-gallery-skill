# 提取 / 拉取文案执行手册

需要跑 `extract_top_videos.py` / `fetch_video_scripts.py` 时再读。抓画面另见 [`capture-pipeline.md`](capture-pipeline.md)。参数以各脚本 `--help` 为准。

## 环境

| 用途 | 解释器/能力 |
|---|---|
| 提取 / 收尾 | 任一带 `openpyxl` 的 python3 |
| 抖音文案快速路径 | `web.fetch`（拿视频页文本），失败回退飞书妙记 `--run-lark` |
| 快手/B 站文案 | `doubao-video-extract` 对应平台 downloader + 妙记转写 |

视频文案拉取统一走 `doubao-video-extract` 的通道约定；改策略改工具库，别抄回 skill。

## 步骤 1 —— 提取

```bash
# 在 skill 根目录（含本 SKILL.md 的目录）
python scripts/extract_top_videos.py \
  --xlsx <数据包>/diagnosis-answers.xlsx \
  --brand "天猫养车,天猫养车连锁" \
  --top 10 \
  --scope-platform douyin \
  --stages 探索 \
  --package-date 20260830 \
  --out <包路径>/
```

- `--scope-platform douyin`（默认，仅抖音）/ `all`（抖音+快手+B 站等全部视频信源）
- 自定义题：`--questions-file <一行一题.txt>`（可与 `--stages` 取交集）
- 交付：`视频索引.md`、`_机器可读/top.json`；过程进 `_过程/`
- 引用次数 = 覆盖问题数；总提取次数 = 含多平台重复
- 先剔品牌题再做非品牌 Top；`--brand` 带全称+简称

## 步骤 2 —— 拉取文案

```bash
python scripts/fetch_video_scripts.py --package <包路径> --init
# Agent 按清单用通道填入 文案/<rank>_*.md
python scripts/fetch_video_scripts.py --package <包路径> --verify
```

- 补拉失败：`--verify --retry-failed`（只处理未成功 / 缺文件的；每个序号必有 md）
- 试跑：`--limit 3`（若脚本支持）
- 文案 → `文案/`；状态回写 `top.json`（含 `fetch_status` / `fail_reason` / `analysis_eligible` / `account` / `publish_date` / `duration` / `play_count` / `word_count`）
- 失败也落盘：标题加 `【未拉取到】`，头字段写明原因；**不要空号**
- 文案头统一：`来源` / `平台` / `账号` / `发布时间` / `时长` / `播放量` / `总字数` / `拉取状态`
- 通道：
  - **抖音**：`web.fetch` 快速路径；失败再走 `doubao-video-extract` 的 `--run-lark`。不要用网页标题/描述/评论补写正文。
  - **快手 / B 站**：先平台 downloader，再转写。
  - 拉不到口播/字幕、纯 BGM 无有效文案 → `analysis_eligible=false`。

## 步骤收尾 —— finalize

```bash
python scripts/finalize_package.py --package <包路径>
```

缺画廊 `gallery/index.html`（或根 `index.html`）、`README.md`、`视频索引.md`、`文案/`、`top.json` 会失败。`偏好分析.md` 默认可选（内部归档）；加 `--require-preference` 才强制。成功则删除 `_过程/`。

包目录约定见 [`package-spec.md`](package-spec.md)。
