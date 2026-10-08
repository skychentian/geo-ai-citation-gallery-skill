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
- `citation_count`：有 answer_id 时按平台＋answer_id 去重（status=verified）；缺 answer_id 时按同一视频（规范化视频身份）在数据包中的链接出现次数计，按（平台、问题、回答行 round/response_index）去重（status=link_occurrence，非 verified）。排序按 citation_count，并列按 question_count；报告须用一句话写明口径。`question_count` = 按题干去重的覆盖问题数；`total_pickups` 仅为原始信源行数。
- 不得把原始信源行数 `total_pickups` 当作引用次数。Top JSON 的 ranking_metric 必须随报告说明。
- 引用率只在同周期、同 AI 平台、同问题范围（含品牌题剔除规则）的全部回答分母可核实时计算；只含信源的表无法给出无引用回答。xlsx 含 answers 表时，提取脚本按与信源行相同的筛选计算同范围分母 `total_answers`，并同样计算 `app_rate`；否则不计算引用率。上游字段若不是 answer_id，先经字段映射并记录来源。
- 同一视频按平台＋视频 ID 归并；未知链接保留关键参数。已有包不能原地重新提取。
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
- 首次初始化为每个序号创建记录，抓取失败在状态中注明原因；已存在正文不覆盖。verify 不创建或改写正文；缺文件在状态中记录并由执行者补齐记录
- 文案头增加 `文案类型`（发布文案/口播文案/画面文字，未知则留空）；不能仅凭字数判断证据可用。其他头字段：`来源` / `平台` / `账号` / `发布时间` / `时长` / `播放量` / `总字数` / `拉取状态`
- 通道：
  - **抖音**：`web.fetch` 快速路径；失败再走 `doubao-video-extract` 的 `--run-lark`。不要用网页标题/描述/评论补写正文。
  - **快手 / B 站**：先平台 downloader，再转写。
  - 按 title/caption/transcript/visual/engagement 分别记录证据可用性。无口播、BGM 或短文案不自动排除标题、发布文案、画面等其他证据。未知文案类型不能当口播分析。

## 步骤收尾 —— finalize

```bash
python scripts/finalize_package.py --package <包路径>
```

缺画廊 `gallery/index.html`（或根 `index.html`）、`README.md`、`视频索引.md`、`文案/`、`top.json` 会失败。`偏好分析.md` 默认可选（内部归档）；加 `--require-preference` 才强制。默认保留 `_过程/` 和原始材料；不会删除文件。通过只表示打包检查通过，数据和页面仍按验收清单核对。

包目录约定见 [`package-spec.md`](package-spec.md)。
