# Serenity Stock Tracker（复刻版）

复刻 [capafy.ai 的 serenity-stock-tracker](https://capafy.ai/zh-hant/agent/serenity-stock-tracker/2521387714)：
追踪 **Serenity ([@aleabitoreddit](https://x.com/aleabitoreddit))**（AI/半导体供应链分析师）
公开 X 贴文中的股票观点，生成互动仪表盘 + 个股 AI 问答。

> 非投资建议。立场标签为自动推断，可能不准确；与 Serenity 本人无关。

## 原版是怎么做的（拆解结论）

Capafy 那个 skill 是闭源的，但从商品页元数据（"External API: github"、每小时更新、
Claude Sonnet）和几个同类开源项目可以还原出架构：

```
┌─ 链下管线（供应商服务器，每小时跑）──────────────────────┐
│ 抓 @aleabitoreddit 的 X 贴文（GraphQL 爬取，非官方 API）   │
│  → 抽取 $TICKER cashtag                                   │
│  → AI 给每条提及打 bullish/bearish/neutral 标签           │
│  → 结果推到 GitHub 仓库（这就是 "External API: github"）  │
└───────────────────────────────────────────────────────────┘
┌─ skill 本体（用户会话里跑）───────────────────────────────┐
│ "dashboard" → 从 GitHub 拉数据 + Yahoo 拉价格             │
│             → 渲染自包含 HTML（日/周/月/季四视图）        │
│ "问个股"    → 取该 ticker 全部提及原文喂给 Claude          │
│             → 综述：最新立场/论点演变/三则定义性贴文/风险 │
└───────────────────────────────────────────────────────────┘
```

参考的开源实现：
- [yan-labs/serenity-aleabitoreddit](https://github.com/yan-labs/serenity-aleabitoreddit)
  —— 完整推文存档（约每半小时更新）+ 分析型 skill。**本项目直接用它当上游数据源**，
  从而免去自己维护 X 登录态爬虫。
- [haskaomni/serenity](https://github.com/haskaomni/serenity)
  —— 展示了链下管线的做法：浏览器复制 X GraphQL curl → 解析贴文 → SQLite → Yahoo 日线。

本复刻与原版的差异：批量立场标签用关键词启发式（原版用 Claude 逐条打标），
但个股深度分析时由 Claude 重读原文修正，效果对齐；数据更新靠上游存档而非自建爬虫。

## 使用

```bash
python3 pipeline.py all          # 更新存档 + 抽取提及 + 抓价格 + 生成仪表盘
open data/dashboard.html         # 查看仪表盘
python3 pipeline.py ticker SIVE  # 导出某 ticker 全部提及（供 AI 综述）
python3 pipeline.py stats        # 提及排行
```

作为 agent skill 使用：把本目录放进 `.claude/skills/`，对 Claude 说
"Serenity dashboard" 或 "Tell me about AXTI" 即可（见 `SKILL.md`）。

## 文件

| 文件 | 作用 |
|---|---|
| `pipeline.py` | 数据管线：update / build / prices / dashboard / ticker / stats |
| `build_dashboard.py` | 把 mentions + prices 嵌进模板生成自包含 HTML |
| `dashboard_template.html` | 仪表盘前端（四视图、立场分布、价格走势、原文链接、深浅主题） |
| `SKILL.md` | agent skill 定义（dashboard / 个股问答 / 横向问题三个工作流） |
| `data/` | 生成物：推文存档、mentions.json、prices.json、dashboard.html |

## 已知限制

- 立场启发式只看关键词，讽刺/反串会误判 —— 所以个股结论必须回到原文。
- 非美股需要 Yahoo 交易所后缀，映射表在 `pipeline.py` 的 `YAHOO_MAP`，遇缺补录。
- 上游存档若停更，需要按 haskaomni/serenity 的 curl 方案自建抓取。
