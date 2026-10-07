# feature-stats / 画廊数据字段说明

模板内嵌两块数据（也可拆成 `data.json` 后注入）：

- `STATS`：汇总、分类、词频、图表序列
- 数据版本 2：`citation_count`/页面 `cite_count`：有 answer_id 时按平台＋answer_id 去重（status=verified）；缺 answer_id 时按同一视频（规范化视频身份）在数据包中的链接出现次数计，按（平台、问题、回答行 round/response_index）去重（status=link_occurrence，非 verified）。`question_count`/页面 `q_count` 为不同题干数；`total_pickups` 为原始信源行数。排序按 citation_count，并列按 question_count；报告须用一句话写明口径。不得将问题数或信源行数映射成引用次数。
- `total_answers` 须来自同周期、AI 平台、问题范围的全部回答（包括无信源回答），保留 denominator_source、scope、去重规则；无法核验时 app_rate=null，不能自行选分母。提取脚本只在数据包含 answers 表时、按与信源行相同的筛选计算 `total_answers`，否则为 null；不从信源表推算分母。
- 本轮 HTML 未改版：旧渲染对 null 引用率、原始标签与归纳主题分离尚不兼容；使用前必须按 QA 检查，不得为了套模板伪填值。
- `data`：详情卡逐条样本（数组）

以下为约定字段；缺省时 UI 应降级为「暂未抓取到」或隐藏对应图，禁止用 `—` 表示缺失。

## STATS.meta

| 字段 | 类型 | 说明 |
|------|------|------|
| sample_n | number | 样本条数 |
| cite_sum | number | 引用次数合计 |
| avg_cite / median_cite / max_cite | number | 条均 / 中位 / 最高引用次数 |
| max_app_rate | number | 最高引用率（与展示单位一致，固定为百分比数值；不可核验时 null） |
| unique_questions | number | 不重复问题数 |
| platform | string | 监测平台，如豆包手机版 |
| total_answers | number | 总回答数（引用率分母） |
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

- `features_summary[]`: `{label, text}` 高引用特征短句；附 kind、sample_ranks、evidence_refs、related_questions、eligible_n、limitations
- `categories[]`: `{name, count, cite_sum, avg_cite, example, why_typical, script_pattern, content_type_split}`
- `content_type_stats[]` / `content_type_by_category[]` / `content_type_conclusion` / `category_note`
- `script_patterns[]`: 拍摄/脚本规律（白话）
- `title_freq` / `htag_freq` / `topic_freq` / `title_len` / `title_examples` / `body_examples` / `tag_examples`（分析「标题·正文·标签」时：`body_examples` 应区分发布文案规律 vs 口播说辞；口播缺 transcript 注明缺口）
- `scatter[]` / `scatter_excluded[]` / `proof_points[]`
- `follower_vs_cite` / `digg_vs_cite` / `collect_vs_cite`：分桶条均引用
- `duration_points` / `duration_buckets`：口播秒
- `image_points` / `image_bucket_stats`（或 `frame_bucket_stats`）：图文页数

## data[] 详情卡

| 字段 | 说明 |
|------|------|
| rank | 排序（引用次数） |
| video_id | 弱化展示 |
| title / title_short | **短标题**（列表/卡片）；≠ 发布文案、≠ 口播文案 |
| cite_count / app_rate | 引用次数 / 引用率 |
| url | 原链 |
| original_desc / caption | **发布文案**：作者写在作品下的文字（三行预览可展开） |
| transcript | **口播文案**：口播里说出来的话（字幕/口播稿/ASR）；与发布文案常不同；图文通常不填；缺则 null/「暂未抓取到」，禁止用发布文案冒充 |
| hashtags / topics | 标签；hashtags_raw 完整留存；hashtags 为完整规范化真实标签；topics 是人工归纳主题，不混作作者标签 |
| account_name / follower_count | 账号 / 粉丝 |
| digg_count / collect_count / share_count / comment_count | 赞藏转评；`null`→暂未抓取到；`0`→0 |
| digg_valid 等 | 清洗后用于作图的有效值 |
| content_type | `图文` \| `口播` |
| duration_sec | 口播秒；图文为 null |
| image_count / frame_count | 图文页/帧 |
| images[] | 相对 `images/` 的画面文件名 |
| main_category | 以主要用户需求归类；分类数量按样本确定，形式与证明方式另列 |
| eligibility | title/caption/transcript/visual/engagement 各证据维度是否可用；每项有来源才置 true |
| analysis_eligible | 旧版兼容汇总，不作为所有维度统一筛选条件 |
| title_has_tubao | 是否命中监测品牌旁注（历史字段名可保留，UI 文案用「监测品牌」） |
| sample_questions | 结论证据映射必须保留；页面升级前至少在证据 Markdown 中可查 |

## 数字与缺口

- 卡片与表格：`0` → `0`；`null`/缺失 → `暂未抓取到`
- 散点/分桶图：按 `engagement_zero_policy` 排除可疑缺失，并在文案标明剔除条数
- 互动图在有互动数据时必须出图；cite_count 为空时 build_report 以 q_count（覆盖问题数）作纵轴并在轴标题/图注写「覆盖问题数」。

### 文案校验的证据字段

文案头 `文案类型` 支持发布文案/视频描述/caption、口播文案/口播逐字稿/字幕转写/transcript。未知类型正文保留，但不作为口播。画面需 visual_evidence_source 与 visual_verified=true；互动需 engagement_source 与 engagement_verified=true。标题须能追溯 URL；正文须有来源和已拉取状态。完整画面文字另存证据，不能当口播。
