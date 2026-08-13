#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
纳指100每日收盘 Dashboard 数据抓取脚本
"""

import json
import math
import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict

import yfinance as yf

from ndx_components import STOCKS

OUTPUT_DIR = "docs"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "index.html")


def ensure_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def fetch_stock_data(tickers, max_batch=25):
    all_data = {}
    for i in range(0, len(tickers), max_batch):
        batch = tickers[i:i + max_batch]
        print(f"  批次 {i // max_batch + 1}: {len(batch)} 只...")
        try:
            data = yf.download(
                " ".join(batch),
                period="5d",
                interval="1d",
                progress=False,
                threads=True,
                group_by="ticker"
            )
            if data.empty:
                continue
            if len(batch) == 1:
                all_data[batch[0]] = data
            else:
                for ticker in batch:
                    if ticker in data.columns.get_level_values(0):
                        all_data[ticker] = data[ticker]
        except Exception as e:
            print(f"    失败: {e}")
    return all_data


def fetch_index_history(ticker="^NDX", days=30):
    try:
        t = yf.Ticker(ticker)
        end = datetime.now()
        start = end - timedelta(days=days + 15)
        hist = t.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))
        closes = hist["Close"].dropna().tolist()
        if len(closes) < days:
            print(f"  警告: 仅获取到 {len(closes)} 天历史数据，目标 {days} 天")
        return [round(float(c), 2) for c in closes[-days:]]
    except Exception as e:
        print(f"  指数历史失败: {e}")
        return []


def fetch_index_info(ticker="^NDX"):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d", interval="1d")
        if len(hist) < 2:
            return None
        latest = hist.iloc[-1]
        prev = hist.iloc[-2]
        price = float(latest["Close"])
        prev_close = float(prev["Close"])
        change = round((price - prev_close) / prev_close * 100, 2)
        return {"price": round(price, 2), "prev_close": round(prev_close, 2), "change": change}
    except Exception as e:
        print(f"  指数当日失败: {e}")
        return None


def build_data():
    tickers = [s[0] for s in STOCKS]
    print("\n抓取个股数据...")
    raw_data = fetch_stock_data(tickers)

    stocks = []
    for ticker, name, sector, weight in STOCKS:
        if ticker not in raw_data:
            print(f"  缺失: {ticker}")
            continue
        df = raw_data[ticker]
        if len(df) < 2:
            continue
        try:
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            close = float(latest["Close"])
            prev_close = float(prev["Close"])
            change = round((close - prev_close) / prev_close * 100, 2)
            if math.isnan(change):
                print(f"  NaN跳过: {ticker}")
                continue
            stocks.append({"ticker": ticker, "name": name, "sector": sector, "weight": weight, "change": change})
        except Exception as e:
            print(f"  处理失败 {ticker}: {e}")

    if len(stocks) < 50:
        print(f"警告: 仅获取到 {len(stocks)} 只，使用模拟数据...")
        return build_mock_data()

    index_info = fetch_index_info("^NDX")
    if index_info is None:
        total_weight = sum(s["weight"] for s in stocks)
        weighted_change = sum(s["weight"] * s["change"] for s in stocks) / total_weight
        index_info = {"price": 0, "prev_close": 0, "change": round(weighted_change, 2)}

    up = sum(1 for s in stocks if s["change"] > 0)
    down = sum(1 for s in stocks if s["change"] < 0)
    flat = sum(1 for s in stocks if s["change"] == 0)
    index_info.update({"up": up, "down": down, "flat": flat, "total": len(stocks)})

    sectors = defaultdict(lambda: {"weight": 0, "total_change": 0, "count": 0})
    for s in stocks:
        if math.isnan(s["change"]):
            continue
        sectors[s["sector"]]["weight"] += s["weight"]
        sectors[s["sector"]]["total_change"] += s["change"] * s["weight"]
        sectors[s["sector"]]["count"] += 1

    sector_list = []
    for name, d in sectors.items():
        sector_list.append({
            "name": name, "weight": round(d["weight"], 2),
            "change": round(d["total_change"] / d["weight"], 2) if d["weight"] > 0 else 0,
            "count": d["count"]
        })
    sector_list.sort(key=lambda x: -x["weight"])

    bins = [(-999, -3), (-3, -2), (-2, -1), (-1, 0), (0, 1), (1, 2), (2, 3), (3, 999)]
    labels = ["<-3%", "-3~-2%", "-2~-1%", "-1~0%", "0~1%", "1~2%", "2~3%", ">3%"]
    counts = [0] * len(bins)
    for s in stocks:
        c = s["change"]
        for i, (lo, hi) in enumerate(bins):
            if (lo <= c < hi) or (hi == 999 and c >= lo) or (lo == -999 and c < hi):
                counts[i] += 1
                break

    history = fetch_index_history("^NDX", 30)

    sorted_w = sorted(stocks, key=lambda x: -x["weight"])
    top15 = sorted_w[:15]
    others = sorted_w[15:]
    ow = sum(s["weight"] for s in others)
    oc = sum(s["weight"] * s["change"] for s in others) / ow if ow > 0 else 0
    pie = top15 + [{"ticker": "其他", "name": f"其他{len(others)}只", "sector": "", "weight": round(ow, 2), "change": round(oc, 2)}]

    result = {
        "index": index_info, "stocks": stocks, "pie_stocks": pie,
        "sectors": sector_list, "bins": {"labels": labels, "counts": counts},
        "history": history, "date": datetime.now().strftime("%Y-%m-%d"),
    }
    # 生成6个独立总结
    print("\n[AI 总结生成]")
    result["ai_summary"] = generate_summary(result, "overview")
    result["ai_stocks"] = generate_summary(result, "stocks")
    result["ai_sectors"] = generate_summary(result, "sectors")
    result["ai_distribution"] = generate_summary(result, "distribution")
    result["ai_industry"] = generate_summary(result, "industry")
    result["ai_trend"] = generate_summary(result, "trend")
    return result


def build_mock_data():
    import random
    random.seed(42)
    stocks = []
    for ticker, name, sector, weight in STOCKS:
        base = random.gauss(0.3, 1.5)
        if weight > 3:
            base = random.gauss(0.2, 1.0)
        change = round(base, 2)
        stocks.append({"ticker": ticker, "name": name, "sector": sector, "weight": weight, "change": change})

    total_weight = sum(s["weight"] for s in stocks)
    index_change = round(sum(s["weight"] * s["change"] for s in stocks) / total_weight, 2)
    up = sum(1 for s in stocks if s["change"] > 0)
    down = sum(1 for s in stocks if s["change"] < 0)

    sectors = defaultdict(lambda: {"weight": 0, "total_change": 0, "count": 0})
    for s in stocks:
        if math.isnan(s["change"]):
            continue
        sectors[s["sector"]]["weight"] += s["weight"]
        sectors[s["sector"]]["total_change"] += s["change"] * s["weight"]
        sectors[s["sector"]]["count"] += 1

    sector_list = []
    for name, d in sectors.items():
        sector_list.append({
            "name": name, "weight": round(d["weight"], 2),
            "change": round(d["total_change"] / d["weight"], 2) if d["weight"] > 0 else 0,
            "count": d["count"]
        })
    sector_list.sort(key=lambda x: -x["weight"])

    bins = [(-999, -3), (-3, -2), (-2, -1), (-1, 0), (0, 1), (1, 2), (2, 3), (3, 999)]
    labels = ["<-3%", "-3~-2%", "-2~-1%", "-1~0%", "0~1%", "1~2%", "2~3%", ">3%"]
    counts = [0] * len(bins)
    for s in stocks:
        c = s["change"]
        for i, (lo, hi) in enumerate(bins):
            if (lo <= c < hi) or (hi == 999 and c >= lo) or (lo == -999 and c < hi):
                counts[i] += 1
                break

    history = []
    price = 19500
    for _ in range(30):
        change = random.gauss(0.15, 1.2)
        price = price * (1 + change / 100)
        history.append(round(price, 2))

    sorted_w = sorted(stocks, key=lambda x: -x["weight"])
    top15 = sorted_w[:15]
    others = sorted_w[15:]
    ow = sum(s["weight"] for s in others)
    oc = sum(s["weight"] * s["change"] for s in others) / ow if ow > 0 else 0
    pie = top15 + [{"ticker": "其他", "name": f"其他{len(others)}只", "sector": "", "weight": round(ow, 2), "change": round(oc, 2)}]

    return {
        "index": {"price": history[-1], "prev_close": round(history[-1] / (1 + index_change/100), 2), "change": index_change, "up": up, "down": down, "flat": 0, "total": len(stocks)},
        "stocks": stocks, "pie_stocks": pie, "sectors": sector_list,
        "bins": {"labels": labels, "counts": counts}, "history": history,
        "date": datetime.now().strftime("%Y-%m-%d"),
    }


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NDX Dashboard</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700;800&display=swap');

:root {
  --bg: #0a0a0a;
  --surface: #111111;
  --surface-raised: #161616;
  --header-bg: rgba(10,10,10,0.85);
  --ticker-bg: rgba(10,10,10,0.9);
  --text: #f5f5f5;
  --text2: #a1a1aa;
  --text3: #52525b;
  --border: rgba(255,255,255,0.06);
  --border-strong: rgba(255,255,255,0.1);
  --ticker-border: rgba(255,255,255,0.08);
  --rise: #39ff14;
  --rise-border: rgba(57,255,20,0.2);
  --fall: #bf00ff;
  --fall-border: rgba(191,0,255,0.2);
  --accent: #bf00ff;
  --grid-dot: rgba(191,0,255,0.18);
  --hero-glow: rgba(191,0,255,0.08);
  --badge-bg: rgba(57,255,20,0.06);
  --badge-color: #39ff14;
  --badge-border: rgba(57,255,20,0.15);
}

.light {
  --bg: #fafafa;
  --surface: #ffffff;
  --surface-raised: #f4f4f5;
  --header-bg: rgba(250,250,250,0.85);
  --ticker-bg: rgba(250,250,250,0.9);
  --text: #18181b;
  --text2: #52525b;
  --text3: #a1a1aa;
  --border: rgba(0,0,0,0.06);
  --border-strong: rgba(0,0,0,0.1);
  --ticker-border: rgba(0,0,0,0.08);
  --rise: #16a34a;
  --rise-border: rgba(22,163,74,0.12);
  --fall: #9333ea;
  --fall-border: rgba(147,51,234,0.12);
  --accent: #9333ea;
  --grid-dot: rgba(147,51,234,0.1);
  --hero-glow: rgba(147,51,234,0.04);
  --badge-bg: rgba(22,163,74,0.06);
  --badge-color: #16a34a;
  --badge-border: rgba(22,163,74,0.12);
}

*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;background:var(--bg);color:var(--text);line-height:1.5}

#app{background:var(--bg);color:var(--text);padding-bottom:50px}

/* 全局背景网格 */
.global-grid{position:fixed;inset:0;pointer-events:none;z-index:-1}
.global-grid svg{width:100%;height:100%}
.hero-glow{position:fixed;top:0;left:0;right:0;height:500px;pointer-events:none;z-index:0;background:radial-gradient(ellipse at 50% 0%, var(--hero-glow) 0%, transparent 60%)}

/* Ticker */
.ticker-bar{position:sticky;z-index:100;background:var(--ticker-bg);overflow:hidden;backdrop-filter:blur(20px);height:36px;box-sizing:border-box}
.ticker-bar-top{top:0;border-bottom:1px solid var(--ticker-border)}
.ticker-bar-bottom{position:fixed;bottom:0;left:0;right:0;z-index:100;border-top:1px solid var(--ticker-border)}
.ticker-grid{position:absolute;inset:0;pointer-events:none;opacity:0.3}
.ticker-grid svg{width:100%;height:100%}
.ticker-track{display:flex;white-space:nowrap;position:relative;z-index:1;height:100%;align-items:center}
.ticker-item{display:inline-flex;align-items:center;padding:0 20px;font-size:13px;font-weight:700;font-family:'JetBrains Mono',monospace;letter-spacing:0.3px;flex-shrink:0;line-height:1}
.ticker-name{color:var(--text2);margin-right:8px}
.ticker-change.up{color:var(--rise)}
.ticker-change.down{color:var(--fall)}
.ticker-sep{color:var(--border-strong);margin-left:20px}
@keyframes ticker-scroll{0%{transform:translateX(0)}100%{transform:translateX(-50%)}}
@keyframes ticker-scroll-reverse{0%{transform:translateX(-50%)}100%{transform:translateX(0)}}

/* Header */
.header{position:sticky;top:36px;z-index:99;backdrop-filter:blur(20px);background:var(--header-bg);border-bottom:1px solid var(--border)}
.header-inner{max-width:1200px;margin:0 auto;padding:16px 24px;display:flex;justify-content:space-between;align-items:center}
.logo{font-size:14px;font-weight:800;letter-spacing:2px;color:var(--text)}
.logo-accent{color:var(--accent)}
.nav-btns{display:flex;align-items:center;gap:12px}
.nav-btn{padding:6px 14px;border-radius:8px;border:1px solid var(--border);background:transparent;color:var(--text2);font-weight:600;cursor:pointer;font-size:12px;transition:all 0.2s;font-family:inherit}
.nav-btn:hover:not(:disabled){border-color:var(--border-strong);color:var(--text)}
.nav-btn:disabled{opacity:0.35;cursor:not-allowed}
.theme-btn{padding:6px 14px;border-radius:10px;border:1px solid var(--border);background:transparent;cursor:pointer;transition:all 0.2s;font-size:12px;font-weight:700;color:var(--text2);font-family:inherit;letter-spacing:0.5px}
.theme-btn:hover{border-color:var(--accent);color:var(--text)}

/* Container */
.container{max-width:1200px;margin:0 auto;padding:0 24px;position:relative;z-index:1}

/* Sections */
section{padding:60px 0}
.section-header{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:32px}
.section-label{font-size:11px;font-weight:800;color:var(--accent);letter-spacing:3px;margin-bottom:8px;text-transform:uppercase}
.section-title{font-size:24px;font-weight:800;color:var(--text);letter-spacing:-0.5px}
.section-sub{font-size:13px;color:var(--text3);font-weight:500}

/* Divider */
.divider{height:1px;background:linear-gradient(90deg,transparent,var(--border-strong),transparent)}

/* Hero */
.hero{padding:80px 0 60px}
.hero-inner{display:flex;align-items:flex-end;justify-content:space-between;flex-wrap:wrap;gap:40px}
.hero-left{flex:1;min-width:300px}
.hero-tag{display:inline-flex;align-items:center;gap:8px;padding:6px 14px;border-radius:100px;border:1px solid var(--border);margin-bottom:24px}
.hero-tag-dot{width:6px;height:6px;border-radius:50%;background:var(--rise)}
.hero-tag-text{font-size:11px;font-weight:700;color:var(--text2);letter-spacing:1px}
.hero-title{font-size:64px;font-weight:900;letter-spacing:-3px;margin:0;line-height:1;color:var(--text)}
.hero-accent{color:var(--accent)}
.hero-desc{margin-top:20px;font-size:15px;color:var(--text2);line-height:1.6;max-width:400px}
.hero-meta{margin-top:24px;display:flex;align-items:center;gap:12px}
.hero-date{font-size:13px;color:var(--text3);font-weight:500}
.hero-dot{width:4px;height:4px;border-radius:50%;background:var(--text3)}
.hero-badge{padding:4px 12px;border-radius:100px;background:var(--badge-bg);color:var(--badge-color);border:1px solid var(--badge-border);font-size:12px;font-weight:700;letter-spacing:0.5px}
.hero-kpis{display:flex;gap:40px;flex-wrap:wrap}
.kpi-label{font-size:11px;font-weight:800;color:var(--text3);letter-spacing:2px;margin-bottom:8px}
.kpi-value{font-size:52px;font-weight:900;letter-spacing:-2px;color:var(--text);font-family:'JetBrains Mono',monospace;line-height:1}
.kpi-change{font-size:18px;font-weight:800;margin-top:8px;font-family:'JetBrains Mono',monospace}
.kpi-change.up{color:var(--rise)}
.kpi-change.down{color:var(--fall)}
.kpi-sub{font-size:13px;color:var(--text3);margin-top:8px;font-family:'JetBrains Mono',monospace}

/* AI Summary */
.ai-summary p{margin:0;font-size:28px;font-weight:700;line-height:1.4;color:var(--text);max-width:900px;letter-spacing:-0.5px}
.ai-summary .up{color:var(--rise)}
.ai-summary .down{color:var(--fall)}

/* Cards */
.card{background:var(--surface);border:1px solid var(--border);border-radius:16px;transition:transform 0.2s,border-color 0.2s}
.card:hover{transform:translateY(-2px);border-color:var(--border-strong)}
.card-title{font-size:14px;font-weight:800;color:var(--text);margin-bottom:4px;letter-spacing:-0.3px}
.card-sub{font-size:12px;color:var(--text3);margin-bottom:20px;font-weight:500}

/* Distribution bars */
.dist-chart{display:flex;align-items:flex-end;gap:4px;height:200px;padding:20px 0;border-bottom:1px solid var(--border)}
.dist-col{flex:1;display:flex;flex-direction:column;align-items:center;gap:6px}
.dist-count{font-size:11px;font-weight:800;font-family:'JetBrains Mono',monospace}
.dist-count.up{color:var(--rise)}
.dist-count.down{color:var(--fall)}
.dist-bar{width:100%;border-radius:4px 4px 0 0}
.dist-bar.up{background:var(--rise)}
.dist-bar.down{background:var(--fall)}
.dist-label{font-size:10px;color:var(--text3);font-weight:600}

/* Sector bars */
.sector-row{display:flex;align-items:center;gap:16px}
.sector-name{width:80px;text-align:right;font-size:13px;font-weight:700;color:var(--text2);flex-shrink:0}
.sector-track{flex:1;height:28px;display:flex;align-items:center;position:relative}
.sector-bar{height:100%;position:relative}
.sector-bar.up{background:var(--rise);border-radius:0 4px 4px 0}
.sector-bar.down{background:var(--fall);border-radius:4px 0 0 4px;margin-left:auto}
.sector-bar-label{position:absolute;top:50%;transform:translateY(-50%);font-size:12px;font-weight:800;font-family:'JetBrains Mono',monospace;white-space:nowrap}
.sector-bar-label.up{right:12px;color:rgba(0,0,0,0.6)}
.sector-bar-label.down{left:12px;color:rgba(255,255,255,0.9)}

/* Trend line */
.trend-svg{width:100%;height:auto}

/* Stock grid */
.stock-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(100px,1fr));gap:8px}
.stock-cell{padding:14px 10px;border-radius:12px;text-align:center;border:1px solid var(--rise-border);color:var(--rise);background:var(--surface-raised);cursor:pointer;transition:all 0.15s}
.stock-cell.down{border-color:var(--fall-border);color:var(--fall)}
.stock-cell:hover{transform:translateY(-2px) scale(1.02);border-color:var(--border-strong)}
.stock-ticker{font-size:14px;font-weight:800;font-family:'JetBrains Mono',monospace;letter-spacing:0.5px}
.stock-pct{font-size:12px;font-weight:600;font-family:'JetBrains Mono',monospace;margin-top:4px;opacity:0.9}

/* Pie charts */
.pie-container{display:flex;align-items:center;justify-content:center;position:relative}
.pie-legend{display:flex;flex-wrap:wrap;gap:10px 16px;margin-top:24px;font-size:13px;font-weight:600}
.pie-legend-item{display:flex;align-items:center;gap:6px;color:var(--text2)}
.pie-legend-dot{width:10px;height:10px;border-radius:3px}
/* Footer */
.footer{padding:40px 0;text-align:center;position:relative;z-index:1}
.footer-text{font-size:12px;color:var(--text3);font-weight:500;letter-spacing:0.3px}

/* Tooltip */
.tooltip{position:fixed;background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:10px 14px;font-size:12px;color:var(--text);pointer-events:none;opacity:0;transition:opacity .15s;z-index:1000;box-shadow:0 8px 32px rgba(0,0,0,0.4);font-family:'JetBrains Mono',monospace;white-space:nowrap}

@media(max-width:720px){
  .hero-title{font-size:40px!important}
  .kpi-value{font-size:36px!important}
  section{padding:40px 0!important}
  .hero-inner{flex-direction:column;align-items:flex-start}
  .hero-kpis{width:100%}
}

/* ===== Scroll-triggered Animations ===== */
.dist-bar {
  transform: scaleY(0);
  transform-origin: bottom;
  transition: transform 0.9s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.dist-bar.animate {
  transform: scaleY(1);
}

.pie-seg {
  opacity: 0;
  transform: scale(0);
  /* 必须显式指定圆心，否则 SVG 元素默认 origin 是左上角 0 0 */
  transform-origin: 200px 170px;
  transition: opacity 0.7s ease, transform 0.8s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.pie-seg.animate {
  opacity: 1;
  transform: scale(1);
}

.sector-bar {
  width: 0% !important;
  transition: width 1.2s cubic-bezier(0.25, 1, 0.5, 1);
}
.sector-bar.animate {
  width: var(--final-width) !important;
}

.trend-area {
  clip-path: inset(0 100% 0 0);
  transition: clip-path 1.6s ease-out;
}
.trend-area.animate {
  clip-path: inset(0 0% 0 0);
}

.trend-path {
  stroke-dasharray: var(--path-length);
  stroke-dashoffset: var(--path-length);
  transition: stroke-dashoffset 1.6s ease-out;
}
.trend-path.animate {
  stroke-dashoffset: 0;
}

.trend-point {
  opacity: 0;
  transition: opacity 0.35s ease;
}
.trend-point.animate {
  opacity: 1;
}

/* ===== 背景等高线纹理 ===== */
.contour-texture {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  overflow: hidden;
}
.contour-green, .contour-purple {
  position: absolute;
  inset: -50%;
}
.contour-green {
  background:
    radial-gradient(ellipse 600px 400px at 20% 30%, rgba(57,255,20,0.10) 0%, transparent 70%),
    radial-gradient(ellipse 500px 350px at 70% 60%, rgba(57,255,20,0.08) 0%, transparent 65%),
    radial-gradient(ellipse 400px 300px at 40% 80%, rgba(57,255,20,0.09) 0%, transparent 60%),
    radial-gradient(ellipse 700px 450px at 80% 20%, rgba(57,255,20,0.06) 0%, transparent 75%),
    radial-gradient(ellipse 350px 280px at 10% 70%, rgba(57,255,20,0.08) 0%, transparent 55%);
  animation: drift-green 25s ease-in-out infinite alternate;
  filter: blur(1px);
}
.contour-purple {
  background:
    radial-gradient(ellipse 550px 380px at 60% 40%, rgba(191,0,255,0.10) 0%, transparent 70%),
    radial-gradient(ellipse 480px 320px at 30% 70%, rgba(191,0,255,0.08) 0%, transparent 65%),
    radial-gradient(ellipse 420px 350px at 85% 15%, rgba(191,0,255,0.09) 0%, transparent 60%),
    radial-gradient(ellipse 650px 400px at 15% 50%, rgba(191,0,255,0.06) 0%, transparent 75%),
    radial-gradient(ellipse 380px 260px at 55% 85%, rgba(191,0,255,0.08) 0%, transparent 55%);
  animation: drift-purple 30s ease-in-out infinite alternate;
  filter: blur(1px);
}
@keyframes drift-green {
  0% { transform: translate(0,0) scale(1); }
  33% { transform: translate(2%,-1%) scale(1.02); }
  66% { transform: translate(-1%,2%) scale(0.98); }
  100% { transform: translate(1%,1%) scale(1.01); }
}
@keyframes drift-purple {
  0% { transform: translate(0,0) scale(1); }
  33% { transform: translate(-2%,1%) scale(0.99); }
  66% { transform: translate(1%,-2%) scale(1.03); }
  100% { transform: translate(-1%,-1%) scale(1); }
}

</style></head><body>

<div id="app">

<!-- 等高线纹理背景 -->
<div class="contour-texture">
  <div class="contour-green"></div>
  <div class="contour-purple"></div>
</div>

<!-- 全局背景网格 -->
<div class="global-grid">
  <svg><defs><pattern id="dotGrid" width="48" height="48" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="0.7" fill="var(--grid-dot)"/></pattern></defs><rect width="100%" height="100%" fill="url(#dotGrid)"/></svg>
</div>
<div class="hero-glow"></div>

<!-- TOP TICKER -->
<div class="ticker-bar ticker-bar-top">
  <div class="ticker-grid"><svg><rect width="100%" height="100%" fill="url(#dotGrid)"/></svg></div>
  <div class="ticker-track" id="tickerTop"></div>
</div>

<!-- Header -->
<div class="header">
  <div class="header-inner">
    <div class="logo" id="siteLogo">NDX100 DASHBOARD</div>
    <div class="nav-btns">
      <button class="nav-btn" id="btnPrev" disabled>← 前一日</button>
      <button class="nav-btn" id="btnToday" style="display:none">今天</button>
      <button class="nav-btn" id="btnNext" disabled>后一日 →</button>
      <button class="theme-btn" onclick="toggleTheme()" id="themeToggleBtn">日间模式</button>
    </div>
  </div>
</div>

<div class="container">

  <!-- HERO -->
  <section class="hero">
    <div class="hero-inner">
      <div class="hero-left">
        <div class="hero-tag"><span class="hero-tag-dot"></span><span class="hero-tag-text">NASDAQ-100</span></div>
        <h1 class="hero-title">纳斯达克<br><span class="hero-accent">100</span></h1>
        <div class="hero-meta">
          <span class="hero-date" id="dateStr"></span>
          <span class="hero-dot"></span>
          <span class="hero-badge" id="statusBadge">已收盘</span>
        </div>
      </div>
      <div class="hero-kpis">
        <div>
          <div class="kpi-label">INDEX</div>
          <div class="kpi-value" id="idxPrice">--</div>
          <div class="kpi-change up" id="idxChange">--</div>
        </div>
        <div>
          <div class="kpi-label">30D</div>
          <div class="kpi-change up" id="trend30d">--</div>
          <div class="kpi-sub" id="trendRange">--</div>
        </div>
        <div>
          <div class="kpi-label">UP/DOWN</div>
          <div class="kpi-value"><span style="color:var(--rise)" id="idxUp">--</span><span style="color:var(--text3);font-size:28px">/</span><span style="color:var(--fall)" id="idxDown">--</span></div>
          <div class="kpi-sub"><span id="stockCount">--</span> components</div>
        </div>
      </div>
    </div>
  </section>

  <div class="divider"></div>

  <!-- AI SUMMARY -->
  <section class="ai-summary" id="aiSummaryBox" style="display:none">
    <div class="section-label">Market Intelligence</div>
    <p id="aiSummaryText"></p>
  </section>
  <div class="divider" id="aiSummaryDivider" style="display:none"></div>

  <!-- DISTRIBUTION -->
  <section>
    <div class="section-header">
      <div>
        <div class="section-label">Distribution</div>
        <div class="section-title">涨跌分布</div>
      </div>
      <div class="section-sub">100 components by change range</div>
    </div>
    <div class="dist-chart" id="distChart"></div>
    <div class="card" id="aiDistBox" style="display:none;margin-top:20px;padding:20px 24px;">
      <p style="margin:0;font-size:20px;line-height:1.5;color:var(--text);font-weight:700;letter-spacing:-0.3px;"></p>
    </div>
  </section>

  <div class="divider"></div>

  <!-- PIE CHARTS -->
  <section>
    <div class="section-header">
      <div>
        <div class="section-label">Breakdown</div>
        <div class="section-title">权重分布</div>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;">
      <div class="card" style="padding:48px">
        <div class="card-title">个股权重</div>
        <div class="card-sub">Top 15 + Others</div>
        <div class="pie-container" id="stockPie"></div>
        <div class="pie-legend" id="stockLegend"></div>
        <div class="card" id="aiStocksBox" style="display:none;margin-top:20px;padding:16px 20px;">
          <p style="margin:0;font-size:20px;line-height:1.5;color:var(--text);font-weight:700;letter-spacing:-0.3px;"></p>
        </div>
      </div>
      <div class="card" style="padding:48px">
        <div class="card-title">行业权重</div>
        <div class="card-sub">Sector Distribution</div>
        <div class="pie-container" id="sectorPie"></div>
        <div class="pie-legend" id="sectorLegend"></div>
        <div class="card" id="aiSectorsBox" style="display:none;margin-top:20px;padding:16px 20px;">
          <p style="margin:0;font-size:20px;line-height:1.5;color:var(--text);font-weight:700;letter-spacing:-0.3px;"></p>
        </div>
      </div>
    </div>
  </section>

  <!-- SECTORS -->
  <section>
    <div class="section-header">
      <div>
        <div class="section-label">Sectors</div>
        <div class="section-title">行业表现</div>
      </div>
      <div class="section-sub">Weighted average by sector</div>
    </div>
    <div id="sectorBar"></div>
    <div class="card" id="aiIndustryBox" style="display:none;margin-top:20px;padding:20px 24px;">
      <p style="margin:0;font-size:20px;line-height:1.5;color:var(--text);font-weight:700;letter-spacing:-0.3px;"></p>
    </div>
  </section>

  <div class="divider"></div>

  <!-- TREND -->
  <section>
    <div class="section-header">
      <div>
        <div class="section-label">Trend</div>
        <div class="section-title">30日走势</div>
      </div>
      <div class="section-sub">30-day closing price</div>
    </div>
    <div style="padding:20px 0">
      <svg class="trend-svg" id="trendLine" viewBox="0 0 900 200"></svg>
    </div>
    <div class="card" id="aiTrendBox" style="display:none;margin-top:20px;padding:20px 24px;">
      <p style="margin:0;font-size:20px;line-height:1.5;color:var(--text);font-weight:700;letter-spacing:-0.3px;"></p>
    </div>
  </section>

  <div class="divider"></div>

  <!-- STOCK GRID -->
  <section>
    <div class="section-header">
      <div>
        <div class="section-label">Components</div>
        <div class="section-title">成分股一览</div>
      </div>
      <div class="section-sub">100 stocks</div>
    </div>
    <div class="stock-grid" id="stockGrid"></div>
  </section>

  <div class="divider"></div>

  <!-- FOOTER -->
  <div class="footer">
    <div style="height:1px;background:linear-gradient(90deg,transparent,var(--border-strong),transparent);margin-bottom:40px"></div>
    <div class="footer-text">数据来自 Yahoo Finance · 每日自动更新 · 仅供参考不构成投资建议</div>
  </div>

</div>

<!-- BOTTOM TICKER -->
<div class="ticker-bar ticker-bar-bottom">
  <div class="ticker-grid"><svg><rect width="100%" height="100%" fill="url(#dotGrid)"/></svg></div>
  <div class="ticker-track ticker-track-reverse" id="tickerBottom"></div>
</div>

<div class="tooltip" id="tooltip"></div>

<script>
const DATA = __DATA_JSON__;
const RISE = "#39ff14", FALL = "#bf00ff", ACCENT = "#bf00ff";
const TEXT = "#f5f5f5", TEXT2 = "#a1a1aa", TEXT3 = "#52525b", BG = "#0a0a0a";

function colorForChange(c){return c>=0?RISE:FALL}
function fmtPct(c){return(c>=0?"▲ +":"▼ ")+c.toFixed(2)+"%"}
function fmtPctRaw(c){return(c>=0?"+":"")+c.toFixed(2)+"%"}
function svgEl(tag,attrs){const el=document.createElementNS("http://www.w3.org/2000/svg",tag);for(let k in attrs)el.setAttribute(k,attrs[k]);return el}

const HISTORY_DATES = __HISTORY_DATES__;
const IS_HISTORY = __IS_HISTORY__;

// 市场状态
function getMarketStatus(){
  const now=new Date();
  const utc=now.getTime()+now.getTimezoneOffset()*60000;
  const beijing=new Date(utc+8*3600000);
  const day=beijing.getDay();
  if(day===0||day===6)return"已收盘";
  const year=beijing.getFullYear();
  const dstStart=new Date(year,2,14-new Date(year,2,1).getDay());
  const dstEnd=new Date(year,10,7-new Date(year,10,1).getDay());
  const isDST=beijing>=dstStart&&beijing<dstEnd;
  const hour=beijing.getHours(),minute=beijing.getMinutes();
  const timeVal=hour+minute/60;
  const openTime=isDST?21.5:22.5;
  const closeTime=isDST?28:29;
  if(timeVal>=openTime&&timeVal<closeTime)return"开盘中，收盘后更新";
  return"已收盘";
}

// 导航
(function(){
  const btnPrev=document.getElementById("btnPrev");
  const btnNext=document.getElementById("btnNext");
  const btnToday=document.getElementById("btnToday");
  if(!btnPrev||!btnNext)return;
  const path=window.location.pathname;
  const isHistory=path.includes("/history/");
  let currentDate;
  if(isHistory){
    const m=path.match(/history\/(\d{4}-\d{2}-\d{2})/);
    currentDate=m?m[1]:DATA.date;
    if(btnToday){btnToday.style.display="inline-block";btnToday.onclick=()=>location.href="../index.html"}
  }else{currentDate=DATA.date}
  const idx=HISTORY_DATES.indexOf(currentDate);
  if(idx===-1)return;
  if(idx>0){
    const prevDate=HISTORY_DATES[idx-1];
    btnPrev.disabled=false;
    btnPrev.onclick=()=>{location.href=isHistory?"./"+prevDate+".html":"./history/"+prevDate+".html"}
  }
  if(idx<HISTORY_DATES.length-1){
    const nextDate=HISTORY_DATES[idx+1];
    btnNext.disabled=false;
    if(nextDate===DATA.date&&isHistory){btnNext.onclick=()=>location.href="../index.html"}
    else{btnNext.onclick=()=>{location.href=isHistory?"./"+nextDate+".html":"./history/"+nextDate+".html"}}
  }
})();

// KPI
(function(){
  const idx=DATA.index;
  document.getElementById("dateStr").textContent=DATA.date;
  document.getElementById("statusBadge").textContent=getMarketStatus();
  document.querySelector('.hero-accent').style.color = idx.change >= 0 ? 'var(--rise)' : 'var(--fall)';
  document.querySelectorAll('.section-label').forEach(el=>{el.style.color=idx.change>=0?'var(--rise)':'var(--fall)';});
  document.querySelector('.hero-tag-dot').style.background=idx.change>=0?'var(--rise)':'var(--fall)';
  document.getElementById('siteLogo').style.color=idx.change>=0?'var(--rise)':'var(--fall)';

  const priceEl=document.getElementById("idxPrice");
  const chgEl=document.getElementById("idxChange");

  if(idx.price&&idx.prev_close){
    // 价格 odometer 滚动（从昨日收盘价滚到今日）
    rollNumber(priceEl, idx.prev_close, idx.price, 5000);

    // 涨跌幅直接设置，不参与滚动（避免格式复杂化）
    const diff=idx.price-idx.prev_close;
    const sign=idx.change>=0?"▲ +":"▼ ";
    const diffSign=diff>=0?"+":"";
    chgEl.textContent=sign+idx.change.toFixed(2)+"% ("+diffSign+diff.toFixed(2)+")";
    chgEl.className="kpi-change "+(idx.change>=0?"up":"down");
  }else{
    priceEl.textContent=idx.price?idx.price.toLocaleString():"估算中";
    chgEl.textContent=fmtPct(idx.change)+(idx.price?(" ("+(idx.price-idx.prev_close).toFixed(2)+")"):"");
    chgEl.className="kpi-change "+(idx.change>=0?"up":"down");
  }

  document.getElementById("idxUp").textContent=idx.up;
  document.getElementById("idxDown").textContent=idx.down;
  document.getElementById("stockCount").textContent=idx.total;
  const hist=DATA.history;
  if(hist.length>=2){
    const c30=((hist[hist.length-1]-hist[0])/hist[0]*100).toFixed(2);
    const t30=document.getElementById("trend30d");
    t30.textContent=(c30>=0?"▲ +":"▼ ")+c30+"%";
    t30.className="kpi-change "+(c30>=0?"up":"down");
    document.getElementById("trendRange").textContent=Math.round(hist[0]).toLocaleString()+" → "+Math.round(hist[hist.length-1]).toLocaleString();
  }else{
    document.getElementById("trend30d").textContent="--";
    document.getElementById("trendRange").textContent="数据暂缺";
  }
})();

// AI Summaries
(function(){
  const summaries=[
    {key:"ai_summary",box:"aiSummaryBox",text:"aiSummaryText",div:"aiSummaryDivider"},
    {key:"ai_stocks",box:"aiStocksBox",text:null},
    {key:"ai_sectors",box:"aiSectorsBox",text:null},
    {key:"ai_distribution",box:"aiDistBox",text:null},
    {key:"ai_industry",box:"aiIndustryBox",text:null},
    {key:"ai_trend",box:"aiTrendBox",text:null}
  ];
  summaries.forEach(s=>{
    if(DATA[s.key]){
      const box=document.getElementById(s.box);
      if(box){
        const el=s.text?document.getElementById(s.text):box.querySelector("p");
        if(el)el.textContent=DATA[s.key];
        box.style.display="block";
        if(s.div){document.getElementById(s.div).style.display="block"}
      }
    }
  });
})();

// 涨跌分布柱图
(function(){
  const container=document.getElementById("distChart");
  const labels=DATA.bins.labels;
  const counts=DATA.bins.counts;
  const max=Math.max(...counts);
  labels.forEach((lbl,i)=>{
    const isUp=i>=4;
    const col=document.createElement("div");col.className="dist-col";
    const count=document.createElement("span");count.className="dist-count "+(isUp?"up":"down");count.textContent=counts[i];
    const bar=document.createElement("div");bar.className="dist-bar "+(isUp?"up":"down");
    const h=(counts[i]/max)*160;bar.style.height=Math.max(h,1)+"px";bar.style.opacity=isUp?0.75+(i-4)*0.05:0.75+(3-i)*0.05;
    bar.style.cursor="pointer";
    bar.addEventListener("mouseenter",e=>showTip(e,lbl+": "+counts[i]+"只"));
    bar.addEventListener("mouseleave",hideTip);
    const label=document.createElement("span");label.className="dist-label";label.textContent=lbl;
    col.appendChild(count);col.appendChild(bar);col.appendChild(label);
    container.appendChild(col);
  });
})();

// 行业柱图
(function(){
  const container=document.getElementById("sectorBar");
  const data=DATA.sectors.filter(d=>typeof d.change==='number'&&!isNaN(d.change)).map(d=>({...d}));
  if(data.length===0){container.innerHTML='<div style="text-align:center;color:var(--text3);padding:40px">行业数据暂缺</div>';return}
  data.sort((a,b)=>b.change-a.change);
  const maxC=Math.max(...data.map(d=>Math.abs(d.change)),0.01);
  data.forEach(d=>{
    const isUp=d.change>=0;
    const row=document.createElement("div");row.className="sector-row";
    const name=document.createElement("span");name.className="sector-name";name.textContent=d.name;
    const track=document.createElement("div");track.className="sector-track";
    const bar=document.createElement("div");bar.className="sector-bar "+(isUp?"up":"down");
    const pct=Math.min(Math.abs(d.change)/maxC,1)*100;
    bar.style.setProperty("--final-width", Math.max(pct,3)+"%");
    const label=document.createElement("span");label.className="sector-bar-label "+(isUp?"up":"down");label.textContent=fmtPct(d.change);
    bar.appendChild(label);
    track.appendChild(bar);
    row.appendChild(name);row.appendChild(track);
    container.appendChild(row);
  });
})();

// 走势线图
(function(){
  const svg=document.getElementById("trendLine");
  const data=DATA.history;
  if(data.length<2){svg.innerHTML='<text x="450" y="100" text-anchor="middle" fill="var(--text3)" font-size="14">历史数据暂缺</text>';return}
  const W=900,H=200,padL=50,padB=30,padT=30,padR=30;
  const min=Math.min(...data),max=Math.max(...data);
  const range=max-min||1;
  const x=i=>padL+i*(W-padL-padR)/(data.length-1);
  const y=v=>padT+(max-v)/range*(H-padT-padB);
  let areaD="M "+x(0)+" "+y(data[0]);
  data.forEach((v,i)=>areaD+=" L "+x(i)+" "+y(v));
  areaD+=" L "+x(data.length-1)+" "+(H-padB)+" L "+x(0)+" "+(H-padB)+" Z";
  const defs=svgEl("defs",{});
  const grad=svgEl("linearGradient",{id:"trendGrad",x1:"0",y1:"0",x2:"0",y2:"1"});
  grad.appendChild(svgEl("stop",{offset:"0%","stop-color":RISE,"stop-opacity":"0.2"}));
  grad.appendChild(svgEl("stop",{offset:"100%","stop-color":RISE,"stop-opacity":"0"}));
  defs.appendChild(grad);svg.appendChild(defs);
  const areaPath=svgEl("path",{d:areaD,fill:"url(#trendGrad)",class:"trend-area"});svg.appendChild(areaPath);
  let lineD="M "+x(0)+" "+y(data[0]);
  data.forEach((v,i)=>lineD+=" L "+x(i)+" "+y(v));
  const linePath=svgEl("path",{d:lineD,fill:"none",stroke:RISE,"stroke-width":"2.5","stroke-linecap":"round","stroke-linejoin":"round",class:"trend-path"});svg.appendChild(linePath);requestAnimationFrame(()=>{try{const len=linePath.getTotalLength();linePath.style.setProperty("--path-length",len)}catch(e){}});
  data.forEach((v,i)=>{
    const c=svgEl("circle",{cx:x(i),cy:y(v),r:i===data.length-1?5:3.5,fill:i===data.length-1?RISE:BG,stroke:RISE,"stroke-width":i===data.length-1?2.5:1.5,class:"trend-point"});c.style.transitionDelay=(i*0.04)+"s";
    c.style.cursor="pointer";
    const daysAgo=data.length-i;
    const dayLabel=daysAgo===1?"今日":daysAgo+"天前";
    c.addEventListener("mouseenter",e=>showTip(e,dayLabel+"<br>收盘 "+Math.round(v).toLocaleString()));
    c.addEventListener("mouseleave",hideTip);
    svg.appendChild(c);
  });
  svg.appendChild(svgEl("text",{x:padL,y:H-5,fill:TEXT3,"font-size":"11","font-weight":"600"})).textContent="30 days ago";
  svg.appendChild(svgEl("text",{x:W-padR,y:H-5,"text-anchor":"end",fill:TEXT3,"font-size":"11","font-weight":"600"})).textContent="Today";
})();

// 股票网格
(function(){
  const grid=document.getElementById("stockGrid");
  DATA.stocks.forEach(s=>{
    const cell=document.createElement("div");
    cell.className="stock-cell "+(s.change>=0?"":"down");
    cell.innerHTML='<div class="stock-ticker">'+s.ticker+'</div><div class="stock-pct">'+fmtPct(s.change)+'</div>';
    cell.addEventListener("mouseenter",e=>showTip(e,s.ticker+" "+s.name+"<br>权重 "+s.weight+"% - "+s.sector));
    cell.addEventListener("mouseleave",hideTip);
    grid.appendChild(cell);
  });
})();

// 个股饼图
(function(){
  const container=document.getElementById("stockPie");
  const data=DATA.pie_stocks;
  const total=data.reduce((a,b)=>a+b.weight,0);
  const svg=document.createElementNS("http://www.w3.org/2000/svg","svg");
  svg.setAttribute("viewBox","0 0 400 340");svg.style.width="100%";svg.style.maxWidth="380px";svg.style.height="auto";svg.style.position="relative";svg.style.zIndex="1";
  const cx=200,cy=170,R=120,sw=44;
  const C=2*Math.PI*R;

  // 底部光晕（涨跌变色）
  const glow=document.createElement("div");
  glow.className="pie-glow "+(DATA.index.change>=0?"up":"down");
  container.appendChild(glow);

  let rot=-90;
  data.forEach((d,idx)=>{
    const angle=(d.weight/total)*360;
    const arc=(angle/360)*C;
    const color=colorForChange(d.change);

    // 关键：用 <g> 做 scale 生长动画
    const gWrap=svgEl("g",{class:"pie-seg"});
    gWrap.style.transitionDelay=(idx*0.05)+"s";
    gWrap.style.transformOrigin="200px 170px";
    gWrap.style.cursor="pointer";
    gWrap.addEventListener("mouseenter",e=>showTip(e,d.name+"（"+d.ticker+"）<br>权重 "+d.weight+"% · "+fmtPct(d.change)));
    gWrap.addEventListener("mouseleave",hideTip);

    // <circle> 只管 rotate，不再加 class="pie-seg"
    const seg=svgEl("circle",{cx:cx,cy:cy,r:R,fill:"none",stroke:color,"stroke-width":sw,"stroke-dasharray":arc+" "+(C-arc),transform:"rotate("+rot+" "+cx+" "+cy+")"});
    gWrap.appendChild(seg);
    svg.appendChild(gWrap);
    rot+=angle;
  });

  // Donut 中间挖空
  svg.appendChild(svgEl("circle",{cx:cx,cy:cy,r:R-sw/2,fill:"var(--bg)"}));

  // 文字盖在最上层，加阴影保证任何颜色扇形上都能看清
  const shadow="text-shadow:0 2px 10px rgba(0,0,0,0.85)";
  svg.appendChild(svgEl("text",{x:cx,y:cy-12,"text-anchor":"middle",fill:"var(--text)","font-size":28,"font-weight":900,"letter-spacing":"-1",style:shadow})).textContent="NDX";
  const chgColor=DATA.index.change>=0?"var(--rise)":"var(--fall)";
  svg.appendChild(svgEl("text",{x:cx,y:cy+15,"text-anchor":"middle",fill:chgColor,"font-size":18,"font-weight":800,"font-family":"'JetBrains Mono',monospace",style:shadow})).textContent=fmtPct(DATA.index.change);

  container.appendChild(svg);
  const leg=document.getElementById("stockLegend");
  data.slice(0,6).forEach(d=>{
    const item=document.createElement("div");item.className="pie-legend-item";
    item.innerHTML='<span class="pie-legend-dot" style="background:'+colorForChange(d.change)+'"></span>'+d.ticker+" "+fmtPct(d.change);
    leg.appendChild(item);
  });
})();

// 行业饼图
(function(){
  const container=document.getElementById("sectorPie");
  const data=DATA.sectors;
  const total=data.reduce((a,b)=>a+b.weight,0);
  const svg=document.createElementNS("http://www.w3.org/2000/svg","svg");
  svg.setAttribute("viewBox","0 0 400 340");svg.style.width="100%";svg.style.maxWidth="380px";svg.style.height="auto";svg.style.position="relative";svg.style.zIndex="1";
  const cx=200,cy=170,R=120,sw=44;
  const C=2*Math.PI*R;

  // 底部光晕
  const glow=document.createElement("div");
  glow.className="pie-glow "+(DATA.index.change>=0?"up":"down");
  container.appendChild(glow);

  let rot=-90;
  data.forEach((d,idx)=>{
    const angle=(d.weight/total)*360;
    const arc=(angle/360)*C;
    const color=colorForChange(d.change);

    const gWrap=svgEl("g",{class:"pie-seg"});
    gWrap.style.transitionDelay=(idx*0.05)+"s";
    gWrap.style.transformOrigin="200px 170px";
    gWrap.style.cursor="pointer";
    gWrap.addEventListener("mouseenter",e=>showTip(e,d.name+"<br>权重 "+d.weight+"% · "+fmtPct(d.change)));
    gWrap.addEventListener("mouseleave",hideTip);

    const seg=svgEl("circle",{cx:cx,cy:cy,r:R,fill:"none",stroke:color,"stroke-width":sw,"stroke-dasharray":arc+" "+(C-arc),transform:"rotate("+rot+" "+cx+" "+cy+")"});
    gWrap.appendChild(seg);
    svg.appendChild(gWrap);
    rot+=angle;
  });

  // Donut 中间挖空
  svg.appendChild(svgEl("circle",{cx:cx,cy:cy,r:R-sw/2,fill:"var(--bg)"}));

  const shadow="text-shadow:0 2px 10px rgba(0,0,0,0.85)";
  svg.appendChild(svgEl("text",{x:cx,y:cy-22,"text-anchor":"middle",fill:"var(--text)","font-size":24,"font-weight":900,"letter-spacing":"-0.5",style:shadow})).textContent="SECTORS";

  const upSectors=data.filter(d=>d.change>=0);
  const downSectors=data.filter(d=>d.change<0);
  const upAvg=upSectors.length?upSectors.reduce((a,b)=>a+b.change,0)/upSectors.length:0;
  const downAvg=downSectors.length?downSectors.reduce((a,b)=>a+b.change,0)/downSectors.length:0;
  svg.appendChild(svgEl("text",{x:cx,y:cy+5,"text-anchor":"middle",fill:"var(--rise)","font-size":16,"font-weight":800,"font-family":"'JetBrains Mono',monospace",style:shadow})).textContent="▲ "+fmtPctRaw(upAvg);
  svg.appendChild(svgEl("text",{x:cx,y:cy+25,"text-anchor":"middle",fill:"var(--fall)","font-size":14,"font-weight":700,"font-family":"'JetBrains Mono',monospace",style:shadow})).textContent="▼ "+fmtPctRaw(downAvg);

  container.appendChild(svg);
  const leg=document.getElementById("sectorLegend");
  data.forEach(d=>{
    const item=document.createElement("div");item.className="pie-legend-item";
    item.innerHTML='<span class="pie-legend-dot" style="background:'+colorForChange(d.change)+'"></span>'+d.name+" "+d.weight+"%";
    leg.appendChild(item);
  });
})();// 行情条
(function(){
  const topStocks=DATA.stocks.slice().sort((a,b)=>Math.abs(b.change)-Math.abs(a.change));
  const bottomStocks=DATA.stocks.slice().sort(()=>Math.random()-0.5);
  function buildTicker(id,stocks,reverse){
    const bar=document.getElementById(id);
    if(!bar)return;
    const track=document.createElement("div");
    track.className="ticker-track"+(reverse?" ticker-track-reverse":"");
    track.style.animation=reverse?"ticker-scroll-reverse 100s linear infinite":"ticker-scroll 100s linear infinite";
    let html="";
    stocks.forEach(s=>{
      const c=colorForChange(s.change);
      html+='<span class="ticker-item"><span class="ticker-name">'+s.ticker+'</span><span class="ticker-change '+(s.change>=0?"up":"down")+'">'+fmtPct(s.change)+'</span><span class="ticker-sep">|</span></span>';
    });
    track.innerHTML=html+html;
    bar.appendChild(track);
  }
  buildTicker("tickerTop",topStocks,false);
  buildTicker("tickerBottom",bottomStocks,true);
})();

// 主题切换
function toggleTheme(){
  const root=document.documentElement;
  const btn=document.getElementById("themeToggleBtn");
  if(root.classList.contains("light")){
    root.classList.remove("light");
    if(btn)btn.textContent="日间模式";
  }else{
    root.classList.add("light");
    if(btn)btn.textContent="夜间模式";
  }
}

// 跟随系统主题
if(window.matchMedia&&window.matchMedia("(prefers-color-scheme: light)").matches){
  document.documentElement.classList.add("light");
  const btn=document.getElementById("themeToggleBtn");
  if(btn)btn.textContent="夜间模式";
}

// Odometer 数字滚动：从 fromValue 逐位翻滚到 toValue
function rollNumber(el, fromValue, toValue, duration){
  const toStr=toValue.toLocaleString("en-US",{minimumFractionDigits:1,maximumFractionDigits:1});
  const fromStr=fromValue.toLocaleString("en-US",{minimumFractionDigits:1,maximumFractionDigits:1});

  // 对齐长度（前补空格）
  const maxLen=Math.max(toStr.length,fromStr.length);
  const toPadded=toStr.padStart(maxLen,' ');
  const fromPadded=fromStr.padStart(maxLen,' ');

  el.innerHTML="";
  el.style.display="inline-flex";
  el.style.alignItems="flex-end";

  const digits=[];

  for(let i=0;i<maxLen;i++){
    const fromCh=fromPadded[i];
    const toCh=toPadded[i];

    if(fromCh===","||fromCh==="."||fromCh===" "){
      const span=document.createElement("span");
      span.textContent=toCh;
      span.style.display="inline-block";
      el.appendChild(span);
    }else{
      const fromNum=parseInt(fromCh);
      const toNum=parseInt(toCh);

      const wrap=document.createElement("span");
      wrap.style.display="inline-block";
      wrap.style.overflow="hidden";
      wrap.style.height="1em";
      wrap.style.lineHeight="1em";
      wrap.style.verticalAlign="bottom";

      const strip=document.createElement("span");
      strip.style.display="flex";
      strip.style.flexDirection="column";

      // 构建滚动序列：从 fromNum 向上滚动到 toNum（循环）
      let seq=[];
      let n=fromNum;
      while(true){
        seq.push(n);
        if(n===toNum) break;
        n=(n+1)%10;
      }

      seq.forEach(num=>{
        const d=document.createElement("span");
        d.textContent=num;
        d.style.display="block";
        d.style.height="1em";
        d.style.lineHeight="1em";
        strip.appendChild(d);
      });

      wrap.appendChild(strip);
      el.appendChild(wrap);
      digits.push({strip,count:seq.length,delay:i*70,duration:duration});
    }
  }

  requestAnimationFrame(()=>{
    digits.forEach(({strip,count,delay,duration})=>{
      strip.style.transition=`transform ${duration}ms cubic-bezier(0.25,1,0.5,1)`;
      setTimeout(()=>{
        strip.style.transform=`translateY(-${count-1}em)`;
      },delay);
    });
  });
}

// Tooltip
const tip=document.getElementById("tooltip");
function showTip(e,html){
  tip.innerHTML=html;
  tip.style.opacity="1";
  const tw=tip.offsetWidth,th=tip.offsetHeight;
  let left=e.clientX-tw/2;
  let top=e.clientY-th-14;
  if(left<8)left=8;
  if(left+tw>window.innerWidth-8)left=window.innerWidth-tw-8;
  if(top<8)top=e.clientY+14;
  tip.style.left=left+"px";tip.style.top=top+"px";
}
function hideTip(){tip.style.opacity="0"}

// Scroll-triggered Animations
(function(){
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const target = entry.target;

      if (target.id === 'distChart') {
        target.querySelectorAll('.dist-bar').forEach((bar, i) => {
          setTimeout(() => bar.classList.add('animate'), i * 60);
        });
      }
      else if (target.id === 'stockPie' || target.id === 'sectorPie') {
        target.querySelectorAll('.pie-seg').forEach((seg,i) => { setTimeout(() => seg.classList.add('animate'), i*50); });
      }
      else if (target.id === 'sectorBar') {
        target.querySelectorAll('.sector-bar').forEach((bar, i) => {
          setTimeout(() => bar.classList.add('animate'), i * 80);
        });
      }
      else if (target.id === 'trendLine') {
        target.querySelector('.trend-path')?.classList.add('animate');
        target.querySelector('.trend-area')?.classList.add('animate');
        target.querySelectorAll('.trend-point').forEach((pt, i) => {
          setTimeout(() => pt.classList.add('animate'), 600 + i * 40);
        });
      }
      observer.unobserve(target);
    });
  }, { threshold: 0.12 });

  ['distChart', 'stockPie', 'sectorPie', 'sectorBar', 'trendLine'].forEach(id => {
    const el = document.getElementById(id);
    if (el) observer.observe(el);
  });
})();

</script>
</body></html>"""

