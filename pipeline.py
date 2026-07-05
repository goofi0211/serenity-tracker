#!/usr/bin/env python3
"""Serenity Stock Tracker pipeline.

复刻 capafy.ai 的 serenity-stock-tracker skill：
  update    从 GitHub (yan-labs/serenity-aleabitoreddit) 拉取最新推文存档
  build     抽取 $TICKER mentions + 关键词启发式立场分类 -> data/mentions.json
  prices    用 Yahoo chart API 抓取热门 ticker 日线 -> data/prices.json
  dashboard 生成自包含 HTML 仪表盘 -> data/dashboard.html
  ticker X  输出某个 ticker 的全部 mentions（供 AI 深度分析用）
  all       update + build + prices + dashboard
"""
import argparse
import datetime as dt
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
ARCHIVE_URL = "https://raw.githubusercontent.com/yan-labs/serenity-aleabitoreddit/main/data/aleabitoreddit_tweets.json"
ARCHIVE_PATH = DATA / "aleabitoreddit_tweets.json"
MENTIONS_PATH = DATA / "mentions.json"
PRICES_PATH = DATA / "prices.json"
DASHBOARD_PATH = DATA / "dashboard.html"

CASHTAG_RE = re.compile(r"(?<![A-Za-z0-9_])\$([A-Z][A-Z0-9.]{0,9})(?![A-Za-z0-9_])")
NOISE_SYMBOLS = {"AI", "I", "A", "USD", "US", "CEO", "ETF", "IPO", "GAAP", "ARR", "GPU", "CPO", "HBM", "M", "B", "K", "T", "EPS", "PE", "YTD"}

BULLISH_WORDS = [
    "bullish", "long ", "bought", "buying", "buy ", "adding", "added",
    "accumulat", "undervalued", "cheap", "underpriced", "mispriced",
    "bottleneck", "chokepoint", "breakout", "conviction", "upside",
    "winner", "beat", "beats", "moon", "top pick", "load", "loaded",
    "position in", "sole supplier", "monopoly", "no.1", "market leader",
]
BEARISH_WORDS = [
    "bearish", "short ", "shorted", "sold", "selling", "sell ", "trim",
    "overvalued", "overpriced", "avoid", "dilution", "atm offering",
    "downside", "miss", "missed", "scam", "fraud", "puts", "exit",
    "red flag", "warning", "cut ", "stay away", "bubble", "crash",
]


def log(msg):
    print(msg, flush=True)


def classify_stance(text):
    """关键词启发式立场分类（bullish/bearish/neutral）。

    与原版一样是"AI 推断可能不准"的粗标签；个股深度分析时由
    Claude 重新阅读原文修正（见 SKILL.md）。
    """
    t = text.lower()
    bull = sum(1 for w in BULLISH_WORDS if w in t)
    bear = sum(1 for w in BEARISH_WORDS if w in t)
    if bull > bear:
        return "bullish"
    if bear > bull:
        return "bearish"
    return "neutral"


