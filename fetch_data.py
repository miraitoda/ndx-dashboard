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

def generate_summary(
    index_change,
    advancers,
    decliners,
    unchanged,
    total_stocks,
    top_gainers=None,
    top_losers=None,
    sector_data=None,
    distribution_data=None,
    industry_data=None,
    trend_data=None,
):
    """
    中文财经编辑式市场总结引擎。

    设计目标：
    1. 不再只是把数字塞进固定句子；
    2. 先识别市场状态，再选择叙事；
    3. 根据市场广度、权重股、行业轮动、涨跌分布、30日趋势形成不同评论；
    4. 输出六个维度：总览、个股、行业、分布、行业广度、趋势；
    5. 保持旧版调用方式兼容：只传前四个参数也可以运行。
    """

    import random
    from math import isfinite

    def _num(x, default=0.0):
        try:
            v = float(x)
            return v if isfinite(v) else default
        except Exception:
            return default

    def _pct(x):
        return f"{_num(x):+.2f}%"

    def _name(item, default=""):
        if isinstance(item, dict):
            for k in ("name", "symbol", "ticker", "code", "sector", "industry"):
                if item.get(k):
                    return str(item[k])
        elif isinstance(item, (list, tuple)) and item:
            return str(item[0])
        elif item:
            return str(item)
        return default

    def _change(item, default=0.0):
        if isinstance(item, dict):
            for k in ("change", "pct_change", "change_pct", "return", "pct"):
                if k in item:
                    return _num(item[k], default)
        elif isinstance(item, (list, tuple)) and len(item) > 1:
            return _num(item[1], default)
        return default

    def _weight(item, default=0.0):
        if isinstance(item, dict):
            for k in ("weight", "index_weight", "weight_pct"):
                if k in item:
                    return _num(item[k], default)
        elif isinstance(item, (list, tuple)) and len(item) > 2:
            return _num(item[2], default)
        return default

    def _items(data):
        if data is None:
            return []
        if isinstance(data, dict):
            # 常见结构：{"data": [...]} / {"items": [...]} / {"sectors": [...]}
            for k in ("data", "items", "sectors", "industries", "rows"):
                if isinstance(data.get(k), (list, tuple)):
                    return list(data[k])
            return list(data.values()) if data else []
        if isinstance(data, (list, tuple)):
            return list(data)
        return []

    def _first_name(data, reverse=False):
        arr = _items(data)
        if not arr:
            return ""
        arr = sorted(arr, key=_change, reverse=reverse)
        return _name(arr[0])

    def _first_change(data, reverse=False):
        arr = _items(data)
        if not arr:
            return 0.0
        arr = sorted(arr, key=_change, reverse=reverse)
        return _change(arr[0])

    def _top_weight_names(data, n=3):
        arr = sorted(_items(data), key=_weight, reverse=True)
        return [_name(x) for x in arr[:n] if _name(x)]

    # ---------- 基础数据 ----------
    chg = _num(index_change)
    adv = int(_num(advancers))
    dec = int(_num(decliners))
    unc = int(_num(unchanged))
    total = max(int(_num(total_stocks)), adv + dec + unc, 1)

    adv_ratio = adv / total * 100
    dec_ratio = dec / total * 100
    breadth = adv - dec
    breadth_ratio = breadth / total * 100

    gainers = sorted(_items(top_gainers), key=_change, reverse=True)
    losers = sorted(_items(top_losers), key=_change)
    sectors = _items(sector_data)
    industries = _items(industry_data)

    # ---------- 分布数据 ----------
    dist = distribution_data if isinstance(distribution_data, dict) else {}
    bins = dist.get("bins") or dist.get("distribution") or dist.get("ranges") or []
    dominant_bin = ""
    dominant_count = 0
    if isinstance(bins, dict):
        for k, v in bins.items():
            c = int(_num(v))
            if c > dominant_count:
                dominant_bin, dominant_count = str(k), c
    elif isinstance(bins, (list, tuple)):
        for x in bins:
            label = _name(x)
            c = _change(x, 0)
            if isinstance(x, dict):
                c = _num(x.get("count", x.get("value", c)))
            elif isinstance(x, (list, tuple)) and len(x) > 1:
                c = _num(x[1])
            if c > dominant_count:
                dominant_bin, dominant_count = label, int(c)

    # ---------- 趋势数据 ----------
    trend = trend_data if isinstance(trend_data, dict) else {}
    trend_return = _num(
        trend.get("return_30d", trend.get("change_30d", trend.get("monthly_change", 0)))
    )
    distance_high = _num(
        trend.get("distance_high", trend.get("from_high", trend.get("high_distance", 0)))
    )
    distance_low = _num(
        trend.get("distance_low", trend.get("from_low", trend.get("low_distance", 0)))
    )

    # ---------- 状态识别 ----------
    if chg >= 2.0:
        market_state = "强势上攻"
    elif chg >= 0.8:
        market_state = "明显走强"
    elif chg >= 0.2:
        market_state = "温和走高"
    elif chg > -0.2:
        market_state = "窄幅整理"
    elif chg > -0.8:
        market_state = "温和走弱"
    elif chg > -2.0:
        market_state = "明显回落"
    else:
        market_state = "显著承压"

    if adv_ratio >= 75:
        breadth_state = "高度扩散"
    elif adv_ratio >= 60:
        breadth_state = "明显偏多"
    elif adv_ratio >= 52:
        breadth_state = "略偏多"
    elif dec_ratio >= 75:
        breadth_state = "高度收缩"
    elif dec_ratio >= 60:
        breadth_state = "明显偏空"
    elif dec_ratio >= 52:
        breadth_state = "略偏空"
    else:
        breadth_state = "多空均衡"

    # 指数与广度的背离是编辑式总结中非常重要的信号。
    breadth_divergence = ""
    if chg >= 0.5 and adv_ratio < 50:
        breadth_divergence = "上涨但广度偏弱"
    elif chg >= 0.8 and adv_ratio < 60:
        breadth_divergence = "上涨但广度有限"
    elif chg <= -0.5 and adv_ratio > 50:
        breadth_divergence = "下跌但广度尚有支撑"
    elif chg <= -0.8 and adv_ratio > 40:
        breadth_divergence = "下跌但并非全面抛售"

    # ---------- 行业状态 ----------
    sector_up = sum(1 for x in sectors if _change(x) > 0)
    sector_down = sum(1 for x in sectors if _change(x) < 0)
    sector_total = max(len(sectors), 1)
    sector_up_ratio = sector_up / sector_total * 100

    best_sector = _first_name(sectors, True)
    worst_sector = _first_name(sectors, False)
    best_sector_chg = _first_change(sectors, True)
    worst_sector_chg = _first_change(sectors, False)

    if sectors:
        if sector_up_ratio >= 75:
            sector_state = "行业普涨"
        elif sector_up_ratio >= 60:
            sector_state = "行业多数走强"
        elif sector_up_ratio <= 25:
            sector_state = "行业普跌"
        elif sector_up_ratio <= 40:
            sector_state = "行业多数承压"
        else:
            sector_state = "行业分化"
    else:
        sector_state = "行业数据有限"

    sector_spread = best_sector_chg - worst_sector_chg

    # ---------- 个股状态 ----------
    top_gain_name = _name(gainers[0]) if gainers else ""
    top_gain_chg = _change(gainers[0]) if gainers else 0
    top_loss_name = _name(losers[0]) if losers else ""
    top_loss_chg = _change(losers[0]) if losers else 0

    weighted_names = _top_weight_names(top_gainers, 3)
    if not weighted_names:
        weighted_names = _top_weight_names(top_losers, 3)

    # ---------- 辅助句库 ----------
    positive_openers = [
        "纳指100延续风险偏好修复势头",
        "纳指100今日获得买盘支持",
        "科技股重新成为市场上行的主要支点",
        "纳指100维持偏强格局",
        "成长股重新占据市场交易中心",
        "美股科技板块延续强势表现",
        "纳指100在震荡中进一步走高",
        "大型科技股的反弹推动指数继续上行",
    ]

    negative_openers = [
        "纳指100今日承受明显卖压",
        "科技股回吐近期涨幅，纳指100走弱",
        "成长股遭遇获利了结，拖累纳指100表现",
        "纳指100在高位震荡中出现回落",
        "大型科技股走弱令指数承压",
        "风险偏好有所降温，科技板块成为主要压力来源",
        "纳指100结束此前的上行势头，今日明显走低",
        "市场对高估值成长股的追价意愿有所减弱",
    ]

    flat_openers = [
        "纳指100今日维持窄幅震荡",
        "科技股整体缺乏明确方向，纳指100基本持平",
        "市场在近期涨跌之后进入消化阶段",
        "纳指100在多空力量拉锯下维持震荡格局",
        "成长股买盘与获利回吐相互抵消，指数方向并不鲜明",
    ]

    breadth_positive = [
        "上涨个股明显占优，买盘已经从少数龙头向更广泛的成分股扩散",
        "超过半数成分股同步收高，显示市场内部参与度正在改善",
        "上涨覆盖面较广，今日行情并非单纯依赖个别权重股拉动",
        "市场广度与指数方向形成共振，风险偏好呈现较为完整的修复特征",
    ]

    breadth_negative = [
        "下跌个股占据明显优势，市场内部的风险偏好仍然偏弱",
        "多数成分股同步走低，今日回落具有较强的市场广度特征",
        "卖压并未局限于少数股票，市场内部呈现较为普遍的收缩",
        "指数走弱的同时市场广度同步恶化，显示资金撤离并非局部现象",
    ]

    # ---------- 总览：按市场状态 + 广度组合 ----------
    if chg >= 0.2:
        opener = random.choice(positive_openers)
        if adv_ratio >= 60:
            middle = random.choice(breadth_positive)
        elif breadth_divergence:
            middle = (
                f"不过，{breadth_divergence}，上涨主要集中在部分成分股，"
                "指数表面的强势仍需更多个股参与来确认。"
            )
        else:
            middle = (
                f"指数上涨{abs(chg):.2f}%，共有{adv}只成分股上涨、"
                f"{dec}只下跌，市场内部整体保持偏多格局。"
            )
    elif chg <= -0.2:
        opener = random.choice(negative_openers)
        if dec_ratio >= 60:
            middle = random.choice(breadth_negative)
        elif breadth_divergence:
            middle = (
                f"但值得注意的是，{breadth_divergence}，"
                "指数跌幅并未完全反映市场内部的真实强弱。"
            )
        else:
            middle = (
                f"指数下跌{abs(chg):.2f}%，共有{adv}只成分股上涨、"
                f"{dec}只下跌，市场内部情绪偏向谨慎。"
            )
    else:
        opener = random.choice(flat_openers)
        middle = (
            f"指数变动仅{abs(chg):.2f}%，上涨{adv}只、下跌{dec}只，"
            "多空双方暂未形成足以推动指数脱离近期区间的力量。"
        )

    if sector_state == "行业普涨":
        sector_tail = (
            f"行业层面同样偏强，约{sector_up_ratio:.0f}%的行业收高，"
            f"{best_sector or '领涨板块'}涨幅居前。"
        )
    elif sector_state == "行业普跌":
        sector_tail = (
            f"行业层面同步承压，约{100-sector_up_ratio:.0f}%的行业收跌，"
            f"{worst_sector or '弱势板块'}成为主要拖累。"
        )
    elif sectors and sector_spread >= 2:
        sector_tail = (
            f"板块之间的分化较为明显，{best_sector or '强势板块'}上涨"
            f"{best_sector_chg:.2f}%，而{worst_sector or '弱势板块'}下跌"
            f"{abs(worst_sector_chg):.2f}%，资金仍在不同科技主题之间轮动。"
        )
    else:
        sector_tail = ""

    ai_summary = (
        f"{opener}，纳指100收于今日交易区间附近，日内变动{_pct(chg)}。"
        f"{middle}"
        f"{sector_tail}"
    ).replace("。", "。 ", 1).strip()

    # ---------- 个股总结 ----------
    if gainers and losers:
        if top_gain_chg >= 5:
            stock_lead = (
                f"{top_gain_name}上涨{top_gain_chg:.2f}%，成为今日表现最突出的成分股；"
                f"{top_loss_name}则下跌{abs(top_loss_chg):.2f}%，位于跌幅前列。"
            )
        elif adv_ratio >= 65:
            stock_lead = (
                f"个股层面买盘较为广泛，领涨股{top_gain_name}上涨{top_gain_chg:.2f}%，"
                f"而跌幅最大的{top_loss_name}下跌{abs(top_loss_chg):.2f}%。"
            )
        elif dec_ratio >= 65:
            stock_lead = (
                f"个股卖压较为普遍，{top_loss_name}下跌{abs(top_loss_chg):.2f}%领跌，"
                f"{top_gain_name}仍录得{top_gain_chg:.2f}%涨幅，但难以改变整体偏弱格局。"
            )
        else:
            stock_lead = (
                f"个股表现分化，{top_gain_name}上涨{top_gain_chg:.2f}%，"
                f"{top_loss_name}下跌{abs(top_loss_chg):.2f}%，"
                "市场内部仍存在较明显的多空博弈。"
            )
    elif gainers:
        stock_lead = f"上涨个股中，{top_gain_name}以{top_gain_chg:.2f}%的涨幅居前。"
    elif losers:
        stock_lead = f"下跌个股中，{top_loss_name}以{abs(top_loss_chg):.2f}%的跌幅居前。"
    else:
        stock_lead = "今日缺乏足够的个股数据形成明确的领涨或领跌结构。"

    if weighted_names:
        weight_tail = (
            f"从核心成分股看，市场关注仍集中于{', '.join(weighted_names[:3])}等权重较高的股票，"
            "其走势对指数方向具有较强影响。"
        )
    elif adv_ratio >= 60:
        weight_tail = "今日指数并未呈现明显的单一龙头依赖特征，市场参与面相对均衡。"
    else:
        weight_tail = "个股层面的分化意味着指数表现仍需结合权重结构观察。"

    ai_stocks = stock_lead + weight_tail

    # ---------- 行业总结 ----------
    if sectors:
        if sector_up_ratio >= 70:
            ai_sectors = (
                f"行业表现明显偏多，{sector_up}个行业上涨、{sector_down}个行业下跌，"
                f"上涨覆盖率约为{sector_up_ratio:.0f}%。"
                f"{best_sector or '领涨板块'}以{best_sector_chg:.2f}%的涨幅领先，"
                "资金参与已经从单一主题扩展至更广泛的科技板块。"
            )
        elif sector_up_ratio <= 30:
            ai_sectors = (
                f"行业表现整体偏弱，仅{sector_up}个行业上涨，而{sector_down}个行业下跌，"
                f"下跌覆盖率约为{100-sector_up_ratio:.0f}%。"
                f"{worst_sector or '弱势板块'}下跌{abs(worst_sector_chg):.2f}%，"
                "显示卖压具有较明显的板块扩散特征。"
            )
        else:
            ai_sectors = (
                f"行业轮动仍是今日市场的重要特征，{sector_up}个行业上涨、"
                f"{sector_down}个行业下跌。"
                f"{best_sector or '强势板块'}上涨{best_sector_chg:.2f}%居前，"
                f"{worst_sector or '弱势板块'}则下跌{abs(worst_sector_chg):.2f}%，"
                "板块之间的收益差距显示资金正在不同科技主题之间重新定价。"
            )
    else:
        ai_sectors = "行业数据暂不足以形成可靠的板块轮动判断。"

    # ---------- 分布总结 ----------
    if dominant_bin:
        if adv_ratio >= 65:
            dist_open = "个股涨跌幅分布呈现明显的正向聚集特征"
        elif dec_ratio >= 65:
            dist_open = "个股涨跌幅分布明显向负收益一侧倾斜"
        else:
            dist_open = "个股涨跌幅分布整体较为分散"

        ai_distribution = (
            f"{dist_open}，数量最多的收益区间为“{dominant_bin}”，"
            f"约有{dominant_count}只成分股落在该区间。"
        )
        if abs(chg) >= 1 and adv_ratio >= 60:
            ai_distribution += (
                "指数与个股分布方向一致，说明今日行情具有较强的内部确认。"
            )
        elif abs(chg) >= 1 and dec_ratio >= 60:
            ai_distribution += (
                "指数方向与多数个股同步，市场并非局部股票造成的单点波动。"
            )
        elif breadth_divergence:
            ai_distribution += (
                "不过指数与市场广度之间存在一定背离，表面指数表现需要谨慎解读。"
            )
        else:
            ai_distribution += (
                "从分布结构看，市场尚未形成极端单边行情。"
            )
    else:
        if adv_ratio >= 70:
            dist_comment = "多数成分股收涨，市场内部呈现较强的正向扩散。"
        elif dec_ratio >= 70:
            dist_comment = "多数成分股收跌，卖压在市场内部形成明显扩散。"
        else:
            dist_comment = "个股涨跌较为均衡，市场内部缺乏极端单边特征。"
        ai_distribution = (
            f"{dist_comment} 今日上涨{adv}只、下跌{dec}只，"
            f"上涨占比约{adv_ratio:.1f}%。"
        )

    # ---------- 行业广度总结 ----------
    if sectors:
        if sector_up_ratio >= 75:
            ai_industry = (
                f"行业广度明显改善，{sector_up}个行业中有{sector_up}个上涨，"
                f"上涨比例达到{sector_up_ratio:.0f}%。"
                "这种广泛参与通常意味着市场风险偏好并非由单一行业独立推动。"
            )
        elif sector_up_ratio <= 25:
            ai_industry = (
                f"行业广度明显恶化，仅{sector_up}个行业上涨，"
                f"{sector_down}个行业下跌。"
                "指数表现背后的资金参与度偏低，防御或局部主题交易特征更加突出。"
            )
        elif 45 <= sector_up_ratio <= 55:
            ai_industry = (
                f"行业广度接近均衡，{sector_up}个行业上涨、{sector_down}个下跌。"
                "在这种环境下，指数方向更多取决于高权重成分股的相对表现。"
            )
        else:
            direction = "偏强" if sector_up_ratio > 50 else "偏弱"
            ai_industry = (
                f"行业广度整体{direction}，上涨行业占比约{sector_up_ratio:.0f}%。"
                f"最强与最弱行业之间相差约{sector_spread:.2f}个百分点，"
                "板块轮动仍然是解释指数表现的重要线索。"
            )
    else:
        ai_industry = (
            f"目前可确认的市场广度为：{adv}只上涨、{dec}只下跌、{unc}只持平，"
            "整体参与度仍需结合行业数据进一步观察。"
        )

    # ---------- 趋势总结 ----------
    if trend_return > 5:
        trend_phrase = "过去30个交易日仍保持较强的上行趋势"
    elif trend_return > 1:
        trend_phrase = "过去30个交易日维持温和上行格局"
    elif trend_return > -1:
        trend_phrase = "过去30个交易日整体处于震荡整理状态"
    elif trend_return > -5:
        trend_phrase = "过去30个交易日呈现温和回落"
    else:
        trend_phrase = "过去30个交易日处于明显的下行阶段"

    ai_trend = (
        f"从中期维度观察，纳指100{trend_phrase}"
        f"，30日累计变动约为{trend_return:.2f}%。"
    )

    if distance_high:
        if abs(distance_high) < 2:
            ai_trend += (
                "指数仍接近近期高位，当前价格位置意味着市场已经消化了相当一部分乐观预期，"
                "后续走势对新的催化因素会更加敏感。"
            )
        elif distance_high < -5:
            ai_trend += (
                f"指数距离近期高点仍有约{abs(distance_high):.1f}%的空间，"
                "中期趋势尚未完全修复，当前反弹仍需进一步观察持续性。"
            )

    if distance_low and distance_low < 5:
        ai_trend += (
            "与此同时，指数仍处于近期低位附近，市场尚未完全摆脱前期调整留下的压力。"
        )

    if trend_return > 1 and chg < -0.5:
        ai_trend += (
            "值得注意的是，今日回落与中期上行趋势形成一定背离，"
            "更接近趋势中的短线整理，而非趋势方向已经发生明确反转。"
        )
    elif trend_return < -1 and chg > 0.5:
        ai_trend += (
            "今日反弹与中期偏弱格局形成一定背离，"
            "在趋势尚未扭转之前，更适合视作阶段性修复而非趋势确认。"
        )
    elif trend_return > 1 and chg > 0.5:
        ai_trend += (
            "今日价格方向与中期趋势形成共振，短线动能对既有趋势构成进一步确认。"
        )
    elif trend_return < -1 and chg < -0.5:
        ai_trend += (
            "今日价格方向与中期趋势一致，短线弱势仍在强化原有下行结构。"
        )
    else:
        ai_trend += (
            "短线价格变化与中期趋势之间尚未形成足够强的方向性信号。"
        )

    # ---------- 最终风格微调 ----------
    # 避免六段文字开头完全重复。
    ai_summary = ai_summary.replace("纳指100纳指100", "纳指100")
    ai_stocks = ai_stocks.replace("纳指100纳指100", "纳指100")

    return {
        "ai_summary": ai_summary,
        "ai_stocks": ai_stocks,
        "ai_sectors": ai_sectors,
        "ai_distribution": ai_distribution,
        "ai_industry": ai_industry,
        "ai_trend": ai_trend,
    }


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