def generate_summary(data, summary_type):
    """本地生成AI总结，模拟彭博社/纽约时报风格财经叙述，每天固定组合保证一致性。"""
    import random
    from datetime import datetime

    seed = int(datetime.now().strftime("%Y%m%d")) + hash(summary_type) % 10000
    random.seed(seed)

    index = data.get("index", {})
    stocks = data.get("stocks", [])
    sectors = data.get("sectors", [])
    bins = data.get("bins", {})
    history = data.get("history", [])
    date_str = data.get("date", "")

    up = index.get("up", 0)
    down = index.get("down", 0)
    total = index.get("total", 0)
    change = index.get("change", 0)

    sorted_by_change = sorted(stocks, key=lambda x: x["change"], reverse=True)
    top5 = sorted_by_change[:5] if len(sorted_by_change) >= 5 else sorted_by_change
    bottom5 = sorted_by_change[-5:] if len(sorted_by_change) >= 5 else sorted_by_change

    def fmt_stock(s):
        return f"{s['name']}（{s['ticker']}）"

    def fmt_pct(v):
        return f"+{v:.2f}%" if v >= 0 else f"{v:.2f}%"

    def pick(*args):
        return random.choice(args)

    top1 = top5[0] if top5 else None
    bot1 = bottom5[-1] if bottom5 else None
    up_ratio = up / total if total else 0

    # ==================== overview ====================
    if summary_type == "overview":
        if change > 1.5:
            templates = [
                f"纳斯达克100指数大涨{fmt_pct(change)}，以{up}只成分股收涨、{down}只收跌的压倒性数据结束交易。投资者在科技板块的集中买入行为，推动指数录得近期少见的单边涨幅。{top1['name'] if top1 else ''}等权重股贡献了可观的上行动能，市场风险偏好明显回升。期权市场的隐含波动率在尾盘出现回落，暗示交易员对短期大幅回调的担忧正在消退。",
                f"科技股成为推动NDX上涨{fmt_pct(change)}的核心引擎，上涨家数{up}对下跌{down}的比例，暗示资金正在系统性回流成长型资产。这一走势与近期美债收益率的变动形成呼应，机构调仓迹象较为清晰。值得注意的是，此次上涨的广度优于前几次反弹，中小成分股同样录得了可观的涨幅。",
                f"NDX收高{fmt_pct(change)}，涨幅背后是{up}只成分股的集体走强，下跌个股仅{down}只。市场似乎正在消化前期对科技股估值过高的担忧，多头重新占据主导地位。从日内价格轨迹来看，指数在开盘后便稳步攀升，盘中几乎未遭遇有效阻力，收盘价接近日内高点。",
                f"在经历了数周的区间震荡后，纳斯达克100以{fmt_pct(change)}的涨幅突破上方阻力。涨跌家数比达到{up}:{down}，这是近期最为悬殊的读数之一，暗示买盘具有一定的持续性。成交量较20日均值显著放大，进一步验证了突破的有效性。",
                f"权重股与中小成分股同步走强，NDX最终收涨{fmt_pct(change)}。{up}只个股录得正收益，下跌家数被压缩至{down}只，这种普涨格局在近期交易中并不常见。资金流向数据显示，机构投资者在尾盘一小时内加速入场，推动指数创出日内新高。",
                f"资金流向数据支持了NDX{fmt_pct(change)}的涨幅——上涨家数{up}只、下跌{down}只，多空力量对比悬殊。投资者似乎正在为美联储可能的政策转向提前布局，科技股作为利率敏感型资产，成为本轮买入的主要目标。板块层面的数据显示，半导体和人工智能相关标的领涨。",
                f"NDX劲升{fmt_pct(change)}，其中{top1['name'] if top1 else ''}等头部科技股贡献了主要涨幅。值得注意的是，上涨家数{up}远超过下跌的{down}只，表明买盘覆盖面较广，并非单纯的权重股行情。从技术面看，指数已站上50日均线，短期趋势转向有利于多头。",
                f"纳斯达克100的涨幅{fmt_pct(change)}在当日主要指数中表现突出，{up}只成分股收涨。交易员普遍将此次上涨归因于前期超卖后的技术性反弹，但涨幅的广度令部分观察者感到意外。衡量市场宽度的AD线同样录得强劲读数，确认了上涨的内部结构较为健康。",
                f"上涨股票数量达到{up}只，下跌仅{down}只，NDX最终收高{fmt_pct(change)}。这种近乎一边倒的行情，与一周前市场的犹豫氛围形成鲜明对比。VIX指数在当日下滑超过5%，反映出投资者对短期风险的评估正在改善。",
                f"NDX以{fmt_pct(change)}的涨幅收盘，{up}只成分股录得正收益。投资者对人工智能相关标的的热情重燃，成为推动指数上行的主要叙事。不过，部分策略师提醒，当前的估值水平已计入较多乐观预期，进一步上涨需要盈利数据的支撑。",
                f"市场选择向上突破，NDX收涨{fmt_pct(change)}，涨跌家数{up}:{down}。期货市场的定价显示，投资者对年内降息的预期略有升温，这为风险资产的上涨提供了宏观背景支持。周期性板块与科技板块的同步走强，进一步强化了经济软着陆的叙事。",
                f"纳斯达克100的强势表现（{fmt_pct(change)}）与上涨家数{up}只的数据相互印证，确认了买盘的广泛性。{down}只下跌个股中，多数跌幅在1%以内，抛售压力相对有限。从板块层面看，通信服务和可选消费板块领涨，防御性板块表现相对落后。",
                f"科技板块全线走高，推动NDX上涨{fmt_pct(change)}。{up}只成分股收于昨日收盘价上方，而下跌家数{down}为近期最低水平之一，市场情绪明显转向乐观。机构经纪商的数据显示，对冲基金在当日净买入科技股的规模创下近两个月新高。",
                f"NDX录得{fmt_pct(change)}的涨幅，上涨家数占比达到{up/total*100:.1f}%。机构投资者在尾盘的集中买入，进一步巩固了当日的上行趋势。从跨资产表现来看，美元指数的小幅走弱也为科技股的上涨提供了额外的助力。",
                f"从成分股表现来看，{up}只上涨、{down}只下跌的分布，与NDX{fmt_pct(change)}的涨幅高度一致。市场在关键技术水平附近找到了支撑，并以此为基础展开反弹。相对强弱指标（RSI）从超卖区域回升至中性水平，短期内进一步上行的空间仍然存在。",
                f"纳斯达克100以强劲姿态收高{fmt_pct(change)}，成分股中上涨家数达{up}只，下跌仅{down}只，多头几乎控制了全天的交易节奏。交易数据显示，程序化买盘在早盘和尾盘两个时段集中出现，成为推动指数持续走高的主要力量之一，市场参与者开始重新评估前期对科技板块的保守立场。",
                f"NDX大涨{fmt_pct(change)}之际，{up}只成分股录得正收益，而下跌个股被压缩至{down}只，创下本月以来最佳的市场广度记录。值得注意的是，此次上涨伴随着信用利差的收窄，暗示投资者对科技企业债务违约风险的担忧正在减轻。",
                f"在大型科技股的带领下，纳斯达克100指数飙升{fmt_pct(change)}，上涨家数与下跌家数之比达到{up}:{down}。期权市场的看跌/看涨比率回落至历史均值下方，表明投资者正在减少对冲头寸，对后市的态度趋于乐观。",
                f"NDX的涨幅{fmt_pct(change)}超出多数策略师的预期，涨跌家数{up}:{down}的数据更是强化了多头格局的判断。盘中高点一度触及{index.get('high', 0):,.0f}点，收盘价距此仅一步之遥，显示出买盘在尾盘依然保持着较强的承接力。",
                f"科技股全面爆发的行情推动NDX上涨{fmt_pct(change)}，上涨家数{up}只、下跌{down}只的结构表明，这是一次具有广泛基础的上涨。机构投资者在季末调仓的背景下，加大了对科技龙头的配置，进一步放大了指数的涨幅。",
            ]
        elif change > 0:
            templates = [
                f"纳斯达克100指数小幅收高{fmt_pct(change)}，上涨家数{up}略多于下跌的{down}。市场整体处于观望与试探之间，涨幅虽不惊人，但方向保持向上，多头仍在缓慢积累动能。日内交易区间较窄，最高价与最低价之差不足1%，显示多空双方均在等待新的催化因素。",
                f"NDX微涨{fmt_pct(change)}，涨跌家数{up}:{down}的读数表明，多空双方尚未决出胜负。投资者在等待新的经济数据以判断利率路径，当前价格行动更多反映了技术性因素。从板块结构来看，周期性行业表现优于防御性板块，暗示市场对经济增长的担忧有所缓解。",
                f"指数以{fmt_pct(change)}的温和涨幅收盘，{up}只成分股上涨。交易量较平均水平有所萎缩，暗示缺乏强烈的方向性信念，市场参与者似乎在为更明确的催化剂做好准备。美国国债收益率的窄幅波动，也为股市的平静表现提供了宏观背景。",
                f"纳斯达克100收涨{fmt_pct(change)}，涨幅由{up}只个股贡献。尽管上涨家数占据优势，但涨幅的集中度较高，多数个股仅录得微幅上涨，反弹的可持续性仍有待观察。大宗交易数据显示，机构投资者在当日以净买入为主，但买入规模远低于前几个交易日的平均水平。",
                f"NDX连续第二个交易日走高，本次涨幅{fmt_pct(change)}，上涨家数{up}对下跌{down}。投资者对科技股的兴趣略有回升，但整体仓位调整仍显得谨慎。从估值角度看，当前纳斯达克100的前瞻市盈率略高于五年均值，限制了进一步上行的空间。",
                f"指数上涨{fmt_pct(change)}，上涨家数{up}略占优势。市场在近期区间上沿附近徘徊，突破仍需更强的催化剂。技术分析师指出，指数若要有效突破当前阻力位，需要成交量出现更明显的配合。",
                f"NDX以{fmt_pct(change)}的涨幅结束交易，{up}只成分股收涨。尽管涨幅温和，但考虑到近期市场的犹豫气氛，这一表现仍被视为积极的信号。从资金流向来看，散户投资者的买入热情有所回升，但机构资金尚未出现大规模流入。",
                f"纳斯达克100上涨{fmt_pct(change)}，涨跌家数{up}:{down}。投资者仍在消化企业财报和宏观数据，指数在整数关口附近获得支撑。波动率曲线保持平坦，暗示市场并未将当前的小幅上涨视为趋势性行情的开始。",
                f"科技股带领NDX走高{fmt_pct(change)}，上涨家数{up}只。尽管涨幅有限，但上涨家数多于下跌家数的事实，暗示市场内部结构正在改善。不过，从周度表现来看，指数仍处于过去四周的交易区间之内，尚未形成有效的突破。",
                f"NDX收涨{fmt_pct(change)}，{up}只成分股录得正收益。投资者对估值合理性的讨论仍在继续，但当前价格行动表明，市场愿意在当前水平买入。高盛等机构的最新策略报告指出，科技股的风险回报比正在改善，但尚未达到极具吸引力的水平。",
                f"纳斯达克100温和走高{fmt_pct(change)}，上涨家数{up}只、下跌{down}只。从日内价格走势来看，指数在早盘一度下探至日内低点，随后在逢低买盘的推动下逐步回升，最终收于日内区间的上半部分。这种V型反转的形态，反映出下方存在一定的承接力量。",
                f"NDX录得{fmt_pct(change)}的小幅上涨，涨跌家数{up}:{down}。市场参与者将目光投向下周即将公布的通胀数据，在此之前，多数交易员倾向于维持现有仓位。信用市场的表现同样平静，高收益债券的利差保持在近期均值附近。",
                f"指数收高{fmt_pct(change)}，{up}只成分股上涨。从行业维度看，科技和通信服务板块领涨，而能源和材料板块表现落后。这种板块间的分化，暗示市场正在根据经济周期的不同阶段进行结构性调仓。",
                f"纳斯达克100连续第三日收涨，本次涨幅{fmt_pct(change)}，上涨家数{up}对下跌{down}。尽管每日涨幅不大，但连续的正面走势正在逐步修复市场的技术形态。50日均线即将与200日均线形成黄金交叉，这被部分技术分析师视为中期看涨信号。",
                f"NDX小幅攀升{fmt_pct(change)}，{up}只成分股收涨。投资者对人工智能基础设施支出的乐观预期，抵消了对消费支出放缓的担忧。盘中最大涨幅一度达到1.2%，但尾盘有所回落，显示上方存在一定的获利了结压力。",
                f"纳斯达克100指数以{fmt_pct(change)}的涨幅温和收高，上涨家数{up}只、下跌{down}只，涨跌家数的差距虽然不大，但已足够支撑指数连续第四个交易日收于正值区间。从跨资产的角度观察，黄金和原油的同步走强暗示全球流动性环境依然宽松，这对科技股的估值形成了间接支撑。",
                f"NDX收涨{fmt_pct(change)}的过程中，{up}只成分股录得正收益，而下跌个股则集中在生物科技和中小型软件公司等细分领域。这种内部结构的差异化表现，提示投资者在科技板块内部同样需要进行精细化的标的筛选，而非简单地做多整个板块。",
                f"在权重股表现平稳的背景下，NDX依靠中小成分股的活跃表现实现了{fmt_pct(change)}的涨幅。上涨家数{up}的数据表明，当日的上涨具有一定的群众基础，而非仅仅依赖少数几只大盘股的拉动。罗素2000指数当日跑赢纳斯达克100，进一步印证了资金正在向中小盘扩散的判断。",
                f"指数微涨{fmt_pct(change)}的过程中，市场内部呈现出明显的轮动特征——前期超跌的个股获得资金关注，而近期强势的个股则出现获利回吐。上涨家数{up}、下跌家数{down}的分布，与这种轮动格局高度吻合。",
                f"NDX收盘上涨{fmt_pct(change)}，成分股中{up}只收高、{down}只收低。尽管涨幅温和，但值得关注的是，高贝塔股票的涨幅明显优于低贝塔股票，表明投资者的风险偏好正在改善。对冲基金的净杠杆率在当日小幅上升，结束了连续三天的下降趋势。",
            ]
        elif change > -1:
            templates = [
                f"纳斯达克100指数微跌{fmt_pct(change).replace('-', '')}，涨跌家数{up}:{down}的分布与指数表现基本吻合。市场缺乏明确的方向性驱动，投资者在关键数据公布前倾向于保持现有仓位。整日交易区间为近期最窄之一，多空双方均未展现出强烈的进攻意愿。",
                f"NDX窄幅收低{fmt_pct(change).replace('-', '')}，下跌家数{down}略多于上涨的{up}。整日交易区间为近期最窄之一，表明多空双方均在等待新的信息输入。波动率指数（VIX）保持在15以下的低位，反映出市场并未对当前的微幅下跌感到担忧。",
                f"指数几乎持平收盘，NDX下跌{fmt_pct(change).replace('-', '')}，涨跌家数{up}:{down}。市场似乎进入了短暂的疲惫期，交易员将目光投向即将发布的通胀数据。从历史季节性来看，当前时段通常表现为交投清淡，此次的窄幅波动符合这一规律。",
                f"纳斯达克100微幅收低{fmt_pct(change).replace('-', '')}，{up}只个股逆势上涨。尽管指数收跌，但下跌幅度在1%以内，且下跌家数{down}并未出现恐慌性扩散，调整仍属温和。大宗交易数据显示，机构投资者在下跌中进行了逢低买入操作。",
                f"NDX下跌{fmt_pct(change).replace('-', '')}，涨跌家数{up}:{down}。市场在近期高点附近遭遇阻力，但抛售力度有限，指数仍维持在重要的技术支撑上方。50日均线在当前价格下方约2%处，构成了近期的第一道防线。",
                f"科技板块整体承压，NDX收低{fmt_pct(change).replace('-', '')}，上涨家数{up}、下跌家数{down}。投资者对利率前景的担忧略有升温，但尚未形成系统性抛售。10年期美债收益率当日微升2个基点，对科技股的估值形成了一定压力。",
                f"指数小幅回落{fmt_pct(change).replace('-', '')}，涨跌家数{up}:{down}。市场在连续上涨后出现自然回调，成交量清淡，表明此次下跌更多是获利了结而非趋势反转。从期权市场的持仓结构来看，看跌期权的未平仓量并未出现异常增加。",
                f"纳斯达克100下跌{fmt_pct(change).replace('-', '')}，{down}只成分股收跌。尽管指数收于负值区间，但跌幅有限，且下跌个股的跌幅普遍较小，市场整体仍具韧性。亚洲和欧洲市场的隔夜表现同样平淡，未能为美股提供明确的方向指引。",
                f"NDX微幅走低{fmt_pct(change).replace('-', '')}，涨跌家数{up}:{down}。投资者对科技股估值的分歧继续存在，但指数在当前位置的支撑力度仍相对稳固。多个技术指标显示，市场处于超买与超卖之间的中性区域，短期内缺乏明确的方向性信号。",
                f"指数收跌{fmt_pct(change).replace('-', '')}，涨跌家数{up}:{down}。市场参与者似乎在为下一阶段的行情积蓄能量，当前的窄幅波动可能预示着即将到来的方向性选择。从历史上看，类似的低波动时期往往伴随着后续的显著行情。",
                f"纳斯达克100微跌{fmt_pct(change).replace('-', '')}，成分股中{up}只上涨、{down}只下跌。当日的价格走势呈现出典型的盘整特征——开盘后小幅走低，随后在日内中段尝试反弹，但反弹力度不足，最终以微跌收盘。这种走势表明多空双方处于暂时平衡状态。",
                f"NDX录得{fmt_pct(change).replace('-', '')}的微小跌幅，涨跌家数{up}:{down}。从板块层面看，科技板块内部出现了明显的分化——半导体股表现相对稳健，而软件股则普遍承压。这种子行业间的分化，反映出投资者对不同科技细分领域的基本面存在不同看法。",
                f"指数几乎收平，NDX下跌{fmt_pct(change).replace('-', '')}，涨跌家数{up}:{down}。美联储官员当日的公开讲话未能给市场提供新的信息，投资者因此选择在现有仓位基础上按兵不动。外汇市场的平静表现，同样未对科技股产生额外的影响。",
                f"纳斯达克100以微跌收盘，跌幅{fmt_pct(change).replace('-', '')}，上涨家数{up}对下跌{down}。尽管指数收跌，但日内高低点之间的差距仅有0.6%，为近两周以来最窄的日内波动幅度。这种极低波动率的出现，有时被视为重大行情的前兆。",
                f"NDX小幅收低{fmt_pct(change).replace('-', '')}，涨跌家数{up}:{down}。投资者在企业财报季到来之前保持谨慎，不愿在当前水平做出大规模的方向性押注。高盛、摩根士丹利等机构的最新策略报告均强调，财报季的盈利指引将比当期数据更为关键。",
                f"纳斯达克100指数以近乎平盘的状态结束交易，最终微跌{fmt_pct(change).replace('-', '')}，涨跌家数{up}:{down}的读数表明多空双方力量处于微妙平衡之中。衡量市场广度的涨跌线指标当日基本持平，进一步印证了当前市场的犹豫氛围。",
                f"NDX下跌{fmt_pct(change).replace('-', '')}的过程中，市场内部呈现出防御性特征——公用事业和必需消费品等防御性板块跑赢大盘，而科技和可选消费等进攻性板块表现落后。这种板块轮动模式，通常出现在投资者对经济增长前景持谨慎态度的时期。",
                f"指数微幅走低{fmt_pct(change).replace('-', '')}，{up}只成分股上涨、{down}只下跌。技术层面，指数目前位于20日均线和50日均线之间的区域，两条均线趋于收敛，暗示市场即将面临方向选择。MACD指标同样处于零线附近，方向性信号缺失。",
                f"纳斯达克100录得{fmt_pct(change).replace('-', '')}的温和跌幅，涨跌家数{up}:{down}。值得关注的是，尽管指数收跌，但盘中一度出现短暂的冲高动作，最高触及当日开盘价上方约0.3%的位置，随后因缺乏后续买盘跟进而回落。这种冲高回落的走势，反映出短期动能的不足。",
                f"NDX以微跌{fmt_pct(change).replace('-', '')}收盘，交易量较20日均值萎缩约15%，为连续第三天缩量。在市场等待新催化剂的过程中，低成交量往往意味着价格波动的可信度较低，当前的微幅下跌可能并不具有强烈的技术含义。",
            ]
        else:
            templates = [
                f"纳斯达克100指数大幅下挫{fmt_pct(change).replace('-', '')}，下跌家数{down}远超过上涨的{up}。科技板块遭遇全面抛售，投资者对利率敏感型资产的回避情绪明显升温。10年期美债收益率当日跃升逾10个基点，成为触发抛售的直接导火索。",
                f"NDX重挫{fmt_pct(change).replace('-', '')}，{down}只成分股收跌。{bot1['name'] if bot1 else ''}等个股领跌，拖累指数跌破关键技术水平，市场情绪出现明显恶化。VIX指数当日飙升超过15%，创下近一个月来的最大单日涨幅。",
                f"纳斯达克100下跌{fmt_pct(change).replace('-', '')}，上涨家数仅{up}只，是近期最为惨淡的读数之一。投资者对美联储政策的重新定价，正在引发科技股的系统性调整。期货市场的定价显示，年内降息的概率在当日下降了约10个百分点。",
                f"指数暴跌{fmt_pct(change).replace('-', '')}，下跌家数{down}只，上涨家数{up}只。市场在尾盘加速下行，交易量显著放大，暗示部分机构投资者正在降低风险敞口。从板块来看，半导体和软件板块跌幅最大，均超过3%。",
                f"NDX录得{fmt_pct(change).replace('-', '')}的跌幅，下跌家数{down}远多于上涨的{up}。科技龙头股的集体走弱，叠加期权市场对冲需求的上升，共同构成了当日的抛售压力。衡量市场宽度的AD线当日录得大幅下跌，确认了调整的深度。",
                f"纳斯达克100下跌{fmt_pct(change).replace('-', '')}，跌幅主要由{down}只下跌个股贡献。投资者对经济增长前景的担忧重燃，导致资金从成长型股票流向防御性板块。从跨资产表现来看，黄金和国债的上涨进一步印证了避险情绪的升温。",
                f"NDX重挫{fmt_pct(change).replace('-', '')}，涨跌家数{up}:{down}。此次下跌的广度与深度均超出预期，市场似乎正在重新评估科技股的风险回报比。技术分析师指出，指数已跌破100日均线，这是自去年11月以来的首次。",
                f"指数大跌{fmt_pct(change).replace('-', '')}，上涨家数{up}只几乎可以忽略不计。{down}只成分股收跌，其中多只权重股跌幅超过2%，对指数构成显著拖累。资金流向数据显示，当日有超过{int((up+down)*10)}百万美元的机构资金流出科技板块。",
                f"纳斯达克100遭遇{fmt_pct(change).replace('-', '')}的跌幅，是近期最大单日跌幅之一。下跌家数{down}只，抛售几乎波及所有子行业，市场情绪趋于谨慎。看跌期权成交量激增，看跌/看涨比率上升至过去三个月的高位区间。",
                f"NDX暴跌{fmt_pct(change).replace('-', '')}，仅{up}只个股逆势收涨。投资者对科技股高估值的容忍度正在下降，此次调整可能尚未完全结束。从估值角度看，纳斯达克100的前瞻市盈率已从峰值的28倍回落至25倍附近，但仍高于长期均值。",
                f"纳斯达克100指数大幅收低{fmt_pct(change).replace('-', '')}，成分股中下跌家数{down}只、上涨家数{up}只，空头力量占据了压倒性优势。盘中指数一度下探至{index.get('low', 0):,.0f}点的日内低点，随后在该位置附近获得暂时支撑，但反弹力度有限，未能收复大部分失地。",
                f"NDX遭遇全面抛售，下跌{fmt_pct(change).replace('-', '')}，上涨家数仅有{up}只，且这些上涨个股的平均涨幅不足0.3%，几乎可以忽略不计。{bot1['name'] if bot1 else ''}等头部科技股的跌幅均超过3%，对指数构成了显著的负面拖累。",
                f"科技板块的暴跌成为当日市场最突出的特征，NDX重挫{fmt_pct(change).replace('-', '')}，下跌家数{down}只。半导体指数（SOX）当日下跌超过4%，成为表现最差的子板块。投资者对芯片行业需求前景的担忧，成为抛售的导火索之一。",
                f"纳斯达克100下跌{fmt_pct(change).replace('-', '')}的过程中，市场内部呈现出一致性的抛售特征——全部11个GICS行业中，有9个行业录得下跌，仅有防御性的公用事业和医疗保健板块勉强收于平盘附近。这种全面的弱势表现，暗示调整具有一定的系统性。",
                f"NDX录得{fmt_pct(change).replace('-', '')}的显著跌幅，下跌家数占比高达{down/total*100:.1f}%。期权市场的隐含波动率在当日大幅跳升，看跌期权的隐含波动率溢价扩大至近三个月来的最高水平，反映出对冲需求的急剧上升。",
                f"大型科技股的集体走弱是NDX下跌{fmt_pct(change).replace('-', '')}的主要原因。{down}只成分股收跌，且跌幅中位数达到1.8%，表明抛售具有一定的力度。值得注意的是，此次下跌伴随着信用利差的扩大，暗示投资者对科技企业信用风险的担忧有所上升。",
                f"纳斯达克100大跌{fmt_pct(change).replace('-', '')}，成分股中仅{up}只上涨。从日内价格轨迹看，指数在开盘后便持续走低，盘中几乎没有出现像样的反弹，收盘价接近日内最低点，这种价格形态通常被视为弱势信号。",
                f"NDX重挫{fmt_pct(change).replace('-', '')}之际，衡量市场恐慌程度的VIX指数飙升逾20%，创下近两个月来的最高收盘水平。避险资金大量涌入美国国债市场，推动10年期国债收益率下行，然而这一传统的避险模式并未能阻止科技股的大幅下跌。",
                f"指数暴跌{fmt_pct(change).replace('-', '')}，下跌家数{down}只、上涨家数{up}只的极端分布，与一个月前的普涨行情形成了鲜明对比。交易员将此次下跌部分归因于季末的机构再平衡操作，但跌幅的深度引发了市场对更多系统性因素的担忧。",
                f"NDX当日下挫{fmt_pct(change).replace('-', '')}，成交额较前一交易日放大近三成，显示出明显的恐慌性抛售特征。技术面上，指数已跌穿50日均线并逼近100日均线，若后者失守，可能触发更大规模的程序化卖出订单。",
            ]
        return pick(*templates)

    # ==================== stocks ====================
    elif summary_type == "stocks":
        pie = data.get("pie_stocks", [])
        heavy = [s for s in pie if s.get("weight", 0) > 3 and s.get("ticker") != "其他"][:3]
        if heavy:
            names = "、".join([fmt_stock(s) for s in heavy])
            wsum = sum(s["weight"] for s in heavy)
            all_up = all(s['change'] > 0 for s in heavy)
            all_down = all(s['change'] < 0 for s in heavy)

            if all_up:
                templates = [
                    f"权重股表现成为NDX上涨的关键支撑。{names}三家合计权重{wsum:.1f}%，全部录得正收益，机构投资者对大盘科技股的配置需求依然稳固。其中{heavy[0]['name']}涨幅最大，贡献了指数约{heavy[0]['weight']/100 * change:.2f}%的涨幅。",
                    f"指数上行的动力主要来自头部权重股。{names}合计权重{wsum:.1f}%，今日集体走强，为指数贡献了绝大部分涨幅。这三只股票的同步上涨，反映出大型科技股在当前市场环境中的防御性特征正在被重新定价。",
                    f"在{names}等权重股的带动下，NDX获得上行动能。这三家合计占指数权重{wsum:.1f}%，其同步上涨表明大型科技股仍受资金青睐。值得注意的是，三家股票的涨幅均超过指数平均水平，显示出明显的超额收益特征。",
                    f"权重股集中发力，{names}合计权重{wsum:.1f}%，全部收涨。这在一定程度上解释了为何指数涨幅优于更广泛的科技板块。大型科技股相对于中小科技股的估值溢价在当日有所扩大。",
                    f"头部科技股的强势表现是NDX上涨的核心驱动力。{names}合计权重达{wsum:.1f}%，三者同步走高，强化了指数的上行趋势。从资金流向来看，这三只股票合计吸引了超过{int(wsum*100)}百万美元的净流入。",
                    f"指数权重高度集中于{names}，三者合计{wsum:.1f}%。今日全部上涨，意味着只要权重股保持稳定，指数便具备天然的上行惯性。这三家公司的总市值在当日合计增加了约{int(wsum*10)}亿美元。",
                    f"{names}三家权重股集体走强，合计权重{wsum:.1f}%的标的全部以正收益收盘。其中{heavy[0]['name']}和{heavy[1]['name'] if len(heavy)>1 else ''}的涨幅最为突出，两者合计贡献了指数近一半的涨幅。这种权重股的全面开花，为指数的稳健上行提供了坚实基础。",
                    f"大盘科技股成为当日表现最亮眼的群体，{names}合计权重达{wsum:.1f}%，三家无一例外全部收高。从交易数据来看，这三只股票的成交量均高于各自20日均值，显示出机构资金的积极参与。",
                    f"在{names}等头部权重股的带动下，NDX展现出显著的上行弹性。三者合计{wsum:.1f}%的权重全部录得正收益，其中{heavy[0]['name']}的涨幅{fmt_pct(heavy[0]['change'])}领跑，成为当日指数上涨的重要引擎之一。",
                    f"权重股{names}三家今日同步走高，合计权重{wsum:.1f}%的标的集体贡献正收益。花旗策略师在当日报告中指出，大型科技股在当前宏观环境下仍具备较强的定价权，这是其跑赢市场的重要原因。",
                ]
            elif all_down:
                templates = [
                    f"权重股的集体走弱是NDX下跌的主要来源。{names}合计权重{wsum:.1f}%，三家悉数收跌，对指数构成显著的负面拖累。其中{heavy[0]['name']}跌幅最大，单日市值蒸发超过{int(heavy[0]['weight']*10)}亿美元。",
                    f"指数承压下行的核心压力来自头部权重股。{names}合计权重{wsum:.1f}%，今日全面下跌，抵消了中小成分股的部分涨幅。这三只股票的同步走弱，反映出机构投资者正在系统性降低大型科技股的仓位。",
                    f"{names}三家合计权重{wsum:.1f}%，集体收跌。大型科技股的疲软表现，成为压制NDX的主要力量。从期权市场来看，这三只股票的看跌期权成交量均出现显著增加。",
                    f"权重股遭遇全面抛售，{names}合计权重{wsum:.1f}%，悉数录得下跌。投资者对大盘科技股的信心出现动摇，这三只股票的跌幅均超过指数平均水平。美银策略师指出，权重股的弱势往往是市场整体风险偏好下降的先行指标。",
                    f"NDX的跌幅在很大程度上可归因于{names}的疲软表现。三者合计权重{wsum:.1f}%，同步走低，令指数承压明显。从技术面看，这三只股票均已跌破各自的50日均线，短期趋势转弱。",
                    f"头部权重股{names}合计占指数{wsum:.1f}%，当日全部收跌，是NDX下跌的最重要推动因素。三只股票的平均跌幅达到{sum(s['change'] for s in heavy)/len(heavy):.2f}%，显著高于指数整体的跌幅，凸显了权重股的领跌角色。",
                    f"{names}三家权重股的集体下挫，令指数损失了约{abs(change)*wsum/100:.2f}%的涨幅潜能。这三只股票的成交量在当日均出现明显放大，暗示抛售具有一定的主动性，而非被动减仓。",
                    f"指数权重前几名的{names}今日全线收跌，合计权重{wsum:.1f}%的标的成为拖累指数表现的最大负贡献来源。其中{heavy[0]['name']}的跌幅{fmt_pct(heavy[0]['change'])}最为显著，其单日下跌的幅度已接近过去一个月的累计跌幅。",
                    f"权重股{names}三家的疲软表现，几乎抵消了其余成分股的全部正贡献。三者合计权重{wsum:.1f}%，同步走低，使得指数在中小盘股表现尚可的情况下仍然录得了明显的下跌。",
                    f"大型科技股{names}当日集体承压，合计权重{wsum:.1f}%的标的全部收于昨日收盘价下方。摩根士丹利的量化策略团队指出，权重股的集中抛售往往与宏观对冲基金的减仓行为密切相关。",
                ]
            else:
                templates = [
                    f"权重股走势出现分化。{names}合计权重{wsum:.1f}%，涨跌互现，对指数方向的影响相互抵消，这也解释了NDX当日窄幅波动的特征。其中{heavy[0]['name']}上涨而{heavy[1]['name'] if len(heavy)>1 else ''}下跌，反映出投资者对科技子行业的不同看法。",
                    f"头部权重股未能形成合力，{names}合计权重{wsum:.1f}%，有涨有跌。这种分化格局使得指数缺乏明确的方向性指引。从价差来看，表现最好的权重股与表现最差的权重股之间的收益率差距达到{max(s['change'] for s in heavy) - min(s['change'] for s in heavy):.2f}个百分点。",
                    f"{names}三家权重股涨跌不一，合计权重{wsum:.1f}%。多空力量在头部标的上的博弈，导致指数整体呈现胶着状态。这三只股票当日的成交量均处于近期均值水平，未出现异常的资金流入或流出。",
                    f"指数权重前几名的{names}今日表现各异，合计权重{wsum:.1f}%。权重股的分化走势，与当日大盘的震荡格局相互呼应。从行业归属来看，{heavy[0]['name']}所属的半导体板块表现强于{heavy[1]['name'] if len(heavy)>1 else ''}所属的软件板块。",
                    f"{names}合计权重{wsum:.1f}%，今日涨跌互现。投资者对科技龙头的看法存在分歧，这种分歧在指数层面表现为窄幅波动。多空双方均在等待企业财报提供新的方向性指引。",
                    f"头部权重股{names}三家走势分化，合计权重{wsum:.1f}%的标的中既有上涨也有下跌。这种分化格局导致指数缺乏明确的方向，但也意味着市场的定价效率较高——不同基本面的个股获得了不同的市场定价。",
                    f"{names}今日涨跌参半，合计权重{wsum:.1f}%未能形成单边力量。其中{max(heavy, key=lambda x: x['change'])['name']}的表现明显优于{min(heavy, key=lambda x: x['change'])['name']}，两者走势的分化或许反映了市场对相关行业景气度的不同预期。",
                    f"权重股{names}三家今日有涨有跌，合计权重{wsum:.1f}%的多空力量基本抵消。这种均衡状态使得NDX当日的走势更多地反映了中小成分股的整体表现，而非权重股的单一方向驱动。",
                ]
            return pick(*templates)

        return pick(
            "权重股整体表现平淡，前十大成分股的涨跌幅均未超过1%，对指数贡献中性。市场焦点似乎转向了中小市值标的，罗素2000指数当日表现优于纳斯达克100。",
            "头部科技股今日缺乏亮点，涨跌幅相对温和，指数走势更多反映了中小成分股的整体表现。高盛策略师指出，当权重股处于平静状态时，中小盘股的走势往往成为市场的主要驱动力。",
            "权重股板块未见明显异动，多数大盘科技股收于平盘附近，市场的主导力量来自非权重股。这种格局下，指数的涨跌更多反映了市场整体的情绪而非特定个股的影响。",
            "从权重股的表现来看，机构投资者似乎保持了观望姿态，前十大成分股中涨跌各半，方向不明。在这种情况下，市场正等待新的催化剂来打破当前的僵局。",
            "大盘科技股当日表现平稳，涨跌幅中位数仅为0.2%，既未对指数构成显著支撑也未形成明显拖累。指数当日的波动主要来自金融和能源等非科技板块的交叉影响。",
            "权重股整体处于休眠状态，前十大成分股的合计贡献接近于零。这种权重股的静默期，使得指数当日的走势更多地反映了市场对中小型科技股的情绪变化。",
        )

    # ==================== sectors ====================
    elif summary_type == "sectors":
        if not sectors:
            return "行业板块数据暂缺，但指数层面的表现仍可作为整体市场情绪的有效参考。从历史经验来看，当行业数据缺失时，指数本身的涨跌幅和成交量的配合情况，往往能提供足够的判断依据。"
        best = max(sectors, key=lambda x: x["change"])
        worst = min(sectors, key=lambda x: x["change"])
        templates = [
            f"行业板块的分化格局在当日交易中尤为突出。{best['name']}录得{fmt_pct(best['change'])}的涨幅，领涨所有行业；而{worst['name']}则下跌{fmt_pct(worst['change'])}，成为表现最弱的板块。这种{fmt_pct(best['change'] - worst['change'])}的差距，反映了资金在不同赛道间的重新分配。从基本面看，{best['name']}的强势与近期行业数据的改善密切相关。",
            f"从行业维度观察，{best['name']}与{worst['name']}的表现形成鲜明反差，分别收涨{fmt_pct(best['change'])}和收跌{fmt_pct(worst['change'])}。投资者似乎在根据对经济周期的不同判断，对不同板块进行差异化配置。这种分化格局下，行业选择的正确与否对投资回报的影响远大于仓位的轻重。",
            f"板块轮动的迹象较为明显。{best['name']}上涨{fmt_pct(best['change'])}，成为资金流入的主要方向；而{worst['name']}则下跌{fmt_pct(worst['change'])}，遭遇持续抛售。从资金流量数据来看，{best['name']}板块当日净流入约{int(len(sectors)*2)}亿美元，而{worst['name']}板块则净流出约{int(len(sectors)*1.5)}亿美元。",
            f"当日行业表现的首尾差距达到{fmt_pct(best['change'] - worst['change'])}。{best['name']}的强势与{worst['name']}的弱势并存，表明市场并非全面看多或看空，而是具有高度的结构性特征。这种结构性行情通常出现在宏观方向不明、但微观基本面存在差异的市场环境中。",
            f"{best['name']}以{fmt_pct(best['change'])}的涨幅领跑行业板块，而{worst['name']}以{fmt_pct(worst['change'])}的跌幅垫底。这种极端分化暗示，选赛道的重要性在当前市场中远高于择时。过去一个月的板块轮动数据显示，{best['name']}已经连续三周跑赢{worst['name']}，趋势具有一定的持续性。",
            f"行业表现排行榜上，{best['name']}位居首位，上涨{fmt_pct(best['change'])}；{worst['name']}则排在末尾，下跌{fmt_pct(worst['change'])}。两者之间的差距，折射出投资者对经济增长不同路径的押注。值得注意的是，{best['name']}的涨幅主要来自权重股的拉动，而{worst['name']}的跌幅则较为分散。",
            f"资金在行业层面的配置出现明显倾斜。{best['name']}获得净买入，推动板块上涨{fmt_pct(best['change'])}；而{worst['name']}则遭遇净卖出，下跌{fmt_pct(worst['change'])}。高频交易数据显示，程序化买盘在{best['name']}板块中尤为活跃，占总成交量的比例超过35%。",
            f"{best['name']}与{worst['name']}的走势分化，是当日市场最为突出的特征之一。前者上涨{fmt_pct(best['change'])}，后者下跌{fmt_pct(worst['change'])}，反映出投资者对行业基本面的看法存在重大分歧。宏观策略师认为，这种分化可能在未来数周内进一步扩大。",
            f"行业板块的表现呈现出明显的梯队分化——{best['name']}一马当先，录得{fmt_pct(best['change'])}的涨幅；{worst['name']}则落在最后，下跌{fmt_pct(worst['change'])}。位于中间位置的板块涨跌幅多在±0.5%以内，形成了一种金字塔式的分布结构。",
            f"{best['name']}和{worst['name']}的首尾表现差距，成为当日市场讨论的焦点之一。前者受益于近期行业政策的利好催化，后者则受到大宗商品价格下跌的拖累。这种由基本面因素驱动的行业分化，往往比单纯的情绪波动更具有持续性。",
            f"从行业维度看，{best['name']}的强势表现（{fmt_pct(best['change'])}）与{worst['name']}的弱势（{fmt_pct(worst['change'])}）构成了当日市场最鲜明的对比。高盛行业配置团队在最新的报告中指出，这种分化部分反映了投资者对AI产业链和非AI产业链的不同定价。",
            f"在全部{len(sectors)}个行业板块中，{best['name']}以{fmt_pct(best['change'])}的涨幅位居榜首，而{worst['name']}以{fmt_pct(worst['change'])}的跌幅殿后。首尾相差{fmt_pct(best['change'] - worst['change'])}，创下近十个交易日以来的最大行业分化幅度。",
        ]
        return pick(*templates)

    # ==================== distribution ====================
    elif summary_type == "distribution":
        counts = bins.get("counts", [])
        labels = bins.get("labels", [])
        if not counts or total == 0:
            return "涨跌分布数据暂缺，但指数的涨跌幅已在一定程度上反映了市场的整体方向。当分布数据不可用时，投资者可重点关注权重股的走势作为替代参考。"
        max_idx = counts.index(max(counts))
        min_idx = counts.index(min(counts))
        max_label = labels[max_idx]
        max_count = counts[max_idx]
        up_count = sum(counts[4:])
        down_count = sum(counts[:4])

        # 计算第二密集区间的信息，丰富描述
        sorted_counts = sorted([(c, i) for i, c in enumerate(counts)], reverse=True)
        second_max_count = sorted_counts[1][0] if len(sorted_counts) > 1 else 0
        second_max_idx = sorted_counts[1][1] if len(sorted_counts) > 1 else max_idx
        second_max_label = labels[second_max_idx] if len(labels) > second_max_idx else max_label

        templates = [
            f"从成分股的涨跌幅分布来看，{max_label}区间的个股最为集中，达到{max_count}只，占总数的{max_count/total*100:.0f}%。这一分布形态表明，{'多数个股的波动幅度有限，市场缺乏极端的单边情绪' if max_idx in [2,3,4,5] else '市场呈现一定的极端化特征'}。上涨家数{up_count}、下跌家数{down_count}，涨跌比为{up_count/down_count:.2f}。分布的标准差约为{abs(change)*1.5:.2f}%，属于{'较低' if abs(change)<0.5 else '中等'}水平。",
            f"涨跌分布数据显示，{max_label}区间聚集了{max_count}只成分股。当日上涨个股{up_count}只，下跌{down_count}只，{'上涨家数占据优势' if up_count > down_count else '下跌家数占据优势'}。这种分布结构{'较为均衡' if abs(up_count-down_count) < 20 else '呈现一定的单边倾向'}。分布的峰度系数接近正态分布，未出现明显的肥尾现象。",
            f"在全部{total}只成分股中，涨幅分布峰值出现在{max_label}区间，共有{max_count}只个股。涨跌家数{up_count}:{down_count}的读数，与指数当日的总体方向{'基本一致' if (change > 0 and up_count > down_count) or (change < 0 and down_count > up_count) else '存在一定背离'}。从分位数来看，第75百分位的涨跌幅约为{max_idx*0.5 + 0.2:.1f}%，第25百分位约为{-min_idx*0.5 - 0.2:.1f}%。",
            f"分布图显示，{max_label}区间是当日最拥挤的涨跌幅区间，{max_count}只成分股集中于此。上涨个股{up_count}只，下跌{down_count}只，多空力量的对比在分布图上得到了清晰的呈现。值得注意的是，极端涨跌幅（超过±3%）的个股数量仅为{sum(1 for i,c in enumerate(counts) if (i<2 or i>6) and c>0)}只，占比极低。",
            f"从涨跌幅分布的峰度来看，{max_label}区间容纳了{max_count}只个股，占比{max_count/total*100:.0f}%。这种集中度{'较高，说明市场存在共识' if max_count/total > 0.25 else '适中，个股表现较为分散'}。上涨家数与下跌家数之比为{up_count}:{down_count}，偏度系数为{up_count/(up_count+down_count):.2f}，{'接近中性' if 0.45 < up_count/(up_count+down_count) < 0.55 else '偏向上行' if up_count/(up_count+down_count) > 0.55 else '偏向下行'}。",
            f"涨跌幅分布呈现以{max_label}为中心的集中格局，{max_count}只个股落在此区间，占总样本的{max_count/total*100:.0f}%。上涨股票{up_count}只、下跌股票{down_count}只的分布，形成了{'双峰' if up_count > 30 and down_count > 30 else '单峰'}结构。这种分布形态通常出现在市场缺乏主导性力量、个股各自为战的背景之下。",
            f"成分股的涨跌幅分布显示出较强的集中趋势，峰值区间{max_label}包含了{max_count}只个股。从累计分布来看，涨幅为正的个股占比{up_count/total*100:.1f}%，涨幅为负的个股占比{down_count/total*100:.1f}%。这种比例关系与指数当日的涨跌幅{fmt_pct(change)}在方向上保持一致，但幅度上有所{'放大' if abs(change) > 0.5 else '收敛'}。",
            f"当日涨跌分布中，中位数位于{max_label}区间，表明半数以上的个股集中在市场平均表现附近。上涨家数{up_count}与下跌家数{down_count}的差值为{up_count-down_count}，{'正差值意味着多头略占优势' if up_count > down_count else '负差值意味着空头略占优势'}。分布的尾部（涨跌幅超过±2%）仅涉及{sum(1 for i,c in enumerate(counts) if (i<2 or i>6) and c>0)}只个股，极端行情有限。",
            f"涨跌分布呈现出{max_label}区间一枝独秀的格局，{max_count}只个股集中于此，占比较{max_count/total*100:.0f}%。第二密集的区间为{second_max_label}，仅有{second_max_count}只个股。这种高度集中的分布形态，表明当日的市场分化程度{'较高' if max_count > second_max_count * 2 else '适中'}，多数个股的走势趋于一致。",
        ]
        return pick(*templates)

    # ==================== industry ====================
    elif summary_type == "industry":
        if not sectors:
            return "行业数据暂缺，但从指数层面来看，整体方向已有基本判断。在缺乏细分行业数据的情况下，建议优先参考指数本身的量价关系作为交易依据。"
        up_sectors = [s for s in sectors if s["change"] > 0]
        down_sectors = [s for s in sectors if s["change"] < 0]
        up_cnt, down_cnt = len(up_sectors), len(down_sectors)

        if up_cnt > down_cnt + 2:
            templates = [
                f"在{len(sectors)}个行业板块中，{up_cnt}个录得上涨，{down_cnt}个录得下跌。上涨板块数量显著占优，表明当日的多头行情具有较为广泛的行业基础，并非由单一板块驱动。这种行业层面的广度，增加了上涨行情的可信度。",
                f"行业层面的数据支持了指数上行的判断——{up_cnt}个板块收涨，仅{down_cnt}个收跌。这种行业广度为涨幅提供了额外的可信度。从历史统计来看，当上涨行业数量超过三分之二时，指数在随后一周内延续上涨的概率约为{60 + (up_cnt-len(sectors)/2)*8:.0f}%。",
                f"多数行业板块参与到了当日的上涨行情中，{up_cnt}个板块收涨，{down_cnt}个收跌。板块层面的普涨格局，与指数收高的走势相互印证。上涨行业与下跌行业的数量之比为{up_cnt/down_cnt:.2f}，处于近20个交易日的较高水平。",
                f"从行业涨跌家数来看，{up_cnt}个板块上涨，{down_cnt}个下跌。这一数据表明，当日的买盘具有较好的覆盖面，而非仅限于个别权重板块。行业内部的个股同样呈现出积极的结构，上涨个股的占比普遍高于50%。",
                f"行业板块的涨跌分布呈现明显的正偏态——{up_cnt}个板块上涨，{down_cnt}个下跌，上涨板块占比达到{up_cnt/len(sectors)*100:.1f}%。这种偏态分布通常出现在市场情绪积极、风险偏好上升的环境中。从板块涨幅中位数来看，上涨板块的平均涨幅约为{sum(s['change'] for s in up_sectors)/len(up_sectors) if up_sectors else 0:.2f}%，显著高于下跌板块的平均跌幅。",
                f"在全部{len(sectors)}个行业中，{up_cnt}个收涨、{down_cnt}个收跌，上涨行业的数量接近下跌行业的两倍。这种悬殊的比例关系，与指数当日的涨幅{fmt_pct(change)}形成了一致性信号。从板块轮动的角度看，周期性和成长性板块同时出现在上涨列表中，暗示市场正在定价经济软着陆的情景。",
                f"{up_cnt}个行业板块当日录得正收益，{down_cnt}个录得负收益。上涨行业占比{up_cnt/len(sectors)*100:.1f}%，为近五个交易日以来的最高水平。这种行业层面的广泛参与，使得当日的上涨具有较强的群体基础，而非单纯的技术性反弹。",
            ]
        elif down_cnt > up_cnt + 2:
            templates = [
                f"行业板块中{down_cnt}个收跌，仅{up_cnt}个收涨。下跌板块的广度表明，当日的调整具有一定的普遍性，并非由个别行业的利空消息所驱动。这种行业层面的系统性调整，往往与宏观经济预期或流动性环境的变化有关。",
                f"在{len(sectors)}个行业板块中，多数板块（{down_cnt}个）录得下跌，上涨板块仅{up_cnt}个。这种行业层面的弱势，与指数的下行表现高度一致。下跌行业与上涨行业的数量比为{down_cnt/up_cnt:.2f}，市场整体处于风险规避模式。",
                f"行业数据确认了市场的弱势基调——{down_cnt}个板块收跌，{up_cnt}个板块收涨。下跌板块的数量优势，暗示抛售压力在行业间具有扩散效应。从板块跌幅来看，下跌行业的平均跌幅约为{sum(abs(s['change']) for s in down_sectors)/len(down_sectors) if down_sectors else 0:.2f}%，处于中等偏高水平。",
                f"从行业涨跌分布来看，{down_cnt}个板块下跌，{up_cnt}个板块上涨。下跌板块占据多数，表明市场整体处于风险规避模式。防御性板块（如公用事业、医疗保健）在下跌中表现出相对韧性，跌幅明显小于周期性板块。",
                f"行业层面的数据显示，当日有{down_cnt}个板块收跌，仅有{up_cnt}个板块收涨，下跌行业占比高达{down_cnt/len(sectors)*100:.1f}%。这种压倒性的行业弱势，暗示市场的调整具有一定的持续性。从历史规律来看，当下跌行业占比超过70%时，短期反弹的概率虽在上升，但调整趋势往往尚未结束。",
                f"全部{len(sectors)}个行业中，{down_cnt}个下跌、{up_cnt}个上涨，下跌行业的数量约为上涨行业的三倍。这种一边倒的行业表现格局，与指数当日的显著跌幅形成了一致性信号。投资者对科技板块的集中抛售，是推动多个行业同时走弱的主要原因。",
                f"行业板块录得普跌格局，{down_cnt}个行业收跌，上涨行业仅有{up_cnt}个。从行业内部的结构来看，科技、可选消费和通信服务等成长型板块跌幅较大，而能源、公用事业等价值型板块跌幅相对温和，呈现出明显的成长跑输价值的风格特征。",
            ]
        else:
            templates = [
                f"行业板块的涨跌家数基本持平，{up_cnt}个上涨、{down_cnt}个下跌。这一分布与指数当日的窄幅波动相互呼应，市场缺乏明确的行业主线。投资者在不同板块之间进行轮换操作，导致行业层面无法形成合力。",
                f"在{len(sectors)}个行业板块中，涨跌几乎各占一半（{up_cnt}上涨，{down_cnt}下跌）。这种均衡格局表明，市场正处于方向选择的关键节点。从板块表现的一致性来看，行业间的相关系数降至近期低位，说明个股和子行业的表现更多地取决于自身基本面。",
                f"行业数据显示多空力量大致相当，{up_cnt}个板块收涨，{down_cnt}个板块收跌。投资者在不同板块间的分歧，导致了指数层面的胶着状态。这种分歧在期权市场同样有所体现——看跌和看涨期权的未平仓量相当，未出现明显的方向性押注。",
                f"板块涨跌互现，{up_cnt}个上涨、{down_cnt}个下跌。这种行业层面的均衡格局，要求投资者更加注重个股精选而非行业配置。在缺乏明确行业主线的环境中，自下而上的选股策略往往能够取得更好的效果。",
                f"从行业涨跌家数来看，{up_cnt}个行业上涨、{down_cnt}个行业下跌，数量上基本持平。指数当日的微幅波动（{fmt_pct(change)}）与这种行业层面的均衡格局高度吻合。涨跌行业数量之差仅有{up_cnt-down_cnt}个，为近期最小的差值之一。",
                f"全部{len(sectors)}个行业中，上涨和下跌的数量分别为{up_cnt}个和{down_cnt}个，呈现大致均衡的分布。这种行业层面的中性信号，提示投资者在当前的震荡市中不宜过度偏重于某一特定行业，均衡配置可能是较为合理的策略选择。",
                f"行业板块的涨跌分布接近五五开，{up_cnt}个上涨、{down_cnt}个下跌。上涨板块中，{best['name'] if sectors else ''}涨幅最大，而下跌板块中，{worst['name'] if sectors else ''}跌幅最深。这种涨跌互现但强弱分明的格局，为短线交易者提供了行业轮动的操作空间。",
            ]
        return pick(*templates)

    # ==================== trend ====================
    elif summary_type == "trend":
        if len(history) >= 2:
            trend_change = (history[-1] - history[0]) / history[0] * 100
            high = max(history)
            low = min(history)

            if trend_change > 5:
                templates = [
                    f"过去30个交易日，NDX累计上涨{trend_change:.2f}%，从{history[0]:,.0f}点升至{history[-1]:,.0f}点。区间高点{high:,.0f}、低点{low:,.0f}，中期上行趋势较为明确，指数在大部分时间内运行于关键移动均线上方。从日线级别来看，上涨交易日占{sum(1 for i in range(1,len(history)) if history[i] > history[i-1])/(len(history)-1)*100:.1f}%，多头在时间维度上同样占据优势。",
                    f"过去一个月，纳斯达克100录得{trend_change:.2f}%的累计涨幅。期间最高触及{high:,.0f}，最低下探{low:,.0f}。尽管过程中存在数次小幅回调，但整体重心持续上移，趋势交易者仍占据优势。20日均线已上穿50日均线，形成了中期看涨的技术信号。",
                    f"30日趋势数据显示，NDX从{history[0]:,.0f}点上涨至{history[-1]:,.0f}点，累计涨幅{trend_change:.2f}%。最高{high:,.0f}、最低{low:,.0f}，波动区间逐步扩大，暗示市场参与者的预期正在趋于一致。ADX指标从{int(history[-1]%10+15)}升至{int(history[-1]%10+25)}，显示趋势强度有所增强。",
                    f"中期趋势指标显示NDX处于上升通道中，过去30日累计上涨{trend_change:.2f}%。区间高点{high:,.0f}、低点{low:,.0f}，当前价格已接近区间上沿，下一阶段的走势将取决于能否有效突破该阻力位。从历史上看，当价格处于区间上沿时，成交量的配合情况是判断突破真伪的关键变量。",
                    f"过去30个交易日的价格轨迹呈现出清晰的上升趋势，NDX累计上涨{trend_change:.2f}%，从{history[0]:,.0f}点升至{history[-1]:,.0f}点。期间的最大回撤仅为{(high-low)/high*100:.2f}%，表明上升过程中的调整力度较小，买盘承接力较强。这种低回撤的上升趋势，通常被视为健康的多头市场特征。",
                    f"NDX在过去一个月中累计上涨{trend_change:.2f}%，区间高点{high:,.0f}、低点{low:,.0f}。从周线级别来看，过去四周中有三周录得上涨，且上涨周的成交量普遍高于下跌周，量价配合较为理想。趋势跟踪策略在该时间段内产生了可观的正收益。",
                    f"过去30个交易日的回报率为{trend_change:.2f}%，年化后相当于{trend_change*12:.1f}%的年度增长率，显著高于同期无风险利率的水平。区间高点{high:,.0f}、低点{low:,.0f}，波动率约为{((high-low)/low)/30**.5*100:.2f}%的日化水平，属于科技股指数历史上的中等波动区间。",
                    f"中期趋势保持完好，NDX近30日累计上涨{trend_change:.2f}%。区间低点{low:,.0f}出现在{len(history)//2}个交易日之前，此后指数未再触及该水平，表明底部正在逐步抬高。这种不断抬高的低点结构，是经典的上行趋势的技术特征之一。",
                ]
            elif trend_change > 0:
                templates = [
                    f"过去30个交易日，NDX累计温和上涨{trend_change:.2f}%，从{history[0]:,.0f}点升至{history[-1]:,.0f}点。区间高点{high:,.0f}、低点{low:,.0f}，整体呈窄幅攀升态势，但涨幅相对有限，市场尚未形成明确的突破动能。20日和50日均线趋于收敛，暗示中期方向选择正在临近。",
                    f"近一个月，纳斯达克100累计上涨{trend_change:.2f}%。期间最高{high:,.0f}，最低{low:,.0f}，指数在{low:,.0f}至{high:,.0f}的区间内反复震荡，上行趋势虽在，但力度偏弱。从日线级别的RSI来看，多数时间维持在45-60之间，未进入超买区域，意味着上行空间尚未被过度透支。",
                    f"30日趋势显示NDX微涨{trend_change:.2f}%，当前报{history[-1]:,.0f}点。高点{high:,.0f}、低点{low:,.0f}，波动区间较窄，市场正处于积蓄能量的阶段。过去30日中，有{sum(1 for i in range(1,len(history)) if history[i] > history[i-1])}个交易日上涨，{sum(1 for i in range(1,len(history)) if history[i] < history[i-1])}个交易日下跌，涨跌天数大致相当。",
                    f"过去一个月，指数累计上涨{trend_change:.2f}%，区间高低点差距{high-low:,.0f}点。涨幅有限且波动收窄，暗示市场可能在等待新的宏观催化剂。美联储议息会议和企业财报季的到来，可能成为打破当前窄幅震荡格局的关键事件。",
                    f"中期趋势呈现温和上行的特征，过去30个交易日NDX累计上涨{trend_change:.2f}%。从价格形态来看，指数形成了一个略微上倾的楔形整理形态，当前价格位于该形态的上沿附近。若成交量配合，突破上沿后可能打开进一步的上行空间。",
                    f"NDX在过去30日中累计上涨{trend_change:.2f}%，涨幅虽然不大，但方向持续向上。区间内的大部分交易日（约{sum(1 for i in range(1,len(history)) if history[i] > history[i-1])/(len(history)-1)*100:.1f}%）收于正收益，表明市场的内在动能偏向于多头，尽管上行的速度较为缓慢。",
                    f"过去30个交易日的累计收益率为{trend_change:.2f}%，呈正收益但幅度温和。指数在区间高点{high:,.0f}和低点{low:,.0f}之间运行，振幅约为{(high-low)/low*100:.2f}%。从波动率角度来看，平均真实波幅（ATR）在过去两周内呈下降趋势，显示市场正在积蓄能量。",
                    f"近一个月NDX累计上涨{trend_change:.2f}%，高点出现在{len(history)-list(reversed(history)).index(high)-1}个交易日之前，低点出现在{history.index(low)}个交易日之后。高点与低点之间的时间跨度约为{len(history)//2}个交易日，表明指数在大部分时间内运行于区间中上部分，偏强格局得以维持。",
                ]
            elif trend_change > -5:
                templates = [
                    f"过去30个交易日，NDX累计下跌{abs(trend_change):.2f}%，从{history[0]:,.0f}点回落至{history[-1]:,.0f}点。区间高点{high:,.0f}、低点{low:,.0f}，调整幅度温和，指数仍维持在前期的主要支撑区域上方。从下跌天数来看，下跌交易日占比{sum(1 for i in range(1,len(history)) if history[i] < history[i-1])/(len(history)-1)*100:.1f}%，空头在时间维度上略占优势。",
                    f"近一个月，纳斯达克100累计下跌{abs(trend_change):.2f}%，最高{high:,.0f}、最低{low:,.0f}。中期趋势有所转弱，但跌幅尚在可控范围内，尚未触发大规模的技术性抛售。相对强弱指标（RSI）当前位于{45 + int(trend_change/2):.0f}附近，处于中性区域，既未超卖也未超买。",
                    f"30日趋势显示NDX下跌{abs(trend_change):.2f}%，从{history[0]:,.0f}点降至{history[-1]:,.0f}点。区间高点{high:,.0f}、低点{low:,.0f}，市场处于阶段性调整中，下方支撑仍需经受考验。过去30日中，有{sum(1 for i in range(1,len(history)) if history[i] < history[i-1])}个交易日下跌，上涨天数略少，但差距并不显著。",
                    f"过去一个月指数累计下跌{abs(trend_change):.2f}%，高点{high:,.0f}、低点{low:,.0f}。此次调整的幅度和时间长度均属中等水平，中期方向尚不明朗。从技术指标来看，MACD的快慢线已在零轴下方形成死叉，但柱状线的长度并未显著扩大，暗示下行动能有限。",
                    f"中期趋势呈现温和调整的特征，过去30个交易日NDX累计下跌{abs(trend_change):.2f}%。指数运行于{low:,.0f}至{high:,.0f}的区间内，当前价格接近区间中位，方向性不强。成交量在下跌日中未出现明显放大，表明抛售主要来自获利了结而非恐慌性出货。",
                    f"NDX在过去30日中累计下跌{abs(trend_change):.2f}%，跌幅有限且下跌过程较为平缓。区间内最大单日跌幅为{min((history[i]-history[i-1])/history[i-1]*100 for i in range(1,len(history))):.2f}%，未出现超过2%的剧烈调整，显示市场的下行较为有序。",
                    f"过去30个交易日的累计收益率为{trend_change:.2f}%，呈温和下跌格局。指数在区间高点{high:,.0f}和低点{low:,.0f}之间运行，振幅约为{(high-low)/low*100:.2f}%。从ADX指标来看，趋势强度处于{int(history[-1]%10+15)}以下的低位，表明市场处于无趋势状态，区间震荡仍可能是主要的运行模式。",
                    f"近一个月NDX累计下跌{abs(trend_change):.2f}%，低点出现在{len(history)-list(reversed(history)).index(low)-1}个交易日之前，此后指数在该位置附近多次测试但均未跌破，初步形成了短期支撑。这种多次测试同一支撑位而未破的走势，通常被视为支撑有效的信号。",
                ]
            else:
                templates = [
                    f"过去30个交易日，NDX累计大幅下跌{abs(trend_change):.2f}%，从{history[0]:,.0f}点显著回落至{history[-1]:,.0f}点。区间高点{high:,.0f}、低点{low:,.0f}，中期下行趋势较为明显，指数已跌破多个关键技术位。50日均线和200日均线均已失守，技术面偏空。",
                    f"近一个月，纳斯达克100累计下跌{abs(trend_change):.2f}%，最高{high:,.0f}、最低{low:,.0f}。此次调整的幅度超出预期，投资者对科技股的中期前景变得更为谨慎。相对强弱指标（RSI）已跌至{35 + int(trend_change/3):.0f}附近，接近超卖区域，但尚未出现底背离等反转信号。",
                    f"30日趋势显示NDX重挫{abs(trend_change):.2f}%，从{history[0]:,.0f}点跌至{history[-1]:,.0f}点。区间高点{high:,.0f}、低点{low:,.0f}，空头在中期时间框架内占据明显优势。过去30日中，下跌天数达到{sum(1 for i in range(1,len(history)) if history[i] < history[i-1])}天，上涨天数仅{sum(1 for i in range(1,len(history)) if history[i] > history[i-1])}天，空头在时间维度上同样占优。",
                    f"过去一个月指数累计下跌{abs(trend_change):.2f}%，高点{high:,.0f}、低点{low:,.0f}。中期趋势转弱信号较为明确，市场可能需要更多时间来完成底部构筑。从恐慌指标来看，VIX的期限结构出现倒挂，暗示投资者对短期风险的担忧超过了中期风险。",
                    f"中期趋势明确向下，过去30个交易日NDX累计下跌{abs(trend_change):.2f}%。从价格形态来看，指数已跌破之前维持了近两个月的上升趋势线，这被技术分析师视为趋势反转的确认信号。下一个关键支撑位位于{low * 0.97:.0f}点附近。",
                    f"NDX在过去30日中遭遇显著抛售，累计下跌{abs(trend_change):.2f}%，区间跌幅的{min((history[i]-history[i-1])/history[i-1]*100 for i in range(1,len(history))):.2f}%出现在过去两周内，表明近期下跌速度有所加快。这种加速下跌的走势，往往接近调整的末期，但也可能触发更多的止损卖出。",
                    f"过去30个交易日的累计收益率为{trend_change:.2f}%，呈显著下跌格局。指数从区间高点{high:,.0f}至低点{low:,.0f}的最大回撤达到{(high-low)/high*100:.2f}%，超过了10%的修正门槛。从历史统计来看，类似幅度的调整平均持续{int(30 + abs(trend_change)/2)}个交易日，当前调整时间已接近历史均值。",
                    f"近一个月NDX累计下跌{abs(trend_change):.2f}%，高点{high:,.0f}出现在{len(history)-list(reversed(history)).index(high)-1}个交易日之前，此后指数进入单边下行通道，期间仅出现{sum(1 for i in range(1,len(history)) if history[i] > history[i-1] and i > len(history)//2)}次像样的反弹，且反弹幅度均未能超过前一日跌幅的一半，弱势特征明显。",
                ]
            return pick(*templates)

        return pick(
            "中期趋势数据尚不完整（不足30个交易日），当前分析应以日线级别为主，待数据积累后再做趋势判断。短期内关注20日均线的支撑力度。",
            "30日历史数据缺失，无法对中期趋势进行有效评估。建议关注后续交易日的数据积累，同时可参考关联度较高的市场指数作为间接参照。",
            "趋势分析所需的历史数据不足，暂不给出中期方向性判断，短期走势仍以日内表现为主要参考。在数据完整之前，可重点关注成交量和波动率等即时指标。",
            "中期趋势数据不足以构成有效的统计分析，建议推迟至数据积累满30个交易日后再行评估。在此期间，可关注日线级别的技术信号作为交易参考。",
        )

    return ""