def cmd_update():
    DATA.mkdir(exist_ok=True)
    log(f"downloading {ARCHIVE_URL} ...")
    req = urllib.request.Request(ARCHIVE_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = resp.read()
    ARCHIVE_PATH.write_bytes(body)
    log(f"saved {len(body) / 1e6:.1f} MB -> {ARCHIVE_PATH}")


def load_archive():
    if not ARCHIVE_PATH.exists():
        sys.exit("archive missing; run: python3 pipeline.py update")
    return json.loads(ARCHIVE_PATH.read_text())


def extract_symbols(text):
    found = set()
    for m in CASHTAG_RE.finditer(text or ""):
        s = m.group(1).upper().rstrip(".")
        if s not in NOISE_SYMBOLS and 1 < len(s) <= 10:
            found.add(s)
    return sorted(found)


def cmd_build():
    tweets = load_archive()
    mentions = []
    for t in tweets:
        text = t.get("text") or ""
        symbols = extract_symbols(text)
        if not symbols:
            continue
        stance = classify_stance(text)
        iso = t.get("createdAtISO") or ""
        screen = "aleabitoreddit"
        tid = t.get("id")
        for s in symbols:
            mentions.append({
                "symbol": s,
                "tweet_id": tid,
                "time": iso,
                "stance": stance,
                "text": text,
                "url": f"https://x.com/{screen}/status/{tid}",
                "likes": eval_metrics(t).get("likes", 0),
                "views": eval_metrics(t).get("views", 0),
            })
    mentions.sort(key=lambda m: m["time"])
    MENTIONS_PATH.write_text(json.dumps(mentions, ensure_ascii=False))
    symbols = {m["symbol"] for m in mentions}
    log(f"{len(mentions)} mentions across {len(symbols)} tickers -> {MENTIONS_PATH}")


def eval_metrics(t):
    m = t.get("metrics")
    if isinstance(m, dict):
        return m
    if isinstance(m, str):
        try:
            import ast
            return ast.literal_eval(m)
        except Exception:
            return {}
    return {}


def load_mentions():
    if not MENTIONS_PATH.exists():
        sys.exit("mentions missing; run: python3 pipeline.py build")
    return json.loads(MENTIONS_PATH.read_text())


# Serenity 常提的非美股上市代码 -> Yahoo Finance 代码
YAHOO_MAP = {
    "SIVE": "SIVE.ST",    # Sivers Semiconductors (Stockholm)
    "SOI": "SOI.PA",      # Soitec (Paris)
    "IQE": "IQE.L",       # IQE plc (London)
    "RPI": "RPI.L",       # Raspberry Pi Holdings (London)
    "LPK": "LPK.DE",      # LPKF Laser (Xetra)
    "ALRIB": "ALRIB.PA",  # Riber SA (Euronext Growth Paris)
    "HPS.A": "HPS-A.TO",  # Hammond Power Solutions (Toronto)
    "XFAB": "XFAB.PA",    # X-FAB Silicon Foundries (Paris)
    "APPL": "AAPL",       # 原帖常见的 Apple 拼写
}


def yahoo_chart(symbol, start, end):
    symbol = YAHOO_MAP.get(symbol, symbol)
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.parse.quote(symbol)}?period1={int(start.timestamp())}"
        f"&period2={int(end.timestamp())}&interval=1d&events=history"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def cmd_prices(min_mentions=10, max_symbols=120):
    mentions = load_mentions()
    counts = {}
    first_seen = {}
    for m in mentions:
        counts[m["symbol"]] = counts.get(m["symbol"], 0) + 1
        first_seen.setdefault(m["symbol"], m["time"])
    symbols = sorted((s for s, c in counts.items() if c >= min_mentions),
                     key=lambda s: -counts[s])[:max_symbols]
    now = dt.datetime.now(dt.timezone.utc)
    prices = {}
    for i, symbol in enumerate(symbols):
        start = dt.datetime.fromisoformat(first_seen[symbol]) - dt.timedelta(days=5)
        try:
            data = yahoo_chart(symbol, start, now + dt.timedelta(days=2))
            result = (data.get("chart") or {}).get("result") or []
            if not result:
                log(f"  [{i + 1}/{len(symbols)}] {symbol}: no result")
                continue
            res = result[0]
            timestamps = res.get("timestamp") or []
            closes = ((res.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
            series = [
                [dt.datetime.fromtimestamp(ts, dt.timezone.utc).date().isoformat(), round(c, 3)]
                for ts, c in zip(timestamps, closes) if c is not None
            ]
            if series:
                prices[symbol] = series
            log(f"  [{i + 1}/{len(symbols)}] {symbol}: {len(series)} bars")
            time.sleep(0.25)
        except Exception as exc:
            log(f"  [{i + 1}/{len(symbols)}] {symbol}: FAILED {exc}")
    PRICES_PATH.write_text(json.dumps(prices))
    log(f"{len(prices)} price series -> {PRICES_PATH}")


def cmd_ticker(symbol):
    symbol = symbol.upper().lstrip("$")
    rows = [m for m in load_mentions() if m["symbol"] == symbol]
    if not rows:
        log(f"no mentions found for ${symbol}")
        return
    log(f"${symbol}: {len(rows)} mentions, {rows[0]['time'][:10]} -> {rows[-1]['time'][:10]}\n")
    for m in rows:
        log(f"--- {m['time']} [{m['stance']}] likes={m['likes']} views={m['views']}")
        log(m["text"])
        log(m["url"] + "\n")


def cmd_dashboard():
    import build_dashboard
    build_dashboard.build(load_mentions(),
                          json.loads(PRICES_PATH.read_text()) if PRICES_PATH.exists() else {},
                          DASHBOARD_PATH)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=["update", "build", "prices", "dashboard", "ticker", "all", "stats"])
    ap.add_argument("symbol", nargs="?", help="ticker for the `ticker` command")
    ap.add_argument("--min-mentions", type=int, default=10)
    ap.add_argument("--max-symbols", type=int, default=120)
    args = ap.parse_args()
    if args.command in {"update", "all"}:
        cmd_update()
    if args.command in {"build", "all"}:
        cmd_build()
    if args.command in {"prices", "all"}:
        cmd_prices(args.min_mentions, args.max_symbols)
    if args.command in {"dashboard", "all"}:
        cmd_dashboard()
    if args.command == "ticker":
        if not args.symbol:
            sys.exit("usage: pipeline.py ticker SYMBOL")
        cmd_ticker(args.symbol)
    if args.command == "stats":
        mentions = load_mentions()
        counts = {}
        for m in mentions:
            counts[m["symbol"]] = counts.get(m["symbol"], 0) + 1
        log(f"mentions={len(mentions)} tickers={len(counts)}")
        for s, c in sorted(counts.items(), key=lambda kv: -kv[1])[:30]:
            log(f"  {s:8s} {c}")


if __name__ == "__main__":
    main()
