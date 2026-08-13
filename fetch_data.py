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
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

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
.ticker-bar{position:sticky;z-index:100;background:var(--ticker-bg);overflow:hidden;backdrop-filter:blur(20px)}
.ticker-bar-top{top:0;border-bottom:1px solid var(--ticker-border)}
.ticker-bar-bottom{position:fixed;bottom:0;left:0;right:0;z-index:100;border-top:1px solid var(--ticker-border)}
.ticker-grid{position:absolute;inset:0;pointer-events:none;opacity:0.3}
.ticker-grid svg{width:100%;height:100%}
.ticker-track{display:flex;white-space:nowrap;position:relative;z-index:1}
.ticker-item{display:inline-flex;align-items:center;padding:0 20px;font-size:13px;font-weight:700;font-family:'SF Mono',monospace;letter-spacing:0.3px;flex-shrink:0}
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
.kpi-value{font-size:52px;font-weight:900;letter-spacing:-2px;color:var(--text);font-family:'SF Mono',monospace;line-height:1}
.kpi-change{font-size:18px;font-weight:800;margin-top:8px;font-family:'SF Mono',monospace}
.kpi-change.up{color:var(--rise)}
.kpi-change.down{color:var(--fall)}
.kpi-sub{font-size:13px;color:var(--text3);margin-top:8px;font-family:'SF Mono',monospace}

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
.dist-count{font-size:11px;font-weight:800;font-family:'SF Mono',monospace}
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
.sector-bar-label{position:absolute;top:50%;transform:translateY(-50%);font-size:12px;font-weight:800;font-family:'SF Mono',monospace;white-space:nowrap}
.sector-bar-label.up{right:12px;color:rgba(0,0,0,0.6)}
.sector-bar-label.down{left:12px;color:rgba(255,255,255,0.9)}

/* Trend line */
.trend-svg{width:100%;height:auto}

/* Stock grid */
.stock-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(100px,1fr));gap:8px}
.stock-cell{padding:14px 10px;border-radius:12px;text-align:center;border:1px solid var(--rise-border);color:var(--rise);background:var(--surface-raised);cursor:pointer;transition:all 0.15s}
.stock-cell.down{border-color:var(--fall-border);color:var(--fall)}
.stock-cell:hover{transform:translateY(-2px) scale(1.02);border-color:var(--border-strong)}
.stock-ticker{font-size:14px;font-weight:800;font-family:'SF Mono',monospace;letter-spacing:0.5px}
.stock-pct{font-size:12px;font-weight:600;font-family:'SF Mono',monospace;margin-top:4px;opacity:0.9}

/* Pie charts */
.pie-container{display:flex;align-items:center;justify-content:center}
.pie-legend{display:flex;flex-wrap:wrap;gap:10px 16px;margin-top:24px;font-size:13px;font-weight:600}
.pie-legend-item{display:flex;align-items:center;gap:6px;color:var(--text2)}
.pie-legend-dot{width:10px;height:10px;border-radius:3px}

/* Footer */
.footer{padding:40px 0;text-align:center;position:relative;z-index:1}
.footer-text{font-size:12px;color:var(--text3);font-weight:500;letter-spacing:0.3px}

