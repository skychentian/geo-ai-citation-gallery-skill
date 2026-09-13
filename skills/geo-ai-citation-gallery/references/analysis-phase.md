# 分析阶段：防上下文爆炸（必须拆子 Agent）

## 为什么要拆

Top10 起步，每条文案上千字时，正文总量轻松几十篇。
**主会话若自己通读全部再写偏好，上下文会被文案占满，后半段只能写出很浅的结论**——这不是模板问题，是上下文预算问题。

因此：**提取 / 拉取 / 抓画面留在主会话；偏好写作必须派子 Agent。**

## 主会话在分析阶段只做调度

拉取与抓画面完成后，主会话：

1. 读 `_机器可读/top.json`，汇总 `analysis_eligible=true` 的清单（只保留：平台、rank、title、script_path、account、citation_count）。
2. **不要**把全量文案读进主会话。
3. 派子 Agent → 等落地 → **把洞察写入晨光陶瓷画廊五 Tab**（主交付）→ 可选落盘 `偏好分析.md`（内部归档）→ 写 README → `finalize_package.py`。

## 子 Agent 组织方式（按包模式）

**仅抖音（scope=仅抖音）：**
- Top < 15：**一个子 Agent** 读全部 `analysis_eligible=true` 文案，按模板产出偏好洞察。
- Top ≥ 15：拆三个子任务，主会话合并：
  - A：标题/文案特征 + 话题标签
  - B：口播结构类型 + 内容类型分布
  - C：账号类型 + 数据/时长特征 + 可复制写法
  每个子 Agent 只读自己那部分样本。

**全部视频平台（scope=all）：**
- 每平台一个子 Agent 写 `平台偏好/<平台名>.md`，再派 1 个总论子 Agent 综合。

## 写到哪里（统一技能）

| 产物 | 是否对客 | 说明 |
|------|----------|------|
| `gallery/index.html` 五 Tab | **主交付** | 特征总结 / 内容分类 / 标题·正文·标签 / 互动与时长 / 详情；套 `assets/template.html` |
| `偏好分析.md` | 可选归档 | 结构见 [`video-preference-template.md`](video-preference-template.md) |
| 绿头 KPI HTML | **不要** | `assets/legacy/` 仅存档，禁止当客户主页 |

阶段口径 → [`stage-guidance.md`](stage-guidance.md)。

## 子 Agent 指令要点

- 只读清单内文件，禁止去读其他平台/其他批次的文案
- 严格按偏好模板结构写（标题/文案特征表、口播结构类型表、内容类型、5～7 条写法）
- 不合格样本若被误放进清单，在「样本与可信度」里剔除并说明
- 数据（时长/播放量/账号）以 `top.json` / 抓取 meta 为准，拉不到就写「未获取」/「暂未抓取到」，不要编
- 写完即停，不要收尾、不要改 top.json
- 标签分析只用截断后 ≤5 的列表（见 [`hashtags.md`](hashtags.md)）

## 质量闸门（主会话检查）

收尾前抽查：

- 画廊五 Tab 是否有实质洞察（非空壳占位）
- 若有 `偏好分析.md`：是否含「标题/文案特征」表与「口播结构类型」表；篇幅是否明显过短 → 打回
- 是否误把 `analysis_eligible=false` 的纯 BGM/无口播样本当范文
- 是否编造了 `top.json` / engagement 里没有的播放量/点赞数
- 画廊用词是否为「引用*」且标签 ≤5（再过 [`qa-checklist.md`](qa-checklist.md)）
