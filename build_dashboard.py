#!/usr/bin/env python3
"""生成自包含 HTML 仪表盘（由 pipeline.py dashboard 调用）。"""
import datetime as dt
import json
from pathlib import Path

WINDOW_DAYS = 90
EXCERPT_LEN = 180
MAX_PRICE_POINTS = 120
STANCE_CODE = {"bullish": 0, "neutral": 1, "bearish": 2}

TEMPLATE_PATH = Path(__file__).resolve().parent / "dashboard_template.html"


def downsample(series, max_points=MAX_PRICE_POINTS):
    if len(series) <= max_points:
        return series
    step = len(series) / max_points
    out = [series[int(i * step)] for i in range(max_points)]
    if out[-1] != series[-1]:
        out.append(series[-1])
    return out


def build(mentions, prices, out_path):
    latest = max(m["time"] for m in mentions)
    latest_dt = dt.datetime.fromisoformat(latest)
    cutoff = (latest_dt - dt.timedelta(days=WINDOW_DAYS)).isoformat()

    tickers = {}
    for m in mentions:
        t = tickers.setdefault(m["symbol"], {"total": 0, "first": m["time"][:10], "last": "", "sb": 0, "sn": 0, "sr": 0})
        t["total"] += 1
        t["last"] = m["time"][:10]
        t["sb" if m["stance"] == "bullish" else ("sr" if m["stance"] == "bearish" else "sn")] += 1

    window = [
        [m["symbol"], m["tweet_id"], m["time"][:16].replace("T", " "),
         STANCE_CODE[m["stance"]],
         (m["text"][:EXCERPT_LEN] + ("…" if len(m["text"]) > EXCERPT_LEN else "")).replace("\n", " ")]
        for m in mentions if m["time"] >= cutoff
    ]
    window.reverse()  # newest first

    window_syms = {w[0] for w in window}
    price_out = {s: downsample(v) for s, v in prices.items() if s in window_syms}

    data = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat()[:16].replace("T", " ") + " UTC",
        "latest": latest[:16].replace("T", " "),
        "tickers": {s: t for s, t in tickers.items() if s in window_syms},
        "mentions": window,
        "prices": price_out,
        "totalTweets": len({m["tweet_id"] for m in mentions}),
        "totalTickers": len(tickers),
        "totalMentions": len(mentions),
    }

    template = TEMPLATE_PATH.read_text()
    html = template.replace("/*__DATA__*/", "const DATA = " + json.dumps(data, ensure_ascii=False) + ";")
    Path(out_path).write_text("<!doctype html>\n" + html)
    print(f"dashboard: {len(window)} window mentions, {len(window_syms)} tickers, "
          f"{len(price_out)} price series -> {out_path} ({Path(out_path).stat().st_size / 1e6:.1f} MB)")
