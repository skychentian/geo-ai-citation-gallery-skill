# 标签保留、分析与展示规则

`hashtags_raw` 保存完整原始输入；`hashtags` 保存 Unicode NFKC 规范化、去重后的全部真实标签。历史样本分析不按发布限制裁剪。

1. 页面抓到多少真实标签就保留多少；无法确定标签边界时标缺口，不猜补。
2. 不按赛道词、品牌词等优先级挑选样本标签。展示摘要可用 `hashtags_display`，不得回写覆盖分析字段。
3. 规范化：统一 `#` 前缀；去重（大小写/全半角同一）；去空标签；不要把整句发布文案拆成伪标签。
4. 词频分析使用完整规范化列表，按视频计数；作者标签与人工归纳主题分开。新作品的发布限制在具体发布任务另行核实，不从旧模板推定。

执行规范化（默认输出到 stdout，不原地修改；--inplace 才更新 JSON 字段）：

```bash
python scripts/normalize_hashtags.py path/to/meta.json
# 如需显示摘要：加 --limit 5，只生成 hashtags_display，不截断 hashtags
```
