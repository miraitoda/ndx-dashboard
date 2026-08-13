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
.global-grid{position:fixed;inset:0;pointer-events:none;z-index:0}
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
.header{position:sticky;top:38px;z-index:99;backdrop-filter:blur(20px);background:var(--header-bg);border-bottom:1px solid var(--border)}
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
  filter: blur(0.5px);
}
.contour-green {
  background:
    radial-gradient(ellipse 600px 400px at 20% 30%, rgba(57,255,20,0.04) 0%, transparent 70%),
    radial-gradient(ellipse 500px 350px at 70% 60%, rgba(57,255,20,0.03) 0%, transparent 65%),
    radial-gradient(ellipse 400px 300px at 40% 80%, rgba(57,255,20,0.035) 0%, transparent 60%),
    radial-gradient(ellipse 700px 450px at 80% 20%, rgba(57,255,20,0.025) 0%, transparent 75%),
    radial-gradient(ellipse 350px 280px at 10% 70%, rgba(57,255,20,0.03) 0%, transparent 55%);
  animation: drift-green 25s ease-in-out infinite alternate;
}
.contour-purple {
  background:
    radial-gradient(ellipse 550px 380px at 60% 40%, rgba(191,0,255,0.04) 0%, transparent 70%),
    radial-gradient(ellipse 480px 320px at 30% 70%, rgba(191,0,255,0.03) 0%, transparent 65%),
    radial-gradient(ellipse 420px 350px at 85% 15%, rgba(191,0,255,0.035) 0%, transparent 60%),
    radial-gradient(ellipse 650px 400px at 15% 50%, rgba(191,0,255,0.025) 0%, transparent 75%),
    radial-gradient(ellipse 380px 260px at 55% 85%, rgba(191,0,255,0.03) 0%, transparent 55%);
  animation: drift-purple 30s ease-in-out infinite alternate;
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
    <div class="logo">NDX<span class="logo-accent">.</span>DASHBOARD</div>
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
    """本地生成AI总结，使用丰富的专业话术模板，每天固定组合保证一致性。"""
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

    up = index.get("up", 0)      # 上涨家数（绿）
    down = index.get("down", 0)  # 下跌家数（红）
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
    is_bullish = change > 0 and up_ratio > 0.55
    is_bearish = change < 0 and up_ratio < 0.45
    is_mixed = not is_bullish and not is_bearish

    # -------- overview：大盘综述 --------
    if summary_type == "overview":
        if change > 1.5:
            templates = [
                f"纳斯达克100指数今日强势收涨{fmt_pct(change)}，上涨成分股{up}只，下跌{down}只，多头情绪主导全场。",
                f"NDX大涨{fmt_pct(change)}，上涨家数达{up}只，科技板块全面走强，空头回补迹象显著。",
                f"今日行情超出预期，纳斯达克100指数录得{fmt_pct(change)}涨幅，涨跌比{up}:{down}，赚钱效应突出。",
                f"科技龙头集中发力，NDX收高{fmt_pct(change)}，{up}只成分股收于昨日收盘价上方，下跌仅{down}只。",
                f"指数单边上行，纳斯达克100收报{fmt_pct(change)}，{up}只个股录得正收益，市场风险偏好明显回升。",
                f"开盘即呈现强势特征，NDX最终收涨{fmt_pct(change)}，上涨家数占比达{up/total*100:.1f}%，普涨格局明确。",
                f"近期罕见之普涨行情，NDX大涨{fmt_pct(change)}，涨跌家数比{up}:{down}，多头完全掌控盘面。",
                f"今日涨幅{fmt_pct(change)}为近一个月最大单日涨幅之一，{up}只成分股收高，市场信心显著修复。",
                f"纳斯达克100收涨{fmt_pct(change)}，{up}只成分股飘绿（涨），资金回流科技主线的迹象明显。",
                f"大盘呈单边上涨态势，NDX收高{fmt_pct(change)}，{up}涨{down}跌，日内几乎未见有效抛压。",
                f"{fmt_stock(top1)}大涨{fmt_pct(top1['change'])}领跑权重股，带动NDX录得{fmt_pct(change)}的强劲涨幅。",
                f"涨跌比{up}:{down}凸显多头压倒性优势，NDX今日大涨{fmt_pct(change)}，为近期最强表现之一。",
                f"纳指100今日表现堪称近期最强，{fmt_pct(change)}的涨幅配合{up}只上涨成分股，多头格局稳固。",
                f"指数强势突破，NDX收涨{fmt_pct(change)}，上涨家数{up}只，市场呈现典型的risk-on模式。",
                f"今日空头遭受重挫，NDX飙升{fmt_pct(change)}，{up}只个股收涨，{down}只收跌，单边行情特征显著。",
                f"纳斯达克100指数上涨{fmt_pct(change)}，{up}只成分股录得涨幅，市场情绪明显偏向乐观。",
                f"权重股集体爆发，{fmt_stock(top1)}领涨{fmt_pct(top1['change'])}，NDX今日劲升{fmt_pct(change)}。",
                f"多头全日控盘，纳指100收高{fmt_pct(change)}，{up}涨{down}跌，趋势强度超出预期。",
                f"强势格局延续，NDX今日上涨{fmt_pct(change)}，前五大权重股贡献了主要涨幅。",
                f"多头攻势凌厉，纳指100大涨{fmt_pct(change)}，仅{down}只成分股收跌，呈现全面开花格局。",
                f"今日盘面之强劲令人侧目，NDX收高{fmt_pct(change)}，{up}只个股录得正收益，下跌个股几乎可忽略。",
                f"行情势头猛烈，纳指100直接拉涨{fmt_pct(change)}，{up}只成分股收绿（涨），多头势不可挡。",
                f"今日大盘表现亮眼，NDX上涨{fmt_pct(change)}，上涨家数{up}只，持仓者普遍录得正回报。",
                f"纳指100今日表现抢眼，{fmt_pct(change)}的涨幅配合{up}只上涨个股，科技股或迎来新一轮上行周期。",
                f"市场呈现抢筹行情，NDX飙升{fmt_pct(change)}，{up}涨{down}跌，资金流入意愿强烈。",
            ]
        elif change > 0:
            templates = [
                f"纳斯达克100指数小幅收高{fmt_pct(change)}，涨跌家数{up}:{down}，市场呈现温和的正面基调。",
                f"NDX微涨{fmt_pct(change)}，{up}只成分股收绿（涨），整体涨跌互现，日内交投相对平淡。",
                f"指数窄幅震荡后收于正值区间，纳指100上涨{fmt_pct(change)}，上涨家数略占优势，但上行动能有限。",
                f"市场录得温和反弹，NDX收高{fmt_pct(change)}，{up}只成分股收涨，{down}只收跌，分化格局延续。",
                f"纳斯达克100指数小幅走高{fmt_pct(change)}，板块轮动有序，但缺乏明确的方向性突破。",
                f"NDX今日收涨{fmt_pct(change)}，涨跌家数{up}:{down}，虽涨幅有限但方向偏上，多头略占优势。",
                f"指数微幅收高，纳指100上涨{fmt_pct(change)}，{up}只个股录得涨幅，但整体涨幅温和，观望氛围尚存。",
                f"今日市场提供有限的正回报，NDX收高{fmt_pct(change)}，涨跌家数{up}:{down}，信号偏正面但力度不足。",
                f"纳斯达克100指数上涨{fmt_pct(change)}，{up}只成分股录得正收益，整体情绪偏暖但交投清淡。",
                f"今日走势缺乏方向性，NDX微涨{fmt_pct(change)}，涨跌家数{up}:{down}，市场仍在消化近期信息。",
                f"指数温和上行，NDX收涨{fmt_pct(change)}，上涨家数{up}只，反弹力度有限，资金略显犹豫。",
                f"纳斯达克100今日录得{fmt_pct(change)}的小幅涨幅，{up}涨{down}跌，大盘处于区间震荡上沿。",
                f"NDX收于小幅正区间，{fmt_pct(change)}，{up}只成分股走高，本周开局偏正面。",
                f"大盘温和收红（涨），纳指100上涨{fmt_pct(change)}，{up}只成分股收涨，市场情绪偏向谨慎乐观。",
                f"今日走势不温不火，NDX微涨{fmt_pct(change)}，{up}涨{down}跌，市场等待新的催化剂。",
                f"纳斯达克100指数小幅收涨{fmt_pct(change)}，涨跌家数{up}:{down}，整体维持区间震荡格局。",
                f"NDX今日微幅走高{fmt_pct(change)}，{fmt_stock(top1)}领涨，但整体涨跌互现，方向尚未明朗。",
                f"大盘窄幅波动后收于正值区间，纳指100上涨{fmt_pct(change)}，上涨家数略占优势。",
                f"市场录得温和涨幅，NDX收高{fmt_pct(change)}，{up}只成分股收涨，{down}只收跌，多空相对均衡。",
                f"纳斯达克100指数小幅走高{fmt_pct(change)}，板块轮动有序，上行动能有待加强。",
                f"NDX今日收涨{fmt_pct(change)}，涨跌家数{up}:{down}，方向正确但力度温和，保持耐心。",
                f"大盘微幅收涨，纳指100上涨{fmt_pct(change)}，{up}只个股上涨，趋势方向偏上但动能不足。",
                f"今日市场提供温和正收益，NDX收高{fmt_pct(change)}，{up}涨{down}跌，继续观察后续发展。",
                f"纳斯达克100指数今日上涨{fmt_pct(change)}，{up}只成分股收涨，偏暖基调延续但缺乏爆发力。",
                f"今日行情偏正面但缺乏激情，NDX涨{fmt_pct(change)}，{up}涨{down}跌，市场仍在寻找方向。",
            ]
        elif change > -1:
            templates = [
                f"纳斯达克100指数微幅收跌{fmt_pct(change)}，涨跌家数{up}:{down}，市场处于观望模式，方向性不强。",
                f"NDX窄幅收低{fmt_pct(change)}，多空力量大致均衡，{fmt_stock(top1)}与{fmt_stock(bot1)}走势分化显著。",
                f"指数围绕平盘震荡，纳指100收跌{fmt_pct(change)}，涨跌家数接近，缺乏明确趋势信号。",
                f"市场录得小幅整理，NDX下跌{fmt_pct(change)}，{up}只上涨，{down}只下跌，交投清淡。",
                f"纳斯达克100指数微幅收低{fmt_pct(change)}，板块表现参差不齐，未形成清晰主线。",
                f"NDX今日下跌{fmt_pct(change).replace('-', '')}，涨跌家数{up}:{down}，调整幅度有限，属正常波动。",
                f"大盘微幅收跌，纳指100下滑{fmt_pct(change)}，{up}只个股逆势上涨，多空博弈陷入僵局。",
                f"今日市场乏善可陈，NDX收低{fmt_pct(change)}，涨跌家数{up}:{down}，投资者等待新数据指引。",
                f"纳斯达克100指数下跌{fmt_pct(change)}，{up}只成分股收涨，整体偏弱但下行空间有限。",
                f"今日走势索然无味，NDX微跌{fmt_pct(change)}，{up}涨{down}跌，市场处于消化阶段。",
                f"指数小幅走低，NDX收跌{fmt_pct(change)}，上涨家数{up}只，调整幅度可控，未见恐慌情绪。",
                f"纳斯达克100今日录得{fmt_pct(change)}的小幅下跌，{up}涨{down}跌，大盘在近期区间内运行。",
                f"NDX收于平盘下方，{fmt_pct(change)}，{up}只成分股走高，{down}只走低，方向感缺失。",
                f"大盘微幅收阴（跌），纳指100下跌{fmt_pct(change)}，{up}只成分股收涨，市场等待新的催化因素。",
                f"今日走势平淡无奇，NDX微跌{fmt_pct(change)}，{up}涨{down}跌，建议保持观望。",
                f"纳斯达克100指数微幅收低{fmt_pct(change)}，涨跌家数{up}:{down}，市场观望情绪较浓。",
                f"NDX窄幅收低{fmt_pct(change)}，多空力量相对均衡，个股层面分化明显。",
                f"大盘平盘震荡，纳指100收跌{fmt_pct(change)}，涨跌家数接近，等待方向性突破。",
                f"市场录得小幅整理，NDX下跌{fmt_pct(change)}，{up}只上涨，{down}只下跌，成交趋于清淡。",
                f"指数微幅收低，纳斯达克100下跌{fmt_pct(change)}，板块表现分化，缺乏合力。",
                f"NDX今日微跌{fmt_pct(change).replace('-', '')}，涨跌家数{up}:{down}，幅度温和，无需过度解读。",
                f"大盘小幅收跌，纳指100下滑{fmt_pct(change)}，{up}只个股上涨，多空拉锯仍在继续。",
                f"今日市场略显沉闷，NDX收低{fmt_pct(change)}，{up}涨{down}跌，大家都在等待方向信号。",
                f"纳斯达克100指数下跌{fmt_pct(change)}，{up}只成分股收涨，整体偏弱但仍在可控范围内。",
                f"今日走势缺乏亮点，NDX微跌{fmt_pct(change)}，{up}涨{down}跌，继续观望为上。",
            ]
        else:
            templates = [
                f"纳斯达克100指数今日承压收跌{fmt_pct(change).replace('-', '')}，{down}只成分股录得下跌，市场进入调整模式。",
                f"NDX大幅下挫{fmt_pct(change).replace('-', '')}，{fmt_stock(bot1)}领跌{fmt_pct(bot1['change'])}，避险情绪显著升温。",
                f"大盘回调明显，纳指100下跌{fmt_pct(change)}，仅{up}只个股收涨，空头占据主导地位。",
                f"市场全面走弱，NDX收低{fmt_pct(change)}，{down}只成分股收跌，权重股拖累效应显著。",
                f"调整格局延续，纳斯达克100下跌{fmt_pct(change)}，{fmt_stock(bot1)}、{fmt_stock(bottom5[-2] if len(bottom5) > 1 else bot1)}跌幅居前。",
                f"今日大盘表现疲软，NDX下跌{fmt_pct(change).replace('-', '')}，{down}只个股收跌，赚钱效应匮乏。",
                f"纳斯达克100今日下挫{fmt_pct(change)}，涨跌家数{up}:{down}，下跌家数显著占优，风险偏好回落。",
                f"市场遭遇明显抛压，NDX大跌{fmt_pct(change)}，仅{up}只收涨，空头肆虐。",
                f"指数单边下行，纳指100收低{fmt_pct(change)}，{down}只成分股下跌，市场信心受挫。",
                f"今日跌幅{fmt_pct(change)}在近期属于较大水平，{down}只个股下跌，市场情绪偏向悲观。",
                f"NDX今日下挫{fmt_pct(change)}，涨跌家数{up}:{down}，下跌家数远超上涨，建议保持防御姿态。",
                f"纳斯达克100今日收出中阴线，下跌{fmt_pct(change)}，{down}只个股收跌，短期或需进一步消化。",
                f"大盘走弱，NDX下跌{fmt_pct(change)}，{fmt_stock(bot1)}领跌，拖累整体市场情绪。",
                f"今日市场表现惨淡，NDX重挫{fmt_pct(change)}，{down}只成分股收跌，持仓者普遍承压。",
                f"纳斯达克100今日表现不佳，下跌{fmt_pct(change)}，{down}只个股收跌，科技板块集体回调。",
                f"今日空头占据上风，NDX下跌{fmt_pct(change)}，涨跌家数{up}:{down}，短期趋势偏空。",
                f"大盘进入回调模式，纳指100下跌{fmt_pct(change)}，{down}只个股收跌，市场进入调整阶段。",
                f"今日行情令人失望，NDX下挫{fmt_pct(change)}，{down}只个股收跌，赚钱效应极差。",
                f"纳斯达克100收跌{fmt_pct(change).replace('-', '')}，{down}只成分股下跌，市场承压调整。",
                f"NDX今日大幅下挫{fmt_pct(change).replace('-', '')}，{fmt_stock(bot1)}领跌，避险情绪蔓延。",
                f"大盘回调明显，纳指100下跌{fmt_pct(change)}，仅{up}只上涨，空头主导格局。",
                f"市场全面走弱，NDX收低{fmt_pct(change)}，{down}只成分股收跌，权重股拖累显著。",
                f"调整格局延续，纳斯达克100下跌{fmt_pct(change)}，头部科技股跌幅较大。",
                f"今日大盘表现疲软，NDX下跌{fmt_pct(change).replace('-', '')}，{down}只个股收跌，建议加强防守。",
                f"纳斯达克100今日下挫{fmt_pct(change)}，涨跌家数{up}:{down}，下跌家数偏多，短期维持谨慎。",
            ]
        return pick(*templates)

    # -------- stocks：权重股点评 --------
    elif summary_type == "stocks":
        pie = data.get("pie_stocks", [])
        heavy = [s for s in pie if s.get("weight", 0) > 3 and s.get("ticker") != "其他"][:3]
        if heavy:
            names = "、".join([fmt_stock(s) for s in heavy])
            wsum = sum(s["weight"] for s in heavy)
            all_up = all(s['change'] > 0 for s in heavy)
            all_down = all(s['change'] < 0 for s in heavy)
            mixed = not all_up and not all_down

            if all_up:
                return pick(
                    f"权重股集体走强，{names}合计权重{wsum:.1f}%，对指数形成显著支撑。",
                    f"头部权重股今日表现强劲，{names}三家均录得正收益，合计权重{wsum:.1f}%，是推动指数上行的核心力量。",
                    f"{names}三大权重股齐齐发力，合计权重达{wsum:.1f}%，带动效应十分明显。",
                    f"指数权重高度集中，{names}三家合计占比{wsum:.1f}%，今日集体上涨，为NDX提供强劲上行动能。",
                    f"权重股方面，{names}表现优异，合计{wsum:.1f}%的权重全部收涨（涨），对指数贡献显著。",
                    f"头部科技龙头{names}今日全线走高，合计权重{wsum:.1f}%，集中发力推动指数上扬。",
                    f"{names}三家权重股今日同步上涨，合计权重{wsum:.1f}%，构成今日上涨的核心驱动力。",
                    f"指数权重前几名的{names}今日集体收涨，合计权重{wsum:.1f}%，多头弹药集中于此。",
                )
            elif all_down:
                return pick(
                    f"权重股集体承压，{names}合计权重{wsum:.1f}%，成为拖累指数的主要因素。",
                    f"头部权重股今日全面走弱，{names}三家均录得下跌，合计权重{wsum:.1f}%，对指数形成显著拖累。",
                    f"{names}三大权重股齐齐下挫，合计权重达{wsum:.1f}%，带跌效应明显。",
                    f"指数权重高度集中，{names}三家合计占比{wsum:.1f}%，今日集体下跌，对NDX构成较大压力。",
                    f"权重股方面，{names}表现疲软，合计{wsum:.1f}%的权重全部收跌，拖累指数表现。",
                    f"头部科技龙头{names}今日全线走低，合计权重{wsum:.1f}%，集中下挫压制指数。",
                    f"{names}三家权重股今日同步下跌，合计权重{wsum:.1f}%，构成今日下行的核心压力。",
                    f"指数权重前几名的{names}今日集体收跌，合计权重{wsum:.1f}%，空头弹药集中于此。",
                )
            else:
                return pick(
                    f"权重股走势分化，{names}合计权重{wsum:.1f}%，涨跌互现，对指数影响相互抵消。",
                    f"头部权重股表现不一，{names}三家合计权重{wsum:.1f}%，分化格局明显。",
                    f"{names}三大权重股今日有涨有跌，合计权重达{wsum:.1f}%，对指数方向影响中性。",
                    f"指数权重高度集中，{names}三家合计占比{wsum:.1f}%，今日涨跌互现，指数波动有限。",
                    f"权重股方面，{names}表现分化，合计{wsum:.1f}%的权重涨跌互现。",
                    f"头部科技龙头{names}今日强弱不一，合计权重{wsum:.1f}%，多空互相拉扯。",
                    f"{names}三家权重股今日涨跌各半，合计权重{wsum:.1f}%，对指数贡献中性。",
                    f"指数权重前几名的{names}今日走势分化，合计权重{wsum:.1f}%，方向不明确。",
                )
        return pick(
            "权重股今日表现分化，头部科技龙头涨跌互现，缺乏明确的方向性指引。",
            "前十大权重股走势不一，市场主线模糊，各标的各自为战。",
            "权重股整体平稳运行，对指数贡献中性，今日并非权重行情。",
            "头部个股今日波动有限，权重分布稳定，指数走势较为真实地反映了市场整体状况。",
            "权重股表现中规中矩，无明显领涨或领跌品种，指数走势相对客观。",
            "今日权重股整体偏平淡，对指数影响有限，市场焦点或集中在中小盘标的。",
            "头部权重股今日涨跌参半，权重效应不明显，市场呈分散化特征。",
            "权重股今日整体温和，未见剧烈波动，指数走势较为平缓。",
        )

    # -------- sectors：最强/最弱板块 --------
    elif summary_type == "sectors":
        if not sectors:
            return "行业板块数据暂缺，建议关注指数整体走势及后续行业数据更新。"
        best = max(sectors, key=lambda x: x["change"])
        worst = min(sectors, key=lambda x: x["change"])
        return pick(
            f"从板块表现来看，{best['name']}今日表现最佳，录得{fmt_pct(best['change'])}的涨幅；{worst['name']}则表现滞后，收跌{fmt_pct(worst['change'])}。",
            f"行业板块呈现显著分化，{best['name']}领涨{fmt_pct(best['change'])}，而{worst['name']}垫底{fmt_pct(worst['change'])}。",
            f"{best['name']}今日走势强劲，板块平均涨幅{fmt_pct(best['change'])}；{worst['name']}承压下行，录得{fmt_pct(worst['change'])}，板块间差距扩大。",
            f"从行业维度看，{best['name']}与{worst['name']}形成鲜明对比，分别录得{fmt_pct(best['change'])}和{fmt_pct(worst['change'])}，呈冰火两重天格局。",
            f"今日{best['name']}板块表现最为亮眼，上涨{fmt_pct(best['change'])}；{worst['name']}则表现不佳，下跌{fmt_pct(worst['change'])}。",
            f"板块方面，{best['name']}领跑全市场，录得{fmt_pct(best['change'])}的涨幅；{worst['name']}则拖累整体表现，下跌{fmt_pct(worst['change'])}。",
            f"{best['name']}成为今日板块中的佼佼者，上涨{fmt_pct(best['change'])}；{worst['name']}则表现落后，下跌{fmt_pct(worst['change'])}。",
            f"行业层面，{best['name']}表现最佳，录得{fmt_pct(best['change'])}的正收益；{worst['name']}相对弱势，下跌{fmt_pct(worst['change'])}。",
            f"今日资金明显偏向{best['name']}板块，录得{fmt_pct(best['change'])}的涨幅；{worst['name']}则遭到抛售，下跌{fmt_pct(worst['change'])}。",
            f"行业分化加剧，{best['name']}大幅上涨{fmt_pct(best['change'])}，{worst['name']}大幅下跌{fmt_pct(worst['change']).replace('-', '')}，选对赛道至关重要。",
            f"{best['name']}今日为板块增色，上涨{fmt_pct(best['change'])}；{worst['name']}则表现尴尬，下跌{fmt_pct(worst['change'])}。",
            f"从行业表现看，{best['name']}和{worst['name']}处于两个极端，分别录得{fmt_pct(best['change'])}和{fmt_pct(worst['change'])}。",
            f"今日{best['name']}方向最强，上涨{fmt_pct(best['change'])}；{worst['name']}方向最弱，下跌{fmt_pct(worst['change'])}，结构性行情特征明显。",
            f"板块轮动今日轮至{best['name']}，录得{fmt_pct(best['change'])}的涨幅；{worst['name']}则遭到资金撤离，下跌{fmt_pct(worst['change'])}。",
            f"{best['name']}今日扛起领涨大旗，上涨{fmt_pct(best['change'])}；{worst['name']}则成为拖累，下跌{fmt_pct(worst['change'])}。",
        )

    # -------- distribution：涨跌分布 --------
    elif summary_type == "distribution":
        counts = bins.get("counts", [])
        labels = bins.get("labels", [])
        if not counts or total == 0:
            return "涨跌分布数据暂缺，但可从指数涨跌幅大致判断市场结构。"
        max_idx = counts.index(max(counts))
        max_label = labels[max_idx]
        max_count = counts[max_idx]
        up_count = sum(counts[4:])
        down_count = sum(counts[:4])

        if max_idx < 2:
            shape_desc = "跌幅较大的个股相对集中"
        elif max_idx > 5:
            shape_desc = "涨幅较大的个股相对集中"
        elif max_idx in [2, 3, 4, 5]:
            shape_desc = "多数个股涨跌幅集中在中间区间，波动有限"
        else:
            shape_desc = "涨跌幅分布较为分散，个股表现各异"

        return pick(
            f"{shape_desc}。{max_label}区间聚集了{max_count}只个股，占比{max_count/total*100:.0f}%。",
            f"从分布结构看，{max_label}区间个股最多（{max_count}只），上涨家数{up_count}、下跌家数{down_count}，呈{'涨多跌少' if up_count > down_count else '跌多涨少'}格局。",
            f"今日{max_label}为最大分布区间（{max_count}只），市场整体{'偏向上行' if up_count > down_count else '偏向调整'}，分布{'相对均衡' if abs(up_count - down_count) < 15 else '呈单边特征'}。",
            f"分布数据显示{max_label}区间集中了{max_count}只成分股，涨跌比约为{up_count}:{down_count}，{'多头占优' if up_count > down_count else '空头占优'}。",
            f"今日多数个股涨跌幅落在{max_label}区间，共{max_count}只。整体{'涨多跌少' if up_count > down_count else '跌多涨少'}，具体为{up_count}只上涨、{down_count}只下跌。",
            f"从涨跌分布来看，{max_label}是最为拥挤的区间，有{max_count}只个股。{up_count}只上涨、{down_count}只下跌，{'多头格局' if up_count > down_count else '空头格局'}明显。",
            f"{max_label}区间今日扎堆了{max_count}只个股，占比近{max_count/total*100:.0f}%。整体{up_count}涨{down}跌，{'盘面偏暖' if up_count > down_count else '盘面偏冷'}。",
            f"今日涨跌分布的峰值位于{max_label}，共{max_count}只。{up_count}只收涨、{down_count}只收跌，{'普涨格局' if up_count > down_count + 20 else '普跌格局' if down_count > up_count + 20 else '涨跌参半'}。",
            f"观察分布图，{max_label}区间最为密集（{max_count}只），{'上涨家数占优' if up_count > down_count else '下跌家数占优'}，比例为{up_count}:{down_count}。",
            f"今日{max_count}只个股集中在{max_label}区间，整体{up_count}涨{down_count}跌，{'市场情绪偏乐观' if up_count > down_count else '市场情绪偏谨慎'}。",
            f"涨跌分布呈{max_label}区间集中态势，共{max_count}只，占总数的{max_count/total*100:.0f}%。",
            f"从分布看，{max_label}区间个股最多（{max_count}只），上涨{up_count}只、下跌{down_count}只。",
            f"今日{max_label}为最大阵营（{max_count}只），市场整体{'偏向上行' if up_count > down_count else '偏向调整'}。",
            f"分布图显示{max_label}集中了{max_count}只成分股，涨跌比约为{up_count}:{down_count}。",
            f"今日多数个股涨跌幅落在{max_label}区间，共{max_count}只，整体{'涨多跌少' if up_count > down_count else '跌多涨少'}。",
        )

    # -------- industry：行业涨跌家数 --------
    elif summary_type == "industry":
        if not sectors:
            return "行业板块数据暂缺，建议后续补充以完善行业维度分析。"
        up_sectors = [s for s in sectors if s["change"] > 0]
        down_sectors = [s for s in sectors if s["change"] < 0]
        flat_sectors = [s for s in sectors if s["change"] == 0]

        if len(up_sectors) > len(down_sectors) + 2:
            return pick(
                f"{len(up_sectors)}个板块收涨，{len(down_sectors)}个板块收跌，行业层面整体偏强，上涨板块占据多数。",
                f"多数板块录得正收益，{len(up_sectors)}个行业上涨，仅{len(down_sectors)}个下跌，赚钱效应较好。",
                f"行业呈现普涨格局，{len(up_sectors)}个板块飘红（涨），{len(down_sectors)}个板块飘绿（跌），整体基调偏暖。",
                f"今日{len(up_sectors)}个板块上涨，{len(down_sectors)}个板块下跌，行业维度多头占优。",
                f"从行业来看，{len(up_sectors)}个上涨、{len(down_sectors)}个下跌，上涨板块数量明显领先。",
                f"板块今日表现正面，{len(up_sectors)}个收涨，{len(down_sectors)}个收跌，整体氛围良好。",
                f"{len(up_sectors)}个行业收涨，{len(down_sectors)}个收跌，行业整体偏强。",
                f"多数板块上涨，{len(up_sectors)}个行业录得正收益，仅{len(down_sectors)}个收跌。",
                f"行业普涨格局明确，{len(up_sectors)}个板块上涨，{len(down_sectors)}个板块下跌。",
            )
        elif len(down_sectors) > len(up_sectors) + 2:
            return pick(
                f"{len(up_sectors)}个板块收涨，{len(down_sectors)}个板块收跌，行业整体偏弱，下跌板块占据多数。",
                f"多数板块录得负收益，{len(down_sectors)}个行业下跌，仅{len(up_sectors)}个上涨，亏钱效应明显。",
                f"行业呈现跌多涨少格局，{len(down_sectors)}个板块飘绿（跌），{len(up_sectors)}个板块飘红（涨），整体基调偏冷。",
                f"今日{len(down_sectors)}个板块下跌，{len(up_sectors)}个板块上涨，行业维度空头占优。",
                f"从行业来看，{len(up_sectors)}个上涨、{len(down_sectors)}个下跌，下跌板块数量明显领先。",
                f"板块今日表现负面，{len(down_sectors)}个收跌，{len(up_sectors)}个收涨，整体氛围偏冷。",
                f"{len(up_sectors)}个行业收涨，{len(down_sectors)}个收跌，行业整体偏弱。",
                f"多数板块下跌，{len(down_sectors)}个行业录得负收益，仅{len(up_sectors)}个收涨。",
                f"行业跌多涨少格局明确，{len(down_sectors)}个板块下跌，{len(up_sectors)}个板块上涨。",
            )
        else:
            return pick(
                f"{len(up_sectors)}个板块收涨，{len(down_sectors)}个板块收跌，行业涨跌参半，结构性特征突出。",
                f"板块涨跌各半，{len(up_sectors)}个行业上涨，{len(down_sectors)}个下跌，分化格局显著。",
                f"行业层面基本均衡，{len(up_sectors)}个板块上涨，{len(down_sectors)}个板块下跌，选股重于择时。",
                f"今日{len(up_sectors)}个板块上涨，{len(down_sectors)}个板块下跌，板块间相互对冲。",
                f"从行业来看，{len(up_sectors)}个上涨、{len(down_sectors)}个下跌，基本呈五五开格局。",
                f"板块今日涨跌互现，{len(up_sectors)}个收涨，{len(down_sectors)}个收跌，结构性机会为主。",
                f"{len(up_sectors)}个行业收涨，{len(down_sectors)}个收跌，板块涨跌参半。",
                f"板块涨跌各半，{len(up_sectors)}个行业上涨，{len(down_sectors)}个下跌。",
                f"行业层面基本平衡，{len(up_sectors)}个板块上涨，{len(down_sectors)}个板块下跌。",
            )

    # -------- trend：30日趋势 --------
    elif summary_type == "trend":
        if len(history) >= 2:
            trend_change = (history[-1] - history[0]) / history[0] * 100
            high = max(history)
            low = min(history)

            if trend_change > 5:
                return pick(
                    f"过去30个交易日，纳斯达克100指数累计上涨{trend_change:.2f}%，从{history[0]:,.0f}点升至{history[-1]:,.0f}点，上行趋势稳健。区间高点{high:,.0f}、低点{low:,.0f}。",
                    f"近一个月NDX累计上涨{trend_change:.2f}%，重心持续上移。最高触及{high:,.0f}，最低下探{low:,.0f}，中期趋势向好。",
                    f"30日趋势向上，累计涨幅{trend_change:.2f}%，当前报{history[-1]:,.0f}点。期间最高{high:,.0f}、最低{low:,.0f}，呈稳步攀升格局。",
                    f"过去一个月，NDX累计上涨{trend_change:.2f}%，走势健康。区间{low:,.0f}-{high:,.0f}，高点不断抬高，低点同步上移。",
                    f"30日走势显示，指数累计上涨{trend_change:.2f}%，从{history[0]:,.0f}升至{history[-1]:,.0f}，期间最高{high:,.0f}，中期趋势偏强。",
                    f"近一个月NDX表现良好，累计上涨{trend_change:.2f}%，当前位于{history[-1]:,.0f}点。波动区间{low:,.0f}-{high:,.0f}，整体方向向上。",
                    f"过去30个交易日，NDX累计上涨{trend_change:.2f}%，上行趋势明确。高点{high:,.0f}，低点{low:,.0f}，多头格局稳固。",
                    f"近30日NDX累计上涨{trend_change:.2f}%，区间高点{high:,.0f}、低点{low:,.0f}，整体重心稳步上移。",
                )
            elif trend_change > 0:
                return pick(
                    f"过去30个交易日，纳斯达克100指数累计微涨{trend_change:.2f}%，从{history[0]:,.0f}点至{history[-1]:,.0f}点，涨幅温和但方向偏上。区间高点{high:,.0f}、低点{low:,.0f}。",
                    f"近一个月NDX累计上涨{trend_change:.2f}%，重心小幅上移。最高{high:,.0f}，最低{low:,.0f}，走势温和。",
                    f"30日趋势小幅向上，累计涨幅{trend_change:.2f}%，当前报{history[-1]:,.0f}点。期间最高{high:,.0f}、最低{low:,.0f}，呈窄幅攀升态势。",
                    f"过去一个月，NDX累计上涨{trend_change:.2f}%，走势较为平淡。区间{low:,.0f}-{high:,.0f}，缺乏明显趋势。",
                    f"30日走势显示，指数累计上涨{trend_change:.2f}%，从{history[0]:,.0f}升至{history[-1]:,.0f}，期间最高{high:,.0f}，趋势偏暖但力度有限。",
                    f"近一个月NDX表现一般，累计上涨{trend_change:.2f}%，当前位于{history[-1]:,.0f}点。波动区间{low:,.0f}-{high:,.0f}，延续震荡格局。",
                    f"过去30个交易日，NDX累计上涨{trend_change:.2f}%，走势较为纠结。高点{high:,.0f}，低点{low:,.0f}，方向尚未明朗。",
                    f"近30日NDX累计上涨{trend_change:.2f}%，区间高点{high:,.0f}、低点{low:,.0f}，整体重心小幅上移。",
                )
            elif trend_change > -5:
                return pick(
                    f"过去30个交易日，纳斯达克100指数累计下跌{abs(trend_change):.2f}%，从{history[0]:,.0f}点回落至{history[-1]:,.0f}点，调整幅度温和。区间高点{high:,.0f}、低点{low:,.0f}。",
                    f"近一个月NDX累计下跌{abs(trend_change):.2f}%，重心小幅下移。最高{high:,.0f}，最低{low:,.0f}，呈温和调整格局。",
                    f"30日趋势小幅向下，累计跌幅{abs(trend_change):.2f}%，当前报{history[-1]:,.0f}点。期间最高{high:,.0f}、最低{low:,.0f}，偏弱震荡。",
                    f"过去一个月，NDX累计下跌{abs(trend_change):.2f}%，走势平淡。区间{low:,.0f}-{high:,.0f}，波动有限。",
                    f"30日走势显示，指数累计下跌{abs(trend_change):.2f}%，从{history[0]:,.0f}回落至{history[-1]:,.0f}，期间最高{high:,.0f}，趋势偏冷但跌幅可控。",
                    f"近一个月NDX表现一般，累计下跌{abs(trend_change):.2f}%，当前位于{history[-1]:,.0f}点。波动区间{low:,.0f}-{high:,.0f}，继续寻底。",
                    f"过去30个交易日，NDX累计下跌{abs(trend_change):.2f}%，走势较为纠结。高点{high:,.0f}，低点{low:,.0f}，方向不明。",
                    f"近30日NDX累计下跌{abs(trend_change):.2f}%，区间高点{high:,.0f}、低点{low:,.0f}，整体重心小幅下移。",
                )
            else:
                return pick(
                    f"过去30个交易日，纳斯达克100指数累计下跌{abs(trend_change):.2f}%，从{history[0]:,.0f}点显著回落至{history[-1]:,.0f}点，调整幅度较大。区间高点{high:,.0f}、低点{low:,.0f}。",
                    f"近一个月NDX累计下跌{abs(trend_change):.2f}%，重心明显下移。最高{high:,.0f}，最低{low:,.0f}，中期趋势偏弱。",
                    f"30日趋势向下，累计跌幅{abs(trend_change):.2f}%，当前报{history[-1]:,.0f}点。期间最高{high:,.0f}、最低{low:,.0f}，走势承压。",
                    f"过去一个月，NDX累计下跌{abs(trend_change):.2f}%，表现疲软。区间{low:,.0f}-{high:,.0f}，重心持续下探。",
                    f"30日走势显示，指数累计下跌{abs(trend_change):.2f}%，从{history[0]:,.0f}回落至{history[-1]:,.0f}，期间最高{high:,.0f}，中期趋势偏空。",
                    f"近一个月NDX表现不佳，累计下跌{abs(trend_change):.2f}%，当前位于{history[-1]:,.0f}点。波动区间{low:,.0f}-{high:,.0f}，整体承压。",
                    f"过去30个交易日，NDX累计下跌{abs(trend_change):.2f}%，走势较弱。高点{high:,.0f}，低点{low:,.0f}，需保持警惕。",
                    f"近30日NDX累计下跌{abs(trend_change):.2f}%，区间高点{high:,.0f}、低点{low:,.0f}，整体重心下移。",
                )
        return pick(
            "30日趋势数据暂缺，建议关注后续中期走势变化，暂不急于做出趋势判断。",
            "历史数据不足，无法有效评估中期趋势，待数据积累后再行分析。",
            "30天走势数据缺失，短期建议先以日线级别表现作为参考依据。",
            "趋势数据暂缺，但单日走势亦能提供一定的方向性参考。",
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
