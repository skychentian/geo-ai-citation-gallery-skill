# GEO AI 高引用视频画廊 Skill

一句话：装好后让 AI 从诊断包做出「晨光陶瓷」风格客户高引用证据页（抓画面、分析、出 HTML、发布）。

## 安装（只这一条）

```bash
npx skills add skychentian/geo-ai-citation-gallery-skill --skill geo-ai-citation-gallery
```

## 装完怎么跟 AI 说话

复制粘贴即可（附上诊断包路径或 zip）：

```text
按 @geo-ai-citation-gallery，用这份诊断包做客户高引用画廊，赛道是 XX。
```

AI 会按 skill 里的端到端步骤自己跑完。**不用读 capture 文档，不用翻一堆 md。**

## 抓画面

抓图详情见 skill 步骤 3「抓画面（脚本 + 浏览器，已验证）」+ `skills/geo-ai-citation-gallery/assets/scripts/`（`capture_server.py` / `page_hook.example.js`）。成品图来自脚本下载，不是浏览器截屏。


## 用词与标签

- 指标展示用「引用次数 / 引用率」，不要写「应用次数 / 应用率」。
- 抖音话题标签每条最多 **5** 个；入库与页面展示都截断到 5。