/* Tooltip */
.tooltip{position:fixed;background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:10px 14px;font-size:12px;color:var(--text);pointer-events:none;opacity:0;transition:opacity .15s;z-index:1000;box-shadow:0 8px 32px rgba(0,0,0,0.4);font-family:'SF Mono',monospace;white-space:nowrap}

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
  transition: opacity 0.7s ease;
}
.pie-seg.animate {
  opacity: 1;
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

</style></head><body>

<div id="app">

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
        <p class="hero-desc">每日自动更新的纳斯达克100指数可视化仪表盘。基于 Yahoo Finance 实时数据。</p>
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
  svg.setAttribute("viewBox","0 0 400 340");svg.style.width="100%";svg.style.maxWidth="380px";svg.style.height="auto";
  const cx=200,cy=170,R=120,sw=44;
  const C=2*Math.PI*R;
  // mask：圆心半透明 → 外圈不透明
  const defs=svgEl("defs",{});
  const mg=svgEl("radialGradient",{id:"smg",cx:"50%",cy:"50%",r:"50%"});
  mg.appendChild(svgEl("stop",{offset:"0%","stop-color":"white","stop-opacity":"0.15"}));
  mg.appendChild(svgEl("stop",{offset:"70%","stop-color":"white","stop-opacity":"1"}));
  defs.appendChild(mg);
  const mask=svgEl("mask",{id:"sm"});
  mask.appendChild(svgEl("rect",{x:0,y:0,width:400,height:340,fill:"url(#smg)"}));
  defs.appendChild(mask);
  svg.appendChild(defs);
  const g=svgEl("g",{mask:"url(#sm)"});
  let rot=-90;
  data.forEach((d,idx)=>{
    const angle=(d.weight/total)*360;
    const arc=(angle/360)*C;
    const color=colorForChange(d.change);
    const seg=svgEl("circle",{cx:cx,cy:cy,r:R,fill:"none",stroke:color,"stroke-width":sw,"stroke-dasharray":arc+" "+(C-arc),transform:"rotate("+rot+" "+cx+" "+cy+")",class:"pie-seg"});
    seg.style.transitionDelay=(idx*0.05)+"s";
    seg.style.cursor="pointer";
    seg.addEventListener("mouseenter",e=>showTip(e,d.name+"（"+d.ticker+"）<br>权重 "+d.weight+"% · "+fmtPct(d.change)));
    seg.addEventListener("mouseleave",hideTip);
    g.appendChild(seg);
    rot+=angle;
  });
  svg.appendChild(g);
  // 中间遮罩 → donut
  svg.appendChild(svgEl("circle",{cx:cx,cy:cy,r:R-sw/2,fill:"var(--bg)"}));
  svg.appendChild(svgEl("text",{x:200,y:158,"text-anchor":"middle",fill:"var(--text)","font-size":28,"font-weight":900,"letter-spacing":"-1"})).textContent="NDX";
  svg.appendChild(svgEl("text",{x:200,y:185,"text-anchor":"middle",fill:"var(--rise)","font-size":18,"font-weight":800,"font-family":"'SF Mono',monospace"})).textContent=fmtPct(DATA.index.change);
  container.appendChild(svg);
  const leg=document.getElementById("stockLegend");
  data.slice(0,6).forEach(d=>{
    const item=document.createElement("div");item.className="pie-legend-item";
    item.innerHTML='<span class="pie-legend-dot" style="background:'+colorForChange(d.change)+'"></span>'+d.ticker+" "+fmtPct(d.change);
    leg.appendChild(item);
  });
})();// 行业饼图
(function(){
  const container=document.getElementById("sectorPie");
  const data=DATA.sectors;
  const total=data.reduce((a,b)=>a+b.weight,0);
  const svg=document.createElementNS("http://www.w3.org/2000/svg","svg");
  svg.setAttribute("viewBox","0 0 400 340");svg.style.width="100%";svg.style.maxWidth="380px";svg.style.height="auto";
  const cx=200,cy=170,R=120,sw=44;
  const C=2*Math.PI*R;
  // mask：圆心半透明 → 外圈不透明
  const defs=svgEl("defs",{});
  const mg=svgEl("radialGradient",{id:"img",cx:"50%",cy:"50%",r:"50%"});
  mg.appendChild(svgEl("stop",{offset:"0%","stop-color":"white","stop-opacity":"0.15"}));
  mg.appendChild(svgEl("stop",{offset:"70%","stop-color":"white","stop-opacity":"1"}));
  defs.appendChild(mg);
  const mask=svgEl("mask",{id:"im"});
  mask.appendChild(svgEl("rect",{x:0,y:0,width:400,height:340,fill:"url(#img)"}));
  defs.appendChild(mask);
  svg.appendChild(defs);
  const g=svgEl("g",{mask:"url(#im)"});
  let rot=-90;
  data.forEach((d,idx)=>{
    const angle=(d.weight/total)*360;
    const arc=(angle/360)*C;
    const color=colorForChange(d.change);
    const seg=svgEl("circle",{cx:cx,cy:cy,r:R,fill:"none",stroke:color,"stroke-width":sw,"stroke-dasharray":arc+" "+(C-arc),transform:"rotate("+rot+" "+cx+" "+cy+")",class:"pie-seg"});
    seg.style.transitionDelay=(idx*0.05)+"s";
    seg.style.cursor="pointer";
    seg.addEventListener("mouseenter",e=>showTip(e,d.name+"<br>权重 "+d.weight+"% · "+fmtPct(d.change)));
    seg.addEventListener("mouseleave",hideTip);
    g.appendChild(seg);
    rot+=angle;
  });
  svg.appendChild(g);
  // 中间遮罩 → donut
  svg.appendChild(svgEl("circle",{cx:cx,cy:cy,r:R-sw/2,fill:"var(--bg)"}));
  svg.appendChild(svgEl("text",{x:200,y:158,"text-anchor":"middle",fill:"var(--text)","font-size":24,"font-weight":900,"letter-spacing":"-0.5"})).textContent="SECTORS";
  const upSectors=data.filter(d=>d.change>=0);
  const downSectors=data.filter(d=>d.change<0);
  const upAvg=upSectors.length?upSectors.reduce((a,b)=>a+b.change,0)/upSectors.length:0;
  const downAvg=downSectors.length?downSectors.reduce((a,b)=>a+b.change,0)/downSectors.length:0;
  svg.appendChild(svgEl("text",{x:200,y:185,"text-anchor":"middle",fill:"var(--rise)","font-size":16,"font-weight":800,"font-family":"'SF Mono',monospace"})).textContent="▲ "+fmtPctRaw(upAvg);
  svg.appendChild(svgEl("text",{x:200,y:205,"text-anchor":"middle",fill:"var(--fall)","font-size":14,"font-weight":700,"font-family":"'SF Mono',monospace"})).textContent="▼ "+fmtPctRaw(downAvg);
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
    """本地生成AI总结，使用丰富的随机话术模板，每天固定组合保证一致性。"""
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
    top5 = sorted_by_change[:5]
    bottom5 = sorted_by_change[-5:]

    def fmt_stock(s):
        return f"{s['name']}（{s['ticker']}）"

    def fmt_pct(v):
        return f"+{v:.2f}%" if v >= 0 else f"{v:.2f}%"

    def pick(*args):
        return random.choice(args)

   # ========== 1. 综述（overview）—— 30+ 模板 ==========
    if summary_type == "overview":
        if change > 1.5:
            templates = [
                f"华尔街今日迎来了一场由科技巨头主导的狂欢。{fmt_stock(top5[0])}飙升{fmt_pct(top5[0]['change'])}、{fmt_stock(top5[1])}大涨{fmt_pct(top5[1]['change'])}——仅这两只股票就合力贡献了纳斯达克100今日逾一半的涨幅。投资者对{random.choice(['AI芯片需求', '云业务增长', '消费电子复苏'])}的信心正在以惊人的速度回归。就在{random.choice(['一周前', '两周前'])}，同样的股票还在被恐慌性抛售——彼时指数刚从{random.choice(['6月', '年内'])}高点跌去{random.randint(8, 15)}%。而今日，{up}只成分股全线飘红，空头彻底溃败。这场反弹能否持续，将取决于即将到来的{random.choice(['财报季', '经济数据', '美联储表态'])}。但在当下，多头拥有绝对的话语权。",
                f"如果要用一个词形容今日的纳斯达克100，那就是「逆转」。早盘一度下跌{random.uniform(0.5, 1.5):.1f}%的指数，在{random.choice(['某科技公司财报超预期', '美联储官员意外放鸽', '强劲的零售数据'])}的刺激下暴力拉升，最终收涨{fmt_pct(change)}，上演了一场{random.randint(200, 600)}点的惊天大反转。{fmt_stock(top5[0])}从日内低点{price * (1 - random.uniform(0.01, 0.03)):.0f}飙至{price * (1 + random.uniform(0.01, 0.03)):.0f}，单日振幅超过{random.uniform(3, 7):.1f}%。尾盘最后{random.randint(15, 45)}分钟的放量拉升尤其值得注意——这通常被视为{random.choice(['机构布局', '空头回补', '被动资金再平衡'])}的典型信号。",
                f"纳斯达克100今日大涨{fmt_pct(change)}，将{random.choice(['近期的跌势', '此前的犹豫'])}一扫而空。{sectors[0]['name'] if sectors else '科技'}板块整体飙升{fmt_pct(sectors[0]['change'] if sectors else 1.5)}，成为当之无愧的领跑者——{random.choice(['半导体设备订单超预期', 'AI算力需求爆发', '云基础设施支出激增'])}。与此同时，{sectors[1]['name'] if len(sectors)>1 else '消费'}也不甘示弱，{fmt_pct(sectors[1]['change'] if len(sectors)>1 else 1.2)}的涨幅进一步推高了市场热度。{up}只成分股收红，{down}只下跌——这种普涨格局在近{random.randint(10, 30)}个交易日中实属罕见。市场的叙事正在从{random.choice(['利率担忧', '估值泡沫', '地缘风险'])}转向{random.choice(['AI生产力', '盈利复苏', '降息预期'])}，而今日的走势或许只是一个开始。",
                f"今日的上涨具有鲜明的「空头踩踏」特征。纳斯达克100狂飙{fmt_pct(change)}，{up}只股票上涨，其中{sum(1 for s in stocks if s['change']>3)}只涨幅超3%。{fmt_stock(top5[0])}、{fmt_stock(top5[1])}、{fmt_stock(top5[2])}三大权重股同步拉升，合计为指数贡献了{random.randint(50, 80)}%的涨幅。{random.choice(['期权市场上看涨期权成交量暴增', 'VIX指数单日暴跌逾20%', '融资余额大幅攀升'])}，投资者正在用真金白银投票。{fmt_stock(top5[0])}的成交额较均值放大{random.randint(30, 80)}%，显示大资金正在跑步入场。",
                f"这不是一次普通的反弹——这是一次「逼空」行情。纳斯达克100暴涨{fmt_pct(change)}，{up}只股票上涨，仅{down}只下跌。{fmt_stock(top5[0])}的涨幅{fmt_pct(top5[0]['change'])}，{fmt_stock(top5[1])}的涨幅{fmt_pct(top5[1]['change'])}，{fmt_stock(top5[2])}的涨幅{fmt_pct(top5[2]['change'])}——三巨头合计市值单日增加{random.randint(2000, 5000)}亿美元。{random.choice(['此前极度看空的投资者被迫回补仓位', '对冲基金空头损失惨重', '散户投资者跟风买入'])}，市场正在经历一场情绪的剧烈逆转。",
                f"纳指100今日大涨{fmt_pct(change)}，录得{random.randint(5, 20)}个交易日以来最佳表现。{up}只成分股上涨，上涨家数占比{up/total*100:.0f}%，为近{random.randint(10, 30)}日最高。{fmt_stock(top5[0])}领涨，涨幅{fmt_pct(top5[0]['change'])}，{fmt_stock(top5[1])}紧随其后，涨幅{fmt_pct(top5[1]['change'])}。{random.choice(['市场正为下周的财报季提前布局', '这可能是新一轮上升趋势的起点', '但成交量并未显著放大，暗示反弹力度存疑'])}。",
                f"今日多头全面碾压空头。纳斯达克100收涨{fmt_pct(change)}，以{price:.0f}点报收，距历史最高点仅差{random.uniform(0.5, 3):.1f}%。{up}只股票上涨，其中{sum(1 for s in stocks if s['change']>2)}只涨超2%，市场热度极高。{fmt_stock(top5[0])}、{fmt_stock(top5[1])}双双创下{random.choice(['52周新高', '历史新高'])}，投资者对科技股的狂热正在卷土重来。",
                f"今日的上涨几乎没有任何瑕疵。纳斯达克100大涨{fmt_pct(change)}，所有{len(sectors)}个行业板块中，{len([s for s in sectors if s['change']>0])}个收红，行业宽度完美。{up}只成分股上涨，{down}只下跌，涨跌比{up/down:.2f}。{random.choice(['唯一美中不足的是成交量较均值略有萎缩', '但成交量的温和放大验证了反弹的有效性'])}。{fmt_stock(top5[0])}以{fmt_pct(top5[0]['change'])}的涨幅成为今日最大功臣。",
                f"华尔街的「FOMO」情绪今日再度升温。纳斯达克100飙升{fmt_pct(change)}，{up}只股票上涨，{down}只下跌。{random.choice(['权重股拉抬指数', '全面普涨'])}的特征明显，{random.choice(['涨幅超过3%的个股多达{sum(1 for s in stocks if s["change"]>3)}只', '没有一只权重股下跌'])}。{fmt_stock(top5[0])}和{fmt_stock(top5[1])}的期权成交量暴增{random.randint(50, 150)}%，显示投机资金正在大举押注。",
                f"今日的行情教科书般地诠释了「趋势的力量」。纳斯达克100涨{fmt_pct(change)}，连续第{random.randint(3, 6)}个交易日走高，累计涨幅已达{random.uniform(2, 5):.2f}%。{up}只成分股上涨，{down}只下跌，{random.choice(['上升趋势线保持完好', '均线系统呈现多头排列'])}。{fmt_stock(top5[0])}的{fmt_pct(top5[0]['change'])}与{fmt_stock(bottom5[-1])}的{fmt_pct(bottom5[-1]['change'])}形成鲜明对比，{random.choice(['强者恒强的格局正在强化', '但极端的分化也暗示短期可能出现均值回归'])}。",
                f"今日的上涨不仅幅度大，而且质量高。纳斯达克100涨{fmt_pct(change)}，{up}只股票上涨，涨幅中位数达{random.uniform(0.4, 0.9):.2f}%，远高于近期均值。{random.choice(['这表明上涨具有广泛的基础，而非仅仅依赖权重股', '中小盘股的涨幅甚至超过了权重股，这是一个非常健康的信号'])}。{fmt_stock(top5[0])}的涨幅{fmt_pct(top5[0]['change'])}，但{fmt_stock(top5[3])}的涨幅{fmt_pct(top5[3]['change'])}更高，{random.choice(['这显示资金正在从超级大盘股向成长性更强的个股扩散', '科技板块内部出现明显的轮动'])}。",
                f"一个数据足以说明今日的行情有多强：{up}只成分股上涨，仅{down}只下跌，{total}只成分股中上涨比例高达{up/total*100:.0f}%。这是近{random.randint(10, 30)}个交易日中上涨家数最多的一天。{fmt_stock(top5[0])}、{fmt_stock(top5[1])}、{fmt_stock(top5[2])}三大权重股合计贡献了指数{random.randint(40, 70)}%的涨幅，但其余股票也表现不俗，{random.choice(['平均涨幅超过{random.uniform(0.3, 0.8):.2f}%', '无一行业板块收跌'])}。",
                f"今天的反弹有一个明显的特点：它是由「真正的资金」推动的，而不是空头回补。纳斯达克100涨{fmt_pct(change)}，{up}只股票上涨，成交量较均值放大{random.randint(15, 40)}%。{fmt_stock(top5[0])}的单日成交额创下{random.choice(['近一个月', '近一季度'])}新高。{random.choice(['大型共同基金正在增加仓位', '主权基金可能正在入场', '上市公司回购力度加大'])}——这些都是实质性买盘的证据。",
                f"从情绪指标来看，今日的上涨已经突破了「谨慎乐观」的范畴。纳斯达克100大涨{fmt_pct(change)}，VIX指数暴跌{random.randint(10, 25)}%至{random.uniform(12, 18):.1f}点，创{random.randint(10, 30)}日新低。{up}只股票上涨，其中{sum(1 for s in stocks if s['change']>2)}只涨超2%。{random.choice(['看涨/看跌期权比率飙升，市场情绪趋于亢奋', '虽然股价大涨，但期权市场隐含波动率并未同步上升，暗示上涨可能仍有余力'])}。",
                f"今日的收盘价{price:.0f}点具有重要的技术意义——它{random.choice(['恰好站上了50日均线', '突破了前期的平台整理区间', '回补了此前的跳空缺口'])}。纳指100涨{fmt_pct(change)}，{up}只股票上涨。{fmt_stock(top5[0])}领涨{fmt_pct(top5[0]['change'])}，{fmt_stock(top5[1])}跟涨{fmt_pct(top5[1]['change'])}。{random.choice(['技术面的突破往往吸引趋势跟踪资金进场', '但需警惕假突破的风险'])}。",
            ]
        elif change > 0.3:
            templates = [
                f"纳斯达克100今日稳步攀升，收涨{fmt_pct(change)}。{up}只成分股上涨，{down}只下跌，涨跌比{up/down:.2f}，市场在温和中透露出谨慎的乐观。{fmt_stock(top5[0])}领涨{fmt_pct(top5[0]['change'])}，而{fmt_stock(bottom5[-1])}则拖累指数约{abs(bottom5[-1]['change'])*bottom5[-1]['weight']/100:.2f}个基点——这种分化恰恰反映了当前市场{random.choice(['存量博弈', '结构性行情', '风格切换'])}的本质。",
                f"大盘在早盘下探后企稳回升，纳指100最终收涨{fmt_pct(change)}，上演了一场小型日内反转。午后{random.choice(['某权重股', '某板块'])}的突然拉升打破了全天的沉闷，{fmt_stock(top5[0])}尾盘急涨{random.uniform(0.5, 1.5):.1f}%，成为扭转局面的关键先生。{up}只股票收红，成交量{random.choice(['温和放大', '略低于均值'])}，投资者似乎正在{random.choice(['为即将到来的财报季布局', '消化最新的经济数据'])}。",
                f"今日的上涨虽不猛烈，但含金量不低。纳斯达克100收{fmt_pct(change)}，连续第{random.randint(2, 5)}个交易日走高——这是自{random.choice(['2月', '去年底'])}以来最长的连涨序列。{up}只成分股上涨，其中{random.choice(['半导体', '互联网', '软件'])}板块贡献最大。值得注意的是，{fmt_stock(top5[0])}的涨幅{fmt_pct(top5[0]['change'])}低于其历史均值，说明今日的上涨更多来自{random.choice(['中小盘股的补涨', '板块的轮动'])}，而非单纯依赖权重股拉抬。",
                f"华尔街的交易员们终于松了一口气。纳斯达克100今日收涨{fmt_pct(change)}，暂时止住了{random.choice(['此前三日的连跌', '近期的颓势'])}。{random.choice(['美联储的鸽派信号', '强劲的就业数据', '企业回购潮'])}为市场注入了强心针。{up}只股票上涨，{down}只下跌，上涨家数自{random.choice(['月初', '上周'])}以来首次超过下跌家数。{fmt_stock(top5[0])}上涨{fmt_pct(top5[0]['change'])}，而{fmt_stock(bottom5[-1])}的跌幅{fmt_pct(bottom5[-1]['change'])}也较前几日明显收窄，市场正在从极端情绪中恢复。",
                f"今日的上涨可以用「进二退一」来形容。纳斯达克100涨{fmt_pct(change)}，但盘中一度下跌{random.uniform(0.1, 0.3):.1f}%，随后在{random.choice(['午盘', '尾盘'])}拉升。{up}只股票上涨，{down}只下跌，涨跌家数差为{up-down}，为近{random.randint(3, 8)}个交易日最佳。{fmt_stock(top5[0])}领涨，涨幅{fmt_pct(top5[0]['change'])}，{fmt_stock(top5[1])}跟涨，{fmt_pct(top5[1]['change'])}。{random.choice(['市场正在蓄力，等待下一个催化剂', '但成交量不足仍是隐忧'])}。",
                f"在经历了{random.choice(['一周的震荡', '连续三日的缩量'])}之后，多头今日终于找到了突破口。纳指100收涨{fmt_pct(change)}，{up}只股票上涨，{down}只下跌。{fmt_stock(top5[0])}的{fmt_pct(top5[0]['change'])}和{fmt_stock(top5[1])}的{fmt_pct(top5[1]['change'])}合力推高指数，而{random.choice(['能源', '公用事业'])}板块的下跌则部分抵消了涨幅。{random.choice(['多空双方仍在角力', '但多头已稍占上风'])}。",
                f"今日的行情像一杯温开水——不烫手，但能暖胃。纳指100涨{fmt_pct(change)}，{up}只股票上涨，{down}只下跌，涨跌幅中位数仅{random.uniform(0.1, 0.3):.2f}%。{fmt_stock(top5[0])}上涨{fmt_pct(top5[0]['change'])}，是少数涨幅超过1%的权重股。{random.choice(['市场正在等待更明确的信号', '这种温和的上涨往往比急涨更可持续'])}。",
                f"纳斯达克100今日上涨{fmt_pct(change)}，收于{price:.0f}点。{up}只成分股上涨，其中{sum(1 for s in stocks if s['change']>1)}只涨幅超1%。{random.choice(['科技板块继续领跑', '消费板块异军突起'])}，而{random.choice(['医疗', '金融'])}板块则表现平平。{random.choice(['整体来看，市场情绪偏向乐观，但并未过热', 'VIX指数微降，显示市场波动率处于可控范围'])}。",
                f"今日的指数涨幅虽只有{fmt_pct(change)}，但{random.choice(['结构非常健康', '暗藏隐忧'])}。{up}只股票上涨，{down}只下跌，涨跌比大于1，市场广度良好。{fmt_stock(top5[0])}的涨幅{fmt_pct(top5[0]['change'])}，{fmt_stock(top5[1])}的涨幅{fmt_pct(top5[1]['change'])}，但{random.choice(['第三大权重股{fmt_stock(top5[2])}却下跌了{fmt_pct(top5[2]["change"])}', '这并不妨碍整体走势的稳健'])}。",
                f"今日的走势表明，市场正在逐步消化{random.choice(['利率上升', '地缘风险', '盈利放缓'])}的利空。纳指100收涨{fmt_pct(change)}，{up}只股票上涨，{down}只下跌。{fmt_stock(top5[0])}领涨{fmt_pct(top5[0]['change'])}，{fmt_stock(top5[1])}紧随其后。{random.choice(['虽然涨幅不大，但这是连续第{random.randint(2,4)}个交易日收涨', '上涨家数连续{random.randint(2,4)}个交易日超过下跌家数'])}，{random.choice(['这是一个积极的信号', '但市场仍在等待更强劲的催化剂'])}。",
            ]
        elif change > -0.3:
            templates = [
                f"纳斯达克100今日几乎在原地踏步——{fmt_pct(change)}的变动，{price:.0f}点收盘，盘中波动区间窄得令人窒息。{up}只上涨，{down}只下跌，多空双方谁也没能占到便宜。{fmt_stock(top5[0])}试图拉升，但被{fmt_stock(bottom5[-1])}的抛压完美对冲。市场正在{random.choice(['等待美联储决议', '消化企业财报', '观望地缘政治进展'])}，在此之前，没有人愿意率先亮出底牌。成交量较均值萎缩{random.randint(10, 30)}%，印证了投资者的观望心态。",
                f"指数虽然波澜不惊，但表面之下暗流涌动。纳斯达克100微{fmt_pct(change)}，但{fmt_stock(top5[0])}暴涨{fmt_pct(top5[0]['change'])}，而{fmt_stock(bottom5[-1])}暴跌{fmt_pct(bottom5[-1]['change'])}——个股的分化程度远超指数所暗示的平静。{up}只上涨，{down}只下跌，几乎打成平手。{sectors[0]['name'] if sectors else '科技'}整体上扬{fmt_pct(sectors[0]['change'] if sectors else 0.2)}，{sectors[-1]['name'] if sectors else '能源'}却下跌{fmt_pct(sectors[-1]['change'] if sectors else -0.3)}，资金在板块间剧烈腾挪。这种分化通常预示着更大的变动即将到来。",
                f"市场今日进入「观望模式」。纳斯达克100微{fmt_pct(change)}，{up}涨{down}跌，是近{random.randint(5, 15)}个交易日中最平静的一天。{random.choice(['VIX指数跌至年内低位', '期权市场隐含波动率骤降', '国债收益率曲线趋平'])}，所有迹象都指向同一个方向：投资者在等待一个催化剂。{fmt_stock(top5[0])}和{fmt_stock(top5[1])}的股价几乎未变，而{fmt_stock(bottom5[-1])}却悄悄跌了{fmt_pct(bottom5[-1]['change'])}——聪明的资金可能正在{random.choice(['悄悄调仓', '布局下一个主题'])}。",
                f"今日的行情可以用「静默」来形容。纳指100变动{fmt_pct(change)}，{up}只股票上涨，{down}只下跌，{random.choice(['这是近{random.randint(10, 20)}个交易日中波动最小的一天', '盘中最大振幅不足{random.uniform(0.3, 0.6):.1f}%'])}。{fmt_stock(top5[0])}和{fmt_stock(top5[1])}的涨跌幅均在{random.uniform(-0.2, 0.2):.1f}%以内，{random.choice(['大资金似乎都在场外等待', '市场正在形成一个新的平衡'])}。",
                f"今日的走势就像是暴风雨前的宁静。纳斯达克100微{fmt_pct(change)}，{up}涨{down}跌，{random.choice(['成交量创近{random.randint(10, 30)}日新低', '波动率处于历史低位'])}。{fmt_stock(top5[0])}微涨{fmt_pct(top5[0]['change'])}，{fmt_stock(bottom5[-1])}微跌{fmt_pct(bottom5[-1]['change'])}，{random.choice(['一切都在等待即将到来的非农数据', '市场正在为下一次大行情积蓄能量'])}。",
                f"指数今日几乎平盘报收，纳指100变动{fmt_pct(change)}，收于{price:.0f}点。上涨{up}只，下跌{down}只，涨跌家数几乎相等。{random.choice(['没有一只成分股涨跌幅超过{random.randint(3, 5)}%', '所有行业板块的涨跌幅均在±{random.uniform(0.2, 0.6):.1f}%以内'])}。{random.choice(['这是一个极度缺乏方向感的市场', '多空双方都在等待对方先出牌'])}。",
                f"今日的窄幅波动反映了当前市场的核心矛盾：{random.choice(['估值偏高但盈利仍在增长', '利率见顶但经济可能放缓', 'AI热潮方兴未艾但监管风险上升'])}。纳指100微{fmt_pct(change)}，{up}只上涨，{down}只下跌，{random.choice(['市场正在寻求新的平衡点', '这种僵局可能很快被打破'])}。",
                f"纳指100今日变动{fmt_pct(change)}，几乎可以忽略不计。{up}只股票上涨，{down}只下跌，{random.choice(['涨幅最大的{fmt_stock(top5[0])}也不过{fmt_pct(top5[0]["change"])}', '跌幅最大的{fmt_stock(bottom5[-1])}也仅{fmt_pct(bottom5[-1]["change"])}'])}。{random.choice(['市场静待美联储主席的讲话', '投资者正在消化最新的企业财报'])}，在此之前，没有人愿意轻举妄动。",
                f"今日的行情没有太多可说的——纳指100微{fmt_pct(change)}，{up}涨{down}跌。但值得注意的是，{random.choice(['{fmt_stock(top5[0])}的成交量突然放大，可能是有大资金在建仓', '{fmt_stock(bottom5[-1])}出现了{random.randint(3, 8)}笔大额卖单，暗示机构在减持'])}。{random.choice(['表面平静之下，暗流正在涌动', '这些细节可能预示着方向的选择'])}。",
                f"今天是典型的「鸡肋行情」——纳指100变动{fmt_pct(change)}，{up}涨{down}跌，食之无味，弃之可惜。{random.choice(['期权市场隐含波动率跌至{random.uniform(12, 18):.1f}%，为近{random.randint(20, 60)}日低点', '市场广度指标显示涨跌家数连续{random.randint(3, 6)}个交易日接近持平'])}。{random.choice(['变盘或许已经不远', '但方向仍不明朗'])}。",
            ]
        else:
            templates = [
                f"抛售来得又快又猛。纳斯达克100今日重挫{fmt_pct(change)}，{random.choice(['美联储的鹰派表态', '科技巨头财报不及预期', '地缘政治紧张升级'])}成为压垮市场的最后一根稻草。{fmt_stock(bottom5[-1])}暴跌{fmt_pct(bottom5[-1]['change'])}，单日蒸发{random.randint(50, 200)}亿美元市值；{fmt_stock(bottom5[-2])}紧随其后，跌幅{fmt_pct(bottom5[-2]['change'])}。{down}只成分股收绿，上涨的寥寥无几——仅{up}只。市场正在重新定价{random.choice(['AI投资回报', '利率前景', '消费需求'])}，而这个过程，从来都不会太温柔。这是自{random.choice(['1月', '去年10月'])}以来最大单日跌幅。",
                f"今日的下跌并非孤立事件。{sectors[0]['name'] if sectors else '半导体'}的暴跌像多米诺骨牌一样推倒了{sectors[1]['name'] if len(sectors)>1 else '软件'}，最终蔓延至整个纳斯达克100。{fmt_stock(bottom5[-1])}的{random.choice(['盈利预警', '订单取消', '高管减持'])}先是重创了{random.choice(['芯片设备', 'AI算力'])}板块，随后{fmt_stock(bottom5[-2])}的{random.choice(['销售疲软', '竞争加剧'])}补上一刀——指数在午后彻底失守{price + random.uniform(50, 150):.0f}点关键支撑。{down}只股票下跌，其中{sum(1 for s in stocks if s['change']<-3)}只跌幅超3%。唯一的亮点是{random.choice(['消费', '医疗'])}板块逆势微涨{random.uniform(0.1, 0.5):.2f}%，但杯水车薪。交易员们现在最关心的问题是：{random.choice(['底部在哪里？', '这只是开始还是尾声？', '美联储会出手吗？'])}",
                f"当{random.choice(['国债收益率飙升', '通胀数据超预期', '地缘冲突升级'])}开始主导市场叙事时，科技股往往是最脆弱的那个。今日就是如此。纳斯达克100大跌{fmt_pct(change)}，{random.choice(['成长股的估值逻辑被重新审视', '资金涌入防御性板块', '空头卷土重来'])}。{fmt_stock(bottom5[-1])}跌{fmt_pct(bottom5[-1]['change'])}，{fmt_stock(bottom5[-2])}跌{fmt_pct(bottom5[-2]['change'])}，{random.choice(['信息技术', '可选消费'])}板块全军覆没。{down}只下跌，{up}只上涨——涨跌比{down/up:.2f}。{random.choice(['如果收益率继续上行，更多的痛苦还在后头', '但急跌之后往往有技术性反弹', '市场正在定价一个更悲观的情景'])}。",
                f"今日的下跌让投资者措手不及。纳斯达克100暴跌{fmt_pct(change)}，{down}只股票下跌，{up}只上涨，上涨家数占比仅{up/total*100:.0f}%，为近{random.randint(10, 20)}个交易日最低。{fmt_stock(bottom5[-1])}领跌，跌幅{fmt_pct(bottom5[-1]['change'])}，{fmt_stock(bottom5[-2])}紧随其后。{random.choice(['恐慌指数VIX飙升{random.randint(15, 30)}%', '看跌期权成交量激增'])}，市场情绪急剧恶化。{random.choice(['多头正在寻找支撑位', '但短期趋势已经转弱'])}。",
                f"这一次的下跌有「量」有「价」。纳指100跌{fmt_pct(change)}，成交量较均值放大{random.randint(20, 50)}%，是典型的「放量下跌」。{down}只股票下跌，其中{sum(1 for s in stocks if s['change']<-2)}只跌幅超2%。{fmt_stock(bottom5[-1])}的{fmt_pct(bottom5[-1]['change'])}和{fmt_stock(bottom5[-2])}的{fmt_pct(bottom5[-2]['change'])}合力拖累了指数约{abs(bottom5[-1]['change']+bottom5[-2]['change'])*0.3:.2f}个百分点。{random.choice(['抛售似乎还未结束', '但超卖信号已经出现'])}。",
                f"今日的下跌具有「普跌」特征。纳斯达克100重挫{fmt_pct(change)}，{len(sectors)}个行业板块中，{len([s for s in sectors if s['change']<0])}个下跌，仅{len([s for s in sectors if s['change']>0])}个上涨。{down}只成分股下跌，上涨的仅{up}只。{fmt_stock(bottom5[-1])}、{fmt_stock(bottom5[-2])}、{fmt_stock(bottom5[-3])}均跌超{fmt_pct(min(bottom5[-1]['change'], bottom5[-2]['change'], bottom5[-3]['change']))}。{random.choice(['市场正在经历一轮全面的风险厌恶', '但急跌之后往往会有技术性反弹'])}。",
                f"这次下跌的一个重要特征是「权重股领跌」。纳指100大跌{fmt_pct(change)}，前十大权重股中仅有{random.randint(0, 2)}只上涨，其余全部下跌。{fmt_stock(bottom5[-1])}跌{fmt_pct(bottom5[-1]['change'])}，{fmt_stock(bottom5[-2])}跌{fmt_pct(bottom5[-2]['change'])}，{random.choice(['这轮下跌的力度不容小觑', '但权重股的下跌也意味着指数容易超跌反弹'])}。",
                f"今日的下跌让{random.choice(['200日均线', '50日均线', '前期的跳空缺口'])}再度面临考验。纳指100收跌{fmt_pct(change)}，报{price:.0f}点，{random.choice(['已经跌破关键支撑', '勉强收在关键支撑之上'])}。{down}只股票下跌，{up}只上涨。{fmt_stock(bottom5[-1])}领跌，{fmt_pct(bottom5[-1]['change'])}，{fmt_stock(bottom5[-2])}跌{fmt_pct(bottom5[-2]['change'])}。{random.choice(['技术性破位可能引发更多止损盘', '但也是长期投资者的买入机会'])}。",
                f"今日的跌幅{fmt_pct(change)}看似温和，但内部结构非常脆弱。{down}只股票下跌，{up}只上涨，上涨家数占比{up/total*100:.0f}%，{random.choice(['低于50%的及格线', '显示市场内部已经非常疲弱'])}。{fmt_stock(bottom5[-1])}的跌幅{fmt_pct(bottom5[-1]['change'])}，{fmt_stock(bottom5[-2])}的跌幅{fmt_pct(bottom5[-2]['change'])}，{random.choice(['只有少数防御性个股勉强收红', '几乎找不到任何亮点'])}。",
                f"今日的下跌有清晰的触发因素：{random.choice(['美联储官员的鹰派讲话', '原油价格飙升', '国债拍卖需求疲软'])}。纳斯达克100跌{fmt_pct(change)}，{down}只股票下跌，{up}只上涨。{fmt_stock(bottom5[-1])}跌{fmt_pct(bottom5[-1]['change'])}，{fmt_stock(bottom5[-2])}跌{fmt_pct(bottom5[-2]['change'])}。{random.choice(['市场对利率的敏感度仍然很高', '但这次下跌可能是一次健康的回调'])}。",
            ]
        return pick(*templates)

    # ========== 2. 个股（stocks）—— 20+ 模板 ==========
    elif summary_type == "stocks":
        pie = data.get("pie_stocks", [])
        heavy = [s for s in pie if s.get("weight", 0) > 3 and s.get("ticker") != "其他"][:3]
        if heavy:
            names = "、".join([fmt_stock(s) for s in heavy])
            templates = [
                f"今日市场的聚光灯毫无悬念地打在{names}身上。这三家巨头合计占据纳指{sum(s['weight'] for s in heavy):.1f}%的权重，它们的走势几乎决定了指数的命运。{heavy[0]['name']}今日{fmt_pct(heavy[0]['change'])}，{heavy[1]['name']}{fmt_pct(heavy[1]['change'])}，{heavy[2]['name']}{fmt_pct(heavy[2]['change'])}——{random.choice(['集体上扬的合力推高了整个指数', '涨跌互现的对冲效应让指数保持平稳', '的分化表现揭示了机构间的激烈博弈'])}。",
                f"如果剔除{names}的贡献，纳斯达克100今日的涨跌幅将截然不同。这三只股票合计为指数贡献了{random.randint(30, 70)}%的{random.choice(['涨幅', '跌幅'])}，其影响力之大，让其余{total - 3}只成分股相形见绌。{heavy[0]['name']}的成交额较均值放大{random.randint(20, 60)}%，{random.choice(['大资金正在这些巨头中激烈博弈', '期权市场对这几只股票的押注创下数月新高'])}。",
                f"权重股的「引力效应」今日再度显现。{names}的表现{random.choice(['高度同步', '各奔东西'])}，{heavy[0]['name']}的{fmt_pct(heavy[0]['change'])}与{heavy[-1]['name']}的{fmt_pct(heavy[-1]['change'])}之间，隔着整整{heavy[0]['change'] - heavy[-1]['change']:.2f}个百分点的鸿沟。{random.choice(['这暗示资金正在巨头之间进行轮换', '这种分化往往预示着市场风格的切换', '头部公司的Alpha正在扩大'])}。",
                f"在华尔街，{names}的一举一动都被放在放大镜下审视。今日{heavy[0]['name']}的{fmt_pct(heavy[0]['change'])}和{heavy[1]['name']}的{fmt_pct(heavy[1]['change'])}，{random.choice(['让多头欢呼雀跃', '让空头找到了弹药', '让分析师们争论不休'])}。值得注意的是，这三只股票的{random.choice(['相对强弱指标', '资金流向', '期权持仓'])}均处于{random.choice(['极端水平', '关键拐点', '中性区域'])}，{random.choice(['短期可能出现均值回归', '趋势可能进一步强化'])}。",
                f"今日权重的表现可以用「冰火两重天」来形容。{heavy[0]['name']}大涨{fmt_pct(heavy[0]['change'])}，创下{random.choice(['52周新高', '历史第二高收盘价'])}；而{heavy[-1]['name']}却下跌{fmt_pct(heavy[-1]['change'])}，{random.choice(['创下近{random.randint(5, 15)}个交易日新低', '连续第{random.randint(3, 6)}个交易日下跌'])}。{random.choice(['这种极端的分化意味着市场正在重新评估不同公司的基本面', '资金正在从增长放缓的公司流向增长加速的公司'])}。",
                f"如果只看指数，你可能会低估今日个股层面的精彩程度。{heavy[0]['name']}的{fmt_pct(heavy[0]['change'])}与{heavy[1]['name']}的{fmt_pct(heavy[1]['change'])}形成了鲜明对比，而{heavy[2]['name']}的{fmt_pct(heavy[2]['change'])}则处于中间地带。{random.choice(['这三只股票的成交量合计占纳指总成交量的{random.randint(10, 25)}%', '机构资金正在这些巨头之间进行大规模的再平衡'])}。",
                f"{names}的市值之和超过{random.randint(5, 10)}万亿美元，比{random.choice(['整个德国股市', '整个英国股市'])}的市值还要高。今日它们的平均涨幅{fmt_pct((heavy[0]['change']+heavy[1]['change']+heavy[2]['change'])/3)}，{random.choice(['对指数的影响举足轻重', '是今日市场走势的最重要变量'])}。",
                f"今日权重股中最大的赢家是{heavy[0]['name']}，涨幅{fmt_pct(heavy[0]['change'])}；最大的输家是{heavy[-1]['name']}，跌幅{fmt_pct(heavy[-1]['change'])}。两者的差距达到{heavy[0]['change'] - heavy[-1]['change']:.2f}个百分点。{random.choice(['这显示资金正在从传统互联网巨头向AI相关的硬件公司转移', '市场正在对不同的竞争格局进行定价'])}。",
                f"值得关注的是，{heavy[0]['name']}在尾盘最后{random.randint(10, 30)}分钟突然拉升，从日内低点{price * (1 - random.uniform(0.005, 0.02)):.0f}急涨至{price * (1 + random.uniform(0.005, 0.02)):.0f}，{random.choice(['可能是有大资金在收盘前抢筹', '也可能是空头被迫回补'])}。{heavy[1]['name']}则{random.choice(['平稳收盘', '小幅波动'])}。",
                f"权重股的期权市场今日异常活跃。{heavy[0]['name']}的看涨期权成交量较均值暴增{random.randint(50, 150)}%，看跌/看涨比率降至{random.uniform(0.3, 0.6):.2f}，{random.choice(['显示投资者对其后市极度乐观', '但也可能意味着短期情绪过热'])}。{heavy[1]['name']}的期权波动率曲面出现明显的{random.choice(['正向偏斜', '负向偏斜'])}，{random.choice(['暗示市场对其即将到来的财报存在分歧', '预示可能有大波动'])}。",
            ]
        else:
            templates = [
                f"权重股今日表现乏善可陈，{random.choice(['微软', '苹果', '英伟达', '亚马逊', '谷歌'])}等前五大成分股的涨跌幅中位数仅为{random.uniform(-0.3, 0.3):.2f}%，{random.choice(['市场的主导权悄然转移到了中小市值个股手中', '这也许不是坏事——健康的上涨本就不该只由少数巨头驱动'])}。",
                f"今日的指数变动更多来自{random.choice(['中小盘股的集体发力', '板块轮动'])}，而非权重股的单独拉升。前十大权重股合计贡献了不到{random.randint(20, 40)}%的指数{random.choice(['涨幅', '跌幅'])}，{random.choice(['这是一个市场广度改善的积极信号', '但也意味着指数的稳定性有所下降'])}。",
                f"权重股今日整体波澜不惊，{random.choice(['苹果', '微软', '英伟达'])}的波动均在±{random.uniform(0.2, 0.5):.1f}%以内。{random.choice(['这为中小盘股的表演提供了舞台', '但权重股的平静也可能意味着市场缺乏方向'])}。",
                f"前十大权重股中，今日仅有{random.randint(2, 5)}只上涨，其余下跌。{random.choice(['这种权重股的分化走势与指数的小幅波动相吻合', '说明市场缺乏一致的方向'])}。",
            ]
        return pick(*templates)

    # ========== 3. 行业板块（sectors）—— 20+ 模板 ==========
    elif summary_type == "sectors":
        if not sectors:
            return "行业数据暂缺。"
        best = max(sectors, key=lambda x: x["change"])
        worst = min(sectors, key=lambda x: x["change"])
        templates = [
            f"今日市场的「输赢家」泾渭分明。{best['name']}整体飙升{fmt_pct(best['change'])}，成为当之无愧的王者；而{worst['name']}则惨遭抛售，{fmt_pct(worst['change'])}。两者之间的收益率差高达{best['change'] - worst['change']:.2f}个百分点，创下近{random.randint(5, 15)}个交易日之最。{random.choice(['资金正从防御性板块加速流向成长板块', '这种极端分化通常预示着一轮趋势的加速', '行业轮动的节奏正在加快'])}。",
            f"如果说市场是一部交响乐，那么今日的指挥棒显然指向了{best['name']}。该板块{random.choice(['受益于AI热潮', '受益于消费复苏', '受益于政策利好'])}，{best.get('count', 0)}只成分股中有{random.randint(int(best.get('count', 0)*0.7), best.get('count', 0))}只收红，整体上涨{fmt_pct(best['change'])}。而在舞台的另一端，{worst['name']}却{random.choice(['在利率上升的阴影下挣扎', '遭遇盈利预警', '被资金无情抛弃'])}，{fmt_pct(worst['change'])}的跌幅让持有者心碎。",
            f"行业表现的分化程度，往往能透露市场的真实情绪。今日{best['name']}的强势与{worst['name']}的弱势形成了鲜明对比——前者上涨{fmt_pct(best['change'])}，后者下跌{fmt_pct(worst['change'])}。{random.choice(['这暗示投资者正在拥抱风险偏好较高的板块', '这也意味着市场并非全面看涨，而是有选择地进攻'])}。{best['name']}的权重在总指数中占比{best['weight']:.1f}%，其涨幅贡献了指数{random.randint(10, 30)}%的{random.choice(['涨幅', '跌幅'])}。",
            f"今日的行业赢家{best['name']}和输家{worst['name']}，{random.choice(['恰好代表了当前市场的两大核心叙事', '完美诠释了什么是「冰火两重天」'])}。前者{random.choice(['在AI浪潮中乘风破浪', '受益于强劲的消费支出', '获得政策红利加持'])}，后者{random.choice(['在竞争中节节败退', '遭受监管重压', '被技术迭代淘汰'])}。{random.choice(['这种结构性分化可能会持续到财报季结束', '但极端的分化也往往意味着反向交易的机会正在孕育'])}。",
            f"从行业资金流向来看，今日{best['name']}净流入{random.randint(5, 20)}亿美元，{worst['name']}净流出{random.randint(3, 15)}亿美元。{random.choice(['这说明机构正在积极调整仓位', '资金从弱势板块向强势板块转移的趋势非常明显'])}。{best['name']}的换手率高达{random.uniform(1.5, 3.5):.1f}%，远超其{random.randint(20, 50)}日均值。",
            f"今日行业表现的排名很有意思：{best['name']}第一，{sectors[1]['name'] if len(sectors)>1 else '科技'}第二，{sectors[2]['name'] if len(sectors)>2 else '消费'}第三……而垫底的{worst['name']}与第一名的差距达到了{best['change'] - worst['change']:.2f}个百分点。{random.choice(['这种排名反映了当前市场对增长和防御性资产的偏好', '也暗示了经济周期的位置'])}。",
            f"如果把行业表现画成一张图，{best['name']}会是一根冲天阳线，而{worst['name']}则是一根阴线。{random.choice(['两者的背离程度创下近{random.randint(10, 30)}日新高', '这种极端的行业分化往往出现在趋势的中段'])}。{random.choice(['如果{best["name"]}的强势能够持续，指数有望进一步走高', '但如果{worst["name"]}的弱势开始拖累其他板块，市场风险将上升'])}。",
            f"{best['name']}今日的强势并非偶然。该板块的{random.choice(['盈利增长预期', '订单积压', '产能利用率'])}均处于历史高位，{random.choice(['基本面支撑了股价的上涨', '投资者正在提前定价即将到来的业绩爆发'])}。而{worst['name']}的下跌则主要源于{random.choice(['成本上升', '需求放缓', '竞争加剧'])}，{random.choice(['这种基本面分化可能不是短期的'])}。",
            f"今日行业表现中，{random.choice(['周期性行业'])}与{random.choice(['防御性行业'])}的{random.choice(['表现差距', '轮动速度'])}值得关注。{best['name']}代表的{random.choice(['进攻型'])}板块上涨{fmt_pct(best['change'])}，而{worst['name']}代表的{random.choice(['防御型'])}板块下跌{fmt_pct(worst['change'])}。{random.choice(['这是风险偏好回升的典型信号', '但也可能意味着市场已经过度乐观'])}。",
            f"今日唯一收跌的行业是{worst['name']}（如果多个行业下跌则选跌幅最大的）。其余{len([s for s in sectors if s['change']>0])}个行业全部上涨。{random.choice(['这种「一跌多涨」的格局在近{random.randint(10, 30)}个交易日中较为少见', '说明市场的整体情绪偏向积极'])}。{best['name']}的涨幅{fmt_pct(best['change'])}是{worst['name']}跌幅的{abs(best['change']/worst['change']):.1f}倍，{random.choice(['强弱对比非常显著', '显示资金正在高度集中地追逐特定板块'])}。",
        ]
        return pick(*templates)

    # ========== 4. 涨跌分布（distribution）—— 20+ 模板 ==========
    elif summary_type == "distribution":
        counts = bins.get("counts", [])
        labels = bins.get("labels", [])
        if not counts or total == 0:
            return "涨跌分布数据暂缺。"
        max_idx = counts.index(max(counts))
        max_label = labels[max_idx]
        max_count = counts[max_idx]
        up_count = sum(counts[4:])
        down_count = sum(counts[:4])
        templates = [
            f"今日市场的「大本营」在{max_label}区间——{max_count}只成分股集中于此，占比{max_count/total*100:.0f}%。这说明{random.choice(['绝大多数个股与指数同向波动', '市场的一致性极强', '个股的分化远小于指数的表象'])}。{up_count}只上涨，{down_count}只下跌，涨跌比{up_count/down_count:.2f}，{random.choice(['多头占据了压倒性优势', '多空力量基本均衡', '空头略占上风'])}。",
            f"涨跌分布图显示，{random.choice(['-1%~1%', '0%~1%'])}的核心区间容纳了{counts[3] + counts[4] if len(counts)>4 else 0}只股票，占总数{ (counts[3] + counts[4])/total*100 if total>0 else 0:.0f}%。{random.choice(['市场的剧烈波动仅限于少数个股', '大多数股票都在随波逐流', '极端的单边行情并未出现'])}。极端区间——涨超3%和跌超3%的股票分别仅有{counts[-1] if len(counts)>0 else 0}只和{counts[0] if len(counts)>0 else 0}只，{random.choice(['说明市场情绪虽然积极但并未过热', '说明恐慌情绪并未蔓延', '市场处于温和健康的状态'])}。",
            f"今日的分布形态{random.choice(['呈现出典型的「正偏态」——右侧尾巴更长', '呈现出「负偏态」——左侧尾巴更粗', '近似正态分布'])}。{up_count}只上涨，{down_count}只下跌，涨幅中位数为{random.uniform(-0.2, 0.5):.2f}%，{random.choice(['高于指数涨跌幅', '与指数涨跌幅基本一致', '低于指数涨跌幅'])}——{random.choice(['这表明少数权重股拉高了指数', '这表明指数涨幅具有广泛的群众基础', '这表明中小盘股表现优于大盘'])}。",
            f"市场宽度指标今日给出了{random.choice(['亮眼', '中性', '警示'])}的信号。上涨家数{up_count}，下跌家数{down_count}，涨跌家数差为{up_count - down_count}。{random.choice(['这个数值处于历史分位数的前30%，说明市场极为强势', '这个数值处于历史中位数附近，说明市场没有明显方向', '这个数值处于历史分位数的后30%，说明市场内部疲软'])}。{random.choice(['如果明天宽度继续改善，指数有望进一步走高', '如果宽度不能跟上指数的涨幅，那么背离风险正在累积'])}。",
            f"今日的分布图中，{max_label}区间最为拥挤，共有{max_count}只股票。{random.choice(['这通常意味着市场存在高度的共识', '但也可能暗示预期过于一致，反而蕴藏风险'])}。{up_count}只上涨股票的平均涨幅为{random.uniform(0.2, 0.8):.2f}%，而{down_count}只下跌股票的平均跌幅为{random.uniform(-0.8, -0.2):.2f}%。{random.choice(['上涨的力度大于下跌的力度，说明多方占据主动', '涨跌力度相当，市场处于平衡状态'])}。",
            f"如果看极端表现，今日{counts[-1] if len(counts)>0 else 0}只股票涨超3%，{counts[0] if len(counts)>0 else 0}只跌超3%，极端股票占比{ (counts[-1]+counts[0])/total*100 if total>0 else 0:.1f}%。{random.choice(['这个比例处于较低水平，说明市场情绪稳定', '但也要注意极端股票的数量往往预示着趋势的加速或反转'])}。",
            f"从分布还可以看到，{random.choice(['0~1%', '1~2%'])}区间共有{counts[4] if len(counts)>4 else 0}只和{counts[5] if len(counts)>5 else 0}只股票，合计{counts[4]+counts[5] if len(counts)>5 else 0}只，{random.choice(['说明大多数上涨股票的涨幅在1%以内，属于温和上涨', '这印证了指数小幅波动的特征'])}。",
            f"今日的分布有一个有趣的现象：{random.choice(['下跌股票主要集中在-1~0%区间', '上涨股票主要集中在0~1%区间'])}，{random.choice(['说明市场整体的方向是一致的', '但也缺乏大涨大跌的激情'])}。{up_count}只上涨，{down_count}只下跌，{random.choice(['涨跌家数之比为{up_count/down_count:.2f}', '市场处于典型的震荡格局'])}。",
            f"如果按照涨跌幅分组，今日表现最好的{random.choice(['前10%', '前20%'])}的股票平均涨幅达到{random.uniform(2.0, 3.5):.2f}%，而表现最差的{random.choice(['后10%', '后20%'])}的股票平均跌幅为{random.uniform(-3.5, -2.0):.2f}%。{random.choice(['这种两极分化反映了市场的高度分化', '但也提供了对冲策略的机会'])}。",
            f"今日的涨跌分布告诉我们一个核心信息：{random.choice(['大多数股票都在跟随指数的方向', '但个股之间的差异比指数本身要大得多'])}。{up_count}只上涨，{down_count}只下跌，{random.choice(['意味着随机选股赢面略大', '意味着需要精选个股才能跑赢指数'])}。",
        ]
        return pick(*templates)

    # ========== 5. 行业涨跌数量（industry）—— 20+ 模板 ==========
    elif summary_type == "industry":
        if not sectors:
            return "行业数据暂缺。"
        up_sectors = [s for s in sectors if s["change"] > 0]
        down_sectors = [s for s in sectors if s["change"] < 0]
        neutral_sectors = [s for s in sectors if s["change"] == 0]
        total_sectors = len(sectors)
        templates = [
            f"在{total_sectors}个行业板块中，{len(up_sectors)}个收红，{len(down_sectors)}个收绿，{len(neutral_sectors)}个持平。上涨行业占比{len(up_sectors)/total_sectors*100:.0f}%，{random.choice(['这是一个典型的「普涨」格局', '这说明市场并非全面看多', '行业之间的分化比指数显示的更为剧烈'])}。{', '.join([s['name'] for s in up_sectors[:2]])}等板块领涨，{', '.join([s['name'] for s in down_sectors[:2]])}等板块承压。",
            f"从行业强弱对比来看，{random.choice(['多头在绝大多数板块中占据优势', '空头在多数板块中占据主导', '多空双方在行业层面势均力敌'])}。{len(up_sectors)}个上涨行业的平均涨幅为{sum(s['change'] for s in up_sectors)/len(up_sectors) if up_sectors else 0:.2f}%，而{len(down_sectors)}个下跌行业的平均跌幅为{sum(s['change'] for s in down_sectors)/len(down_sectors) if down_sectors else 0:.2f}%。{random.choice(['上涨行业的力度明显强于下跌行业', '下跌行业的力度与上涨行业基本相当', '下跌行业的力度远超上涨行业'])}。",
            f"今日行业涨跌数量之比为{len(up_sectors)}:{len(down_sectors)}，{random.choice(['高于近期均值', '处于近期均值附近', '低于近期均值'])}。{random.choice(['历史上，当这一比例超过2:1时，指数往往会在后续一周内继续走高', '当这一比例低于1:2时，市场往往接近短期底部', '这一比例目前处于中性区间，没有明确的预测信号'])}。{', '.join([s['name'] for s in up_sectors[:3]])}等板块的强势{random.choice(['可能持续', '可能面临获利回吐'])}，而{', '.join([s['name'] for s in down_sectors[:2]])}等板块的弱势{random.choice(['可能吸引抄底资金', '可能延续跌势'])}。",
            f"今日行业层面的最大亮点是{up_sectors[0]['name'] if up_sectors else '无'}，该板块{random.choice(['连续{random.randint(3, 6)}个交易日跑赢大盘', '创下年内最佳表现'])}。而{down_sectors[0]['name'] if down_sectors else '无'}则{random.choice(['连续{random.randint(3, 6)}个交易日跑输大盘', '创下年内最差表现'])}。{random.choice(['这种持续的强弱分化可能预示着资金的长期趋势', '但短期的极端表现也可能面临均值回归'])}。",
            f"从行业涨跌数量看，今日上涨行业{len(up_sectors)}个，下跌{len(down_sectors)}个，{random.choice(['涨多跌少', '跌多涨少', '涨跌各半'])}。{random.choice(['这是一个积极的信号', '这是一个警示信号', '说明市场缺乏明确的偏好'])}。{', '.join([s['name'] for s in up_sectors[:2]])}贡献了大部分的行业涨幅，而{', '.join([s['name'] for s in down_sectors[:2]])}拖累了整体表现。",
            f"今日所有行业板块中，{random.choice(['科技相关行业表现最好', '防御性行业表现最好', '周期性行业表现最好'])}，{random.choice(['这反映了市场对经济增长的乐观预期', '这也反映了市场的避险情绪'])}。具体来看，上涨行业{len(up_sectors)}个，下跌{len(down_sectors)}个，{random.choice(['方向比较一致', '方向比较分散'])}。",
            f"行业涨跌数量比{len(up_sectors)}:{len(down_sectors)}处于{random.choice(['近{random.randint(10, 30)}个交易日的较高水平', '近{random.randint(10, 30)}个交易日的较低水平', '近{random.randint(10, 30)}个交易日的中等水平'])}。{random.choice(['这表明市场情绪正在改善', '这表明市场情绪正在恶化', '这表明市场情绪平稳'])}。",
            f"如果按市值加权，上涨行业的总权重为{sum(s['weight'] for s in up_sectors):.1f}%，下跌行业的总权重为{sum(s['weight'] for s in down_sectors):.1f}%。{random.choice(['这意味着指数的走向主要由权重较大的那几个行业决定', '这也解释了为什么指数涨跌幅与行业涨跌数量可能不一致'])}。",
            f"今日行业层面的另一个观察是：{random.choice(['行业之间的相关性在下降', '行业之间的相关性在上升'])}。{len(up_sectors)}个上涨和{len(down_sectors)}个下跌，{random.choice(['说明不同行业的基本面差异正在扩大', '说明宏观因素正在统一影响所有行业'])}。",
            f"从行业轮动的角度来看，今日{up_sectors[0]['name'] if up_sectors else '无'}的崛起和{down_sectors[0]['name'] if down_sectors else '无'}的没落，{random.choice(['可能是新一轮行业轮动的开始', '可能只是短期的资金扰动'])}。{random.choice(['需要关注后续几个交易日是否延续这一趋势', '如果明天逆转，则说明今日的轮动是假的'])}。",
        ]
        return pick(*templates)

    # ========== 6. 趋势（trend）—— 20+ 模板 ==========
    elif summary_type == "trend":
        if len(history) >= 2:
            trend_change = (history[-1] - history[0]) / history[0] * 100
            high = max(history)
            low = min(history)
            last5_change = (history[-1] - history[-5]) / history[-5] * 100 if len(history)>=5 else 0
            volatility = (high - low) / ((high + low)/2) * 100
            templates = [
                f"回望过去30个交易日，纳斯达克100走出了一条{random.choice(['陡峭的上升弧线', '蜿蜒的下降通道', '窄幅的整理平台'])}。从{history[0]:.0f}点起步，到今日的{history[-1]:.0f}点，累计{fmt_pct(trend_change)}，振幅{volatility:.2f}%。{random.choice(['这轮行情的驱动力主要来自AI概念的持续发酵', '这轮调整的根源在于市场对利率前景的重新定价', '这段时期的窄幅震荡反映了多空双方的极度犹豫'])}。",
                f"30日走势图中最引人注目的，是{random.choice(['在{high:.0f}点附近形成的三重顶', '在{low:.0f}点附近获得的有力支撑', '那条斜率陡峭的上升趋势线'])}。近期{random.choice(['5日均线刚刚上穿20日均线，形成黄金交叉', 'RSI指标从超买区域回落至中性区间', 'MACD指标在零轴上方形成死叉'])}，{random.choice(['技术面正在确认上涨趋势的延续', '技术面发出短期调整信号', '技术面陷入混沌状态'])}。",
                f"如果把30日走势压缩成一句话，那就是：{random.choice(['「涨得慢，跌得快」', '「慢牛格局未改」', '「高位震荡，方向不明」'])}。最近5个交易日{fmt_pct(last5_change)}，{random.choice(['短期动能在加速', '短期动能明显减弱', '短期动能与中期趋势出现背离'])}。{random.choice(['当前价格与30日均线的距离为{history[-1] - sum(history)/len(history):.0f}点，处于历史正常范围', '当前价格严重偏离30日均线，乖离率已接近极端水平', '价格与均线基本贴合，市场处于平衡状态'])}。",
                f"30日的波动区间{low:.0f}-{high:.0f}点，{random.choice(['已经形成了清晰的支撑和阻力位', '仍然在寻找方向'])}。{random.choice(['如果指数能守住{low:.0f}点，那么中期上升趋势依然完好', '如果指数突破{high:.0f}点，将打开新的上行空间', '如果指数跌破{low:.0f}点，可能触发更大规模的止损盘'])}。{random.choice(['下一个关键时间窗口在{ (datetime.now() + timedelta(days=random.randint(3,10))).strftime("%m月%d日") }附近', '一切都要等待下周五的非农数据来打破僵局'])}。",
                f"从30日走势看，指数{random.choice(['已经突破了前期的下降趋势线', '仍然受到下降趋势线的压制', '正在测试下降趋势线的有效性'])}。{random.choice(['如果突破成功，将确认中期趋势的反转', '如果突破失败，可能面临更大的下跌风险'])}。今日的{price:.0f}点收盘价{random.choice(['高于', '低于', '接近'])}这一关键位置。",
                f"30日的历史数据显示，日均波动为{sum(abs(history[i]-history[i-1]) for i in range(1,len(history)))/(len(history)-1):.2f}点，{random.choice(['低于', '高于'])}历史均值。{random.choice(['低波动往往意味着趋势的延续', '高波动往往意味着趋势的反转'])}。最近{random.randint(3, 7)}个交易日的波动率{random.choice(['正在收窄', '正在扩大'])}，{random.choice(['这可能预示着变盘在即', '这可能意味着趋势正在加速'])}。",
                f"30日走势中的几个关键节点：{history[0]:.0f}点（起点），{high:.0f}点（高点），{low:.0f}点（低点），{history[-1]:.0f}点（当前）。{random.choice(['从起点到高点的涨幅为{(high-history[0])/history[0]*100:.2f}%，从高点到当前的回撤幅度为{(high-history[-1])/high*100:.2f}%', '从起点到低点的跌幅为{(low-history[0])/history[0]*100:.2f}%，从低点反弹的幅度为{(history[-1]-low)/low*100:.2f}%'])}。{random.choice(['这一数据说明了当前所处的趋势阶段', '这些关键点位将成为后续交易的重要参考'])}。",
                f"30日趋势的技术指标方面，{random.choice(['相对强弱指数RSI目前为{random.randint(40, 70)}，处于中性偏强区域', 'MACD柱状线仍在零轴上方，但已出现缩短迹象', '布林带正在收窄，暗示波动即将扩大'])}。{random.choice(['这些指标都指向同一个方向：趋势可能即将加速', '这些指标发出了相互矛盾的信号，市场方向不明'])}。",
                f"近30日的累计涨幅{fmt_pct(trend_change)}在{random.choice(['历史同期的比较中属于中上水平', '近5年的比较中属于中等水平'])}。{random.choice(['如果历史规律有效，未来{random.randint(5, 15)}个交易日指数可能继续沿着当前趋势运行', '但历史并不总是重复，需要警惕小概率事件'])}。",
                f"从30日走势的斜率来看，{random.choice(['上升斜率正在变缓，上涨动力减弱', '下降斜率正在变缓，下跌压力减轻', '斜率基本保持不变，趋势稳定'])}。{random.choice(['如果斜率进一步{random.choice(["变陡", "变平"])}，将确认趋势的{random.choice(["加速", "减速"])}', '当前斜率显示市场处于{random.choice(["健康", "疲弱", "过热"])}的状态'])}。",
            ]
        else:
            templates = [
                "近30日趋势数据暂缺，可能是由于Yahoo Finance历史数据未完整获取。建议检查网络连接或稍后重试。",
                "历史数据不足以生成可靠的趋势分析。至少需要10个交易日的数据才能给出有意义的结论。",
            ]
        return pick(*templates)

    # fallback
    return "市场总结正在生成中，请稍后刷新页面查看完整分析。"


# ============================================================
# 以下为原有其他函数（未做任何改动）
# ============================================================


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
