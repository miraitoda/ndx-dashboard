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
.theme-btn{padding:6px 14px;border-radius:10px;border:1px solid var(--border);background:transparent;cursor:pointer;transition:all 0.2s;display:flex;align-items:center;justify-content:center}
.theme-btn:hover{border-color:var(--accent)}
.theme-btn svg{width:20px;height:20px}

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
.sector-name{width:80px;text-align:right;font-size:13px;font-weight:700;color:var(--text2)}
.sector-bar{flex:1;height:28px;border-radius:0 4px 4px 0;position:relative}
.sector-bar.up{background:var(--rise)}
.sector-bar.down{background:var(--fall);border-radius:4px 0 0 4px;margin-left:auto}
.sector-bar-label{position:absolute;top:50%;transform:translateY(-50%);font-size:12px;font-weight:800;font-family:'SF Mono',monospace}
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
      <button class="theme-btn" onclick="toggleTheme()" title="切换主题">
        <svg viewBox="0 0 22 22" fill="none"><circle cx="11" cy="11" r="8" stroke="var(--text3)" stroke-width="1.5" opacity="0.3"/><path d="M11 3C6.03 3 2 7.03 2 12C2 16.97 6.03 21 11 21V3Z" fill="var(--text)" opacity="0.9"/><circle cx="11" cy="7" r="2" fill="var(--bg)"/><circle cx="11" cy="17" r="2" fill="var(--text3)"/></svg>
      </button>
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
      <p style="margin:0;font-size:13px;line-height:1.6;color:var(--text2);font-weight:500;"></p>
    </div>
  </section>

  <div class="divider"></div>

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
      <p style="margin:0;font-size:13px;line-height:1.6;color:var(--text2);font-weight:500;"></p>
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
      <p style="margin:0;font-size:13px;line-height:1.6;color:var(--text2);font-weight:500;"></p>
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
          <p style="margin:0;font-size:13px;line-height:1.6;color:var(--text2);font-weight:500;"></p>
        </div>
      </div>
      <div class="card" style="padding:48px">
        <div class="card-title">行业权重</div>
        <div class="card-sub">Sector Distribution</div>
        <div class="pie-container" id="sectorPie"></div>
        <div class="pie-legend" id="sectorLegend"></div>
        <div class="card" id="aiSectorsBox" style="display:none;margin-top:20px;padding:16px 20px;">
          <p style="margin:0;font-size:13px;line-height:1.6;color:var(--text2);font-weight:500;"></p>
        </div>
      </div>
    </div>
  </section>

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
  document.getElementById("idxPrice").textContent=idx.price?idx.price.toLocaleString():"估算中";
  const chgEl=document.getElementById("idxChange");
  chgEl.textContent=fmtPct(idx.change)+(idx.price?(" ("+(idx.price-idx.prev_close).toFixed(2)+")"):"");
  chgEl.className="kpi-change "+(idx.change>=0?"up":"down");
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
    const bar=document.createElement("div");bar.className="sector-bar "+(isUp?"up":"down");
    const pct=Math.min(Math.abs(d.change)/maxC,1)*100;
    bar.style.width=pct+"%";bar.style.flex="none";bar.style.flexBasis=pct+"%";
    const label=document.createElement("span");label.className="sector-bar-label "+(isUp?"up":"down");label.textContent=fmtPct(d.change);
    bar.appendChild(label);
    row.appendChild(name);row.appendChild(bar);
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
  svg.appendChild(svgEl("path",{d:areaD,fill:"url(#trendGrad)"}));
  let lineD="M "+x(0)+" "+y(data[0]);
  data.forEach((v,i)=>lineD+=" L "+x(i)+" "+y(v));
  svg.appendChild(svgEl("path",{d:lineD,fill:"none",stroke:RISE,"stroke-width":"2.5","stroke-linecap":"round","stroke-linejoin":"round"}));
  data.forEach((v,i)=>{
    const c=svgEl("circle",{cx:x(i),cy:y(v),r:i===data.length-1?5:3.5,fill:i===data.length-1?RISE:BG,stroke:RISE,"stroke-width":i===data.length-1?2.5:1.5});
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
  // 外圈光晕
  svg.appendChild(svgEl("circle",{cx:200,cy:170,r:155,fill:"none",stroke:RISE,"stroke-width":24,opacity:0.06}));
  svg.appendChild(svgEl("circle",{cx:200,cy:170,r:140,fill:"none",stroke:RISE,"stroke-width":18,opacity:0.1}));
  // 主环
  svg.appendChild(svgEl("circle",{cx:200,cy:170,r:125,fill:"none",stroke:RISE,"stroke-width":14,opacity:0.18}));
  svg.appendChild(svgEl("circle",{cx:200,cy:170,r:108,fill:"none",stroke:RISE,"stroke-width":10,opacity:0.28,"stroke-dasharray":"280 680",transform:"rotate(-90 200 170)"}));
  svg.appendChild(svgEl("circle",{cx:200,cy:170,r:93,fill:"none",stroke:FALL,"stroke-width":10,opacity:0.22,"stroke-dasharray":"120 680","stroke-dashoffset":"-280",transform:"rotate(-90 200 170)"}));
  svg.appendChild(svgEl("circle",{cx:200,cy:170,r:78,fill:"none",stroke:ACCENT,"stroke-width":8,opacity:0.15,"stroke-dasharray":"80 680","stroke-dashoffset":"-400",transform:"rotate(-90 200 170)"}));
  // 中心文字
  svg.appendChild(svgEl("text",{x:200,y:158,"text-anchor":"middle",fill:TEXT,"font-size":28,"font-weight":900,"letter-spacing":"-1"})).textContent="NDX";
  svg.appendChild(svgEl("text",{x:200,y:185,"text-anchor":"middle",fill:RISE,"font-size":18,"font-weight":800,"font-family":"'SF Mono',monospace"})).textContent=fmtPct(DATA.index.change);
  container.appendChild(svg);
  // Legend
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
  svg.setAttribute("viewBox","0 0 400 340");svg.style.width="100%";svg.style.maxWidth="380px";svg.style.height="auto";
  // 外圈光晕
  svg.appendChild(svgEl("circle",{cx:200,cy:170,r:155,fill:"none",stroke:ACCENT,"stroke-width":24,opacity:0.06}));
  svg.appendChild(svgEl("circle",{cx:200,cy:170,r:140,fill:"none",stroke:ACCENT,"stroke-width":18,opacity:0.1}));
  // 主环
  svg.appendChild(svgEl("circle",{cx:200,cy:170,r:125,fill:"none",stroke:ACCENT,"stroke-width":14,opacity:0.15}));
  svg.appendChild(svgEl("circle",{cx:200,cy:170,r:108,fill:"none",stroke:RISE,"stroke-width":10,opacity:0.25,"stroke-dasharray":"240 680",transform:"rotate(-90 200 170)"}));
  svg.appendChild(svgEl("circle",{cx:200,cy:170,r:93,fill:"none",stroke:FALL,"stroke-width":10,opacity:0.2,"stroke-dasharray":"140 680","stroke-dashoffset":"-240",transform:"rotate(-90 200 170)"}));
  svg.appendChild(svgEl("circle",{cx:200,cy:170,r:78,fill:"none",stroke:ACCENT,"stroke-width":8,opacity:0.15,"stroke-dasharray":"60 680","stroke-dashoffset":"-380",transform:"rotate(-90 200 170)"}));
  // 中心文字
  svg.appendChild(svgEl("text",{x:200,y:158,"text-anchor":"middle",fill:TEXT,"font-size":24,"font-weight":900,"letter-spacing":"-0.5"})).textContent="SECTORS";
  // 计算涨跌sector平均
  const upSectors=data.filter(d=>d.change>=0);
  const downSectors=data.filter(d=>d.change<0);
  const upAvg=upSectors.length?upSectors.reduce((a,b)=>a+b.change,0)/upSectors.length:0;
  const downAvg=downSectors.length?downSectors.reduce((a,b)=>a+b.change,0)/downSectors.length:0;
  svg.appendChild(svgEl("text",{x:200,y:185,"text-anchor":"middle",fill:RISE,"font-size":16,"font-weight":800,"font-family":"'SF Mono',monospace"})).textContent="▲ "+fmtPctRaw(upAvg);
  svg.appendChild(svgEl("text",{x:200,y:205,"text-anchor":"middle",fill:FALL,"font-size":14,"font-weight":700,"font-family":"'SF Mono',monospace"})).textContent="▼ "+fmtPctRaw(downAvg);
  container.appendChild(svg);
  // Legend
  const leg=document.getElementById("sectorLegend");
  data.forEach(d=>{
    const item=document.createElement("div");item.className="pie-legend-item";
    item.innerHTML='<span class="pie-legend-dot" style="background:'+colorForChange(d.change)+'"></span>'+d.name+" "+d.weight+"%";
    leg.appendChild(item);
  });
})();

// 行情条
(function(){
  const topStocks=DATA.stocks.slice().sort((a,b)=>Math.abs(b.change)-Math.abs(a.change));
  const bottomStocks=DATA.stocks.slice().sort(()=>Math.random()-0.5);
  function buildTicker(id,stocks,reverse){
    const bar=document.getElementById(id);
    if(!bar)return;
    const track=document.createElement("div");
    track.className="ticker-track"+(reverse?" ticker-track-reverse":"");
    track.style.animation=reverse?"ticker-scroll-reverse 40s linear infinite":"ticker-scroll 40s linear infinite";
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
  const icon=document.querySelector(".theme-btn svg");
  if(root.classList.contains("light")){
    root.classList.remove("light");
  }else{
    root.classList.add("light");
  }
}

// 跟随系统主题
if(window.matchMedia&&window.matchMedia("(prefers-color-scheme: light)").matches){
  document.documentElement.classList.add("light");
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
</script>
</body></html>"""
