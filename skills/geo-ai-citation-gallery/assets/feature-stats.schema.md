# feature-stats / 画廊数据字段说明

模板内嵌两块数据（也可拆成 `data.json` 后注入）：

- `STATS`：汇总、分类、词频、图表序列
- `data`：详情卡逐条样本（数组）

以下为约定字段；缺省时 UI 应降级为「暂未抓取到」或隐藏对应图，禁止用 `—` 表示缺失。

## STATS.meta

| 字段 | 类型 | 说明 |
|------|------|------|
| sample_n | number | 样本条数 |
| cite_sum | number | 应用次数合计 |
| avg_cite / median_cite / max_cite | number | 条均 / 中位 / 最高应用次数 |
| max_app_rate | number | 最高应用率（与展示单位一致，通常为百分比数值） |
| unique_questions | number | 不重复问题数 |
| platform | string | 监测平台，如豆包手机版 |
| total_answers | number | 总回答数（应用率分母） |
| monitor_date | string | 监测日 |
| sector | string | 赛道 / 样本说明 |
| oral_n / tuwen_n | number | 口播 / 图文条数 |
| duration_sec_n / duration_sec_total | number | 口播有秒数覆盖 |
| image_count_n / image_count_total | number | 图文有页数覆盖 |
| duration_note | string | 时长/页数缺口说明（人话） |
| engagement_zero_policy / card_display_policy | string | 0 vs 暂未抓取到 的展示政策 |
| scatter_excluded_n / suspect_zero_ranks | number / number[] | 散点剔除说明 |
| spearman_cite_digg | number | 可选脚注，不作主结论 |

## STATS 内容块

- `features_summary[]`: `{label, text}` 高引用特征短句
- `categories[]`: `{name, count, cite_sum, avg_cite, example, why_typical, script_pattern, content_type_split}`
- `content_type_stats[]` / `content_type_by_category[]` / `content_type_conclusion` / `category_note`
- `script_patterns[]`: 拍摄/脚本规律（白话）
- `title_freq` / `htag_freq` / `topic_freq` / `title_len` / `title_examples` / `body_examples` / `tag_examples`
- `scatter[]` / `scatter_excluded[]` / `proof_points[]`
- `follower_vs_cite` / `digg_vs_cite` / `collect_vs_cite`：分桶条均引用
- `duration_points` / `duration_buckets`：口播秒
- `image_points` / `image_bucket_stats`（或 `frame_bucket_stats`）：图文页数

## data[] 详情卡

| 字段 | 说明 |
|------|------|
| rank | 排序（应用次数） |
| video_id | 弱化展示 |
| title / title_short | 大标题；≠ 文案 |
| cite_count / app_rate | 应用次数 / 应用率 |
| url | 原链 |
| original_desc | 文案（三行预览可展开） |
| hashtags / topics | 标签 |
| account_name / follower_count | 账号 / 粉丝 |
| digg_count / collect_count / share_count / comment_count | 赞藏转评；`null`→暂未抓取到；`0`→0 |
| digg_valid 等 | 清洗后用于作图的有效值 |
| content_type | `图文` \| `口播` |
| duration_sec | 口播秒；图文为 null |
| image_count / frame_count | 图文页/帧 |
| images[] | 相对 `images/` 的画面文件名 |
| main_category | 互斥主类 |
| title_has_tubao | 是否命中监测品牌旁注（历史字段名可保留，UI 文案用「监测品牌」） |
| sample_questions | 默认不渲染；仅分析用 |

## 数字与缺口

- 卡片与表格：`0` → `0`；`null`/缺失 → `暂未抓取到`
- 散点/分桶图：按 `engagement_zero_policy` 排除可疑缺失，并在文案标明剔除条数