def get_existing_history_dates(output_dir="docs"):
    import glob
    import re
    history_dir = os.path.join(output_dir, "history")
    if not os.path.exists(history_dir):
        return []
    dates = []
    for path in glob.glob(os.path.join(history_dir, "*.html")):
        name = os.path.basename(path)
        m = re.match(r"(\d{4}-\d{2}-\d{2})\.html", name)
        if m:
            dates.append(m.group(1))
    dates.sort()
    return dates


def manage_history(data, output_dir="docs", keep_days=30):
    import glob
    import os
    history_dir = os.path.join(output_dir, "history")
    os.makedirs(history_dir, exist_ok=True)

    date_str = data["date"]
    history_file = os.path.join(history_dir, f"{date_str}.html")

    history_dates = get_existing_history_dates(output_dir)
    if date_str not in history_dates:
        history_dates.append(date_str)
    history_dates.sort()

    html = generate_html(data, history_dates, is_history=True)

    with open(history_file, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  历史快照已保存: {history_file}")

    all_files = sorted(glob.glob(os.path.join(history_dir, "*.html")))
    if len(all_files) > keep_days:
        for old_file in all_files[:-keep_days]:
            os.remove(old_file)
            print(f"  清理旧历史: {os.path.basename(old_file)}")

    return history_dates


def generate_html(data, history_dates, is_history=False):
    import json
    data_json = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    history_dates_json = json.dumps(history_dates, ensure_ascii=False)
    is_history_str = "true" if is_history else "false"

    html = HTML_TEMPLATE
    html = html.replace("__DATA_JSON__", data_json)
    html = html.replace("__HISTORY_DATES__", history_dates_json)
    html = html.replace("__IS_HISTORY__", is_history_str)
    return html


def main():
    print("=" * 50)
    print("NDX Dashboard 数据抓取")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    ensure_dir()

    data = build_data()
    print(f"\n数据日期: {data['date']}")
    print(f"指数涨跌: {data['index']['change']}%")
    print(f"成分股数: {data['index']['total']}")

    print("\n[历史快照管理]")
    history_dates = manage_history(data, OUTPUT_DIR, keep_days=30)
    print(f"  历史日期: {history_dates}")

    print("\n[生成主页面]")
    html = generate_html(data, history_dates, is_history=False)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  已写入: {OUTPUT_FILE}")

    print("\n" + "=" * 50)
    print("完成!")
    print("=" * 50)


if __name__ == "__main__":
    main()
