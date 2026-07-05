---
name: serenity-stock-tracker
description: >
  追踪 Serenity (@aleabitoreddit) 公开 X 贴文中的股票观点。当用户要求
  "Serenity dashboard"、询问某个 ticker 在 Serenity 语料中的观点
  （如 "Tell me about SIVE"、"AXTI 有什么风险"、"哪些股票他看多"）、
  或想更新/查看 Serenity 股票追踪数据时使用。仅为公开贴文的研究介面，
  不构成投资建议，绝不自动下单。
---

# Serenity Stock Tracker

追踪 **Serenity ([@aleabitoreddit](https://x.com/aleabitoreddit))** —— AI/半导体
供应链分析师 —— 公开贴文中的 `$TICKER` 提及，生成互动仪表盘与个股 AI 观点综述。

所有命令在本 skill 目录下运行（`pipeline.py` 所在目录）。

## 数据新鲜度（每次使用前检查）

上游存档（GitHub: yan-labs/serenity-aleabitoreddit）约每半小时更新一次。
若 `data/aleabitoreddit_tweets.json` 修改时间超过 1 小时，先刷新：

```bash
python3 pipeline.py update && python3 pipeline.py build
```

价格数据（`data/prices.json`）超过 1 天则追加 `python3 pipeline.py prices`。

## 工作流 (a)：生成仪表盘 —— "Serenity dashboard"

```bash
python3 pipeline.py dashboard    # 数据已新鲜时
# 或完整重建：
python3 pipeline.py all
```

产物是自包含的 `data/dashboard.html`，直接在浏览器打开（`open data/dashboard.html`）。
包含：今日 / 近 7 天 / 近 28 天 / 近 90 天四个视图、每只股票的提及次数、
看多/中性/看空分布、自首次提及以来的价格走势、每条提及的原文链接。

## 工作流 (b)：个股深度问答 —— "Tell me about SIVE"

1. 导出该 ticker 的全部提及原文：

   ```bash
   python3 pipeline.py ticker SIVE
   ```

2. **通读原文后自行判断立场** —— 导出里的 `[bullish/neutral/bearish]`
   标签只是关键词启发式粗标，以你对原文的理解为准。
3. 按以下结构综述（每一条都附贴文链接）：
   - **最新明确立场**：他最近一次对该股的清晰表态 + 日期 + 链接
   - **论点叙事**：他的 thesis 如何随时间演变（供应链瓶颈逻辑、
     催化剂、立场反转都要点出）
   - **三则定义性贴文**：最能代表其观点的 3 条原文 + 各一句解释
   - **风险提及**：他自己点名过的风险/担忧（稀释、ATM、客户集中等）
4. 结尾必须声明：立场为 AI 推断可能不准、这是公开贴文聚合而非投资建议、
   他的收益自报未经验证。

## 工作流 (c)：横向问题 —— "哪些股票他看多？"

```bash
python3 pipeline.py stats        # 全期提及排行
```

再结合近期窗口（读取 `data/mentions.json` 过滤最近 N 天），
对候选名单逐个抽查原文确认立场后作答，不要只依赖启发式标签。

## 边界

- 绝不下单、不给出买卖指令；输出一律框定为"他的公开观点整理"。
- 他交易高波动小盘股并自报极高收益，未经验证且有幸存者偏差 —— 每次
  给观点都要带上这一句。
- 数据缺口：非美股需要交易所后缀（见 `pipeline.py` 的 `YAHOO_MAP`），
  遇到无价格的 ticker 先检查是否为国际上市。
