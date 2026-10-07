# 官方报告版式与执行约定（2026-09-24）

本约定固化已确认的 `assets/preview.html` 设计；`assets/template.html` 是去除固定客户数据后的生成模板。旧绿色模板不再使用。Grok 与其他执行模型采用同一要求，不依赖前次聊天或特定模型工具。

## 固定结构

1. 标题：客户名 · 高引用视频分析。下设行业、监测日期与平台；核心指标仅样本数、总引用、覆盖问题数。详细口径放“数据说明”浮层。
2. 五个导航依次为：「视频类别」「内容拆解」「标题、文案与标签」「时长与互动」「全部样本」；DOM ID 依次 types/content/copy/features/samples。
3. 类别用单一占比图；悬停或点击显示条数、引用合计与平均引用。不在图下重复同一份表。主题与呈现形式分开分类。图文、混剪、口播按实物核对，旧数据未区分时说明，不凭名字强行重分类。
4. 拆解从本批选图文、混剪、口播各一个证据充分的案例。某类确实不存在可以不选，但须有全量类型核对记录，不能虚构补齐。真实截图紧凑横排、点击放大；完整原文保持顺序，右侧逐段短批注；禁止仅标题链接、零碎字幕代替全文，也不以笼统总结代替逐段分析。
5. 批注直接引用具体措辞或数字，解释“这句如何引出问题、给出信息、支持判断或指导行动”，通常一至两句。原文不润色；转写应明确区分已人工核对与完整自动转写待核对；后者按v3显示提示并保留真实来源。ASR 草稿不等于已核对原文，不得把 demo 中待校对的文字复制到成品。
6. 标题用紧凑对照行；发布文案使用全文加旁注；作者标签与分析主题分开。样本库内长篇原文可四行摘要＋展开，分析案例里的原文默认完整显示。自动转写的待核对提示必须在样本卡及展开全文中持续可见。
7. 时长和图文页数主图为数量（条）与占比，平均每条被引用次数仅作悬浮补充。注明占比的有效样本分母。粉丝、点赞、收藏的引用表现图须明确纵轴为平均引用次数或单视频引用次数，不能混用。缺失与零分开。
8. 结论在图前，图表宽屏两列、窄屏单列，图高约 205 至 210px；不重复堆叠口径框。缺少数据时说明不能分析，不能生成空图并写肯定结论。
9. 现有 demo 的 50 条样本、日期、板材分类、品牌、截图和结论全部是示例，不是其他客户的默认数据。

## Grok 执行顺序

先读 SKILL.md，再读本文件、采集手册、数据口径与验收清单。检查自己可用的浏览器、文件、Python、ffmpeg、转写能力；工具名可以不同，证据标准不能降低。没有访问能力时明确字段缺口，不用搜索摘要或模型记忆冒充视频原文。复用已授权数据，不触发付费采集测试。

建立逐视频采集台账 → 免费公开渠道补全 → 核对精选案例原视频/音频或明确保留完整自动转写待核对状态 → 形成分析及统计 → 写 report.json → 生成新目录 → 数据验收 → 浏览器验收 → 交付。不要只复制 demo 改标题。

## 可运行生成器

`python scripts/build_report.py --input /path/report.json --out /path/new-gallery`

输出 index.html、images/、vendor/；不覆盖已有目录，不改变已确认统计。

report.json 必需字段：

- `client`：明确客户名。
- `images_dir`：相对 report.json 的图片目录（原始媒体下载或真实视频抽帧）。
- `stats`：既有 feature-stats.schema.md 的 STATS；meta 含 sample_n/cite_sum/unique_questions/max_app_rate/sector/monitor_date/platform；缺失率用 null。分类附 description；title_examples 每项附 style/formula/analysis。
- `data`：完整样本数组；沿用模板字段，每条含 rank/video_id/url/title/cite_count/content_type/images/original_desc/transcript；新增 title_has_brand、visual_status。图片不可跨视频复用；原始标签另存完整证据。
- `findings`：五条本批结论，依次对应时长页数、点赞散点、粉丝分组、点赞分组、收藏分组；无有效数据则写无法判断及原因。
- `duration_reading`：本批时长和页数图的补充解读，不照抄旧结论。
- `cases`、`copy_examples`：案例数组，每项结构如下。copy_examples 不要求 frames。

```json
{
  "rank": 1,
  "heading": "从用户问题引出比较对象",
  "source_field": "original_desc",
  "frames": [{"file": "01_1.png", "label": "首图", "source_ref": "capture-ledger.json:video_id/frames/0"}],
  "paragraphs": [{"text": "原文完整段落", "point": "先限定选购问题", "note": "点出具体措辞及写法作用。"}]
}
```

source_field 只能 original_desc/transcript/image_text；拼接 paragraphs.text 必须等于对应源文（仅允许排版空白差异）。transcript 案例的 transcript_status 可为 verified 或 pending。verified 必须来自真实音频校对，不能为了通过脚本随意填写。pending 表示取得完整自动转写但尚未核对，构建器必须在每个案例中显示“自动转写，待核对”，不得省略真实原文、画面及采集记录。每条案例的 source_ref 指向采集台账，帧须含源视频 ID、时点/页序、文件路径。

系统模式必须另读 system-mode.md：版本 video-2026-09-25-v3，以冻结 videoCandidates 为唯一候选集合，16 个采集字段含 image_text。图文案例 source_field=image_text，混剪/口播=transcript；original_desc 仅用于发布文案对照。生成器输出稳定的证据节点：案例 video-case-{rank}、全文 video-case-{rank}-text、帧 video-case-{rank}-frame-{i}；文案对照用 video-copy-{rank}；样本库帧用 sample-{rank}-frame-{j}，帧序从 1 起。同一分组不得重复 rank。

系统报告沿用已批准 template.html 的完整 style 块，禁止追加或修改 CSS。证据 ID、散列与状态只存在于机器文件及 HTML 属性，不能显示在客户报告正文。全文、图片和缺失记录的详细字段按 system-mode.md，不以一张来源不明的图或一句非空文本充当采集成功。
- 例外（sky 批准，2026-09-28）：样本卡「查看完整口播」在本地预览中以弹窗打开（遮罩、可滚动正文、关闭按钮/Esc/点击遮罩关闭、标题为排名＋视频标题）。弹窗由脚本在点击时创建、用行内样式排版、关闭即移除，不改动已批准 style 块（系统按样式散列核验）；静态导出不含该弹窗，全文弹窗由系统导出脚本生成。

生成器只检查部分结构约束，不证明数据和转写真实性；完整验收按 qa-checklist.md。
