#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
纳指100每日收盘 Dashboard 数据抓取脚本
"""

import json
import math
import os
import sys
from datetime import datetime
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
        hist = t.history(period=f"{days + 5}d", interval="1d")
        closes = hist["Close"].dropna().tolist()
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
    result["ai_summary"] = generate_summary(result)
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
<title>纳指100 - 每日收盘</title>
<style>
:root{
  --bg:#0b0e14;--surface:#151921;--surface-raised:#1e222d;--surface-glass:rgba(30,34,45,0.6);
  --text:#e2e8f0;--text-secondary:#94a3b8;--text-tertiary:#64748b;
  --border:rgba(148,163,184,0.08);--border-strong:rgba(148,163,184,0.15);
  --rise:#089981;--fall:#f23645;
  --accent-glow:rgba(59,130,246,0.08);
  --shadow:0 4px 24px rgba(0,0,0,0.4);--shadow-lg:0 8px 40px rgba(0,0,0,0.5);
  --glow-color:#f23645;--glow-border:rgba(242,54,69,0.25);
  --badge-bg:rgba(242,54,69,0.1);--badge-color:#f23645;--badge-border:rgba(242,54,69,0.2);
}
.light{
  --bg:#f1f5f9;--surface:#ffffff;--surface-raised:#ffffff;--surface-glass:rgba(255,255,255,0.7);
  --text:#0f172a;--text-secondary:#475569;--text-tertiary:#94a3b8;
  --border:rgba(148,163,184,0.15);--border-strong:rgba(148,163,184,0.25);
  --accent-glow:rgba(59,130,246,0.04);
  --shadow:0 4px 24px rgba(0,0,0,0.06);--shadow-lg:0 8px 40px rgba(0,0,0,0.08);
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue","PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--text);line-height:1.5}



.container{max-width:1200px;margin:0 auto;padding:24px}

.toolbar{display:flex;justify-content:space-between;align-items:center;padding:12px 24px;border-bottom:1px solid var(--glow-border);background:linear-gradient(180deg,var(--surface) 0%,var(--surface-glass) 100%);position:sticky;top:0;z-index:100;backdrop-filter:blur(20px);box-shadow:0 0 40px var(--glow-color),0 4px 20px rgba(0,0,0,0.2)}
.toolbar-left,.toolbar-right{display:flex;align-items:center;gap:10px}
.nav-btns{display:flex;gap:8px}
.nav-btn{padding:6px 14px;border-radius:8px;border:1px solid var(--border-strong);background:var(--surface-glass);color:var(--text-secondary);font-size:13px;font-weight:600;cursor:pointer;transition:all 0.2s;font-family:inherit}
.nav-btn:hover:not(:disabled){border-color:var(--text-tertiary);color:var(--text);background:var(--surface)}
.nav-btn:disabled{opacity:0.35;cursor:not-allowed}
.icon-btn{display:flex;align-items:center;justify-content:center;width:36px;height:36px;border-radius:10px;border:1px solid var(--border-strong);background:var(--surface-glass);color:var(--text-secondary);cursor:pointer;transition:all 0.2s}
.icon-btn:hover{border-color:var(--text-tertiary);color:var(--text);background:var(--surface);transform:rotate(180deg)}
.icon-btn svg{transition:transform 0.4s ease}
.icon-btn:hover svg{transform:rotate(-180deg)}

.ai-summary{background:var(--surface-raised);border:1px solid var(--glow-border);border-radius:20px;padding:22px 28px;margin-bottom:32px;position:relative;overflow:hidden;box-shadow:var(--shadow)}
.ai-summary::before{content:"";position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,transparent,var(--glow-color),transparent);opacity:.6}
.ai-label{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--glow-color);font-weight:700;margin-bottom:10px;text-transform:uppercase;letter-spacing:1px}
.ai-summary p{margin:0;font-size:15px;line-height:1.7;color:var(--text-secondary);font-weight:500}

/* Hero */
.hero{position:relative;padding:40px 0 32px;margin-bottom:32px;text-align:center;overflow:hidden}
.hero::before{content:"";position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:600px;height:300px;background:radial-gradient(ellipse,var(--accent-glow) 0%,transparent 70%);pointer-events:none}
.hero h1{font-size:48px;font-weight:900;letter-spacing:-2px;background:linear-gradient(135deg,var(--text) 0%,var(--text-secondary) 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:12px;position:relative}
.hero .meta{display:inline-flex;align-items:center;gap:16px;font-size:14px;color:var(--text-tertiary);font-weight:500}
.hero .badge{font-size:11px;padding:4px 14px;border-radius:20px;background:var(--badge-bg);color:var(--badge-color);border:1px solid var(--badge-border);font-weight:700;letter-spacing:0.5px}

/* KPI */
.kpi-row{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:32px}
.kpi{background:var(--surface-raised);border:1px solid var(--border);border-radius:20px;padding:28px 24px;position:relative;overflow:hidden;transition:transform 0.2s,box-shadow 0.2s;box-shadow:var(--shadow)}
.kpi:hover{transform:translateY(-3px);box-shadow:var(--shadow-lg)}
.kpi::before{content:"";position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,transparent,var(--glow-color),transparent);opacity:0.6}
.kpi::after{content:"";position:absolute;top:-50%;left:-50%;width:200%;height:200%;background:radial-gradient(circle at 50% 0%,rgba(255,255,255,0.03) 0%,transparent 50%);pointer-events:none}
.kpi-label{font-size:11px;color:var(--text-tertiary);margin-bottom:12px;text-transform:uppercase;letter-spacing:2px;font-weight:700}
.kpi-value{font-size:42px;font-weight:900;font-variant-numeric:tabular-nums;line-height:1;letter-spacing:-1.5px;color:var(--text)}
.kpi-sub{font-size:16px;margin-top:12px;font-weight:700;font-variant-numeric:tabular-nums}
.kpi-sub.up{color:var(--rise)}.kpi-sub.down{color:var(--fall)}

/* 图表 */
.charts-row{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:32px}
.chart-box{background:var(--surface-raised);border:1px solid var(--border);border-radius:24px;padding:28px;position:relative;overflow:hidden;box-shadow:var(--shadow);transition:transform 0.2s}
.chart-box:hover{transform:translateY(-2px)}
.chart-box::before{content:"";position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,transparent,var(--glow-color),transparent);opacity:0.5}
.chart-box::after{content:"";position:absolute;top:-30%;right:-20%;width:300px;height:300px;background:radial-gradient(circle,var(--accent-glow) 0%,transparent 60%);pointer-events:none}
.chart-title{font-size:18px;font-weight:800;margin-bottom:6px;color:var(--text);letter-spacing:-0.3px}
.chart-sub{font-size:12px;color:var(--text-tertiary);margin-bottom:16px;font-weight:500}

.full-row{margin-bottom:32px}

.legend{display:flex;flex-wrap:wrap;gap:10px 18px;margin-top:14px;font-size:12px}
.legend-item{display:flex;align-items:center;gap:6px;color:var(--text-secondary);font-weight:600}
.legend-dot{width:10px;height:10px;border-radius:3px}

.stock-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(95px,1fr));gap:6px;margin-top:14px}
.stock-cell{padding:8px 10px;border-radius:10px;font-size:12px;text-align:center;cursor:pointer;transition:all 0.15s;background:var(--surface);border:1px solid var(--border);font-weight:700;box-shadow:0 2px 8px rgba(0,0,0,0.1)}
.light .stock-cell{box-shadow:0 2px 8px rgba(0,0,0,0.03)}
.stock-cell:hover{transform:translateY(-3px) scale(1.02);box-shadow:0 8px 24px rgba(0,0,0,0.2);border-color:var(--border-strong)}

.footer{text-align:center;font-size:12px;color:var(--text-tertiary);margin-top:40px;padding:24px;border-top:1px solid var(--border);font-weight:500}

@media(max-width:720px){.charts-row{grid-template-columns:1fr}.kpi-row{grid-template-columns:repeat(2,1fr)}.kpi-value{font-size:32px}.hero h1{font-size:36px}.container{padding:16px}}
</style></head><body>

<div class="toolbar">
  <div class="toolbar-left">
    <div class="logo">NDX <span>DASHBOARD</span></div>
    <div class="nav-btns">
      <button class="nav-btn" id="btnPrev" disabled>← 前一日</button>
      <button class="nav-btn" id="btnNext" disabled>后一日 →</button>
    </div>
  </div>
  <div class="toolbar-right">
    <button class="icon-btn" onclick="location.reload()" title="刷新页面">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="1 4 1 10 7 10"></polyline>
        <polyline points="23 20 23 14 17 14"></polyline>
        <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"></path>
      </svg>
    </button>
    <button class="icon-btn" onclick="toggleTheme()" title="切换主题">
      <svg id="theme-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>
      </svg>
    </button>
  </div>
</div>

<div class="container">
  <div class="hero">
    <h1>纳斯达克100</h1>
    <div class="meta">
      <span id="dateStr"></span>
      <span class="badge" id="statusBadge">已收盘</span>
    </div>
  </div>

  <div class="ai-summary" id="aiSummaryBox" style="display:none">
    <div class="ai-label">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
      <span>AI 行情总结</span>
    </div>
    <p id="aiSummaryText"></p>
  </div>

  <div class="kpi-row">
    <div class="kpi" id="kpiPrice"><div class="kpi-label">指数点位</div><div class="kpi-value" id="idxPrice">--</div><div class="kpi-sub" id="idxChange">--</div></div>
    <div class="kpi" id="kpiUpDown"><div class="kpi-label">涨跌家数</div><div class="kpi-value" style="font-size:28px" id="upDown">--</div><div class="kpi-sub" style="color:var(--text-tertiary)">涨 / 跌</div></div>
    <div class="kpi" id="kpiTrend"><div class="kpi-label">30日走势</div><div class="kpi-value" id="trend30d">--</div><div class="kpi-sub" style="color:var(--text-tertiary)" id="trendRange">--</div></div>
    <div class="kpi"><div class="kpi-label">数据状态</div><div class="kpi-value" style="font-size:28px" id="dataStatus">正常</div><div class="kpi-sub" style="color:var(--text-tertiary)">成分股 <span id="stockCount">--</span> 只</div></div>
  </div>

  <div class="charts-row">
    <div class="chart-box">
      <div class="chart-title">个股权重饼图（Top 15 + 其他）</div>
      <div class="chart-sub">绿色=上涨，红色=下跌，面积=权重</div>
      <svg id="stockPie" viewBox="0 0 320 280" style="width:100%;height:auto"></svg>
      <div class="legend" id="stockLegend"></div>
    </div>
    <div class="chart-box">
      <div class="chart-title">行业权重饼图</div>
      <div class="chart-sub">绿色=上涨，红色=下跌，面积=权重</div>
      <svg id="sectorPie" viewBox="0 0 320 280" style="width:100%;height:auto"></svg>
      <div class="legend" id="sectorLegend"></div>
    </div>
  </div>

  <div class="charts-row">
    <div class="chart-box">
      <div class="chart-title">涨跌分布柱图</div>
      <div class="chart-sub">100支成分股按涨跌幅区间分布</div>
      <svg id="distChart" viewBox="0 0 400 220" style="width:100%;height:auto"></svg>
    </div>
    <div class="chart-box">
      <div class="chart-title">行业表现柱图</div>
      <div class="chart-sub">各行业按权重加权平均涨跌幅</div>
      <svg id="sectorBar" viewBox="0 0 400 320" style="width:100%;height:auto"></svg>
    </div>
  </div>

  <div class="full-row chart-box">
    <div class="chart-title">纳指100 · 近30日走势</div>
    <div class="chart-sub">每日收盘价连线</div>
    <svg id="trendLine" viewBox="0 0 800 240" style="width:100%;height:auto"></svg>
  </div>

  <div class="chart-box">
    <div class="chart-title">100支成分股涨跌一览</div>
    <div class="chart-sub">鼠标悬停查看详情</div>
    <div class="stock-grid" id="stockGrid"></div>
  </div>

  <div class="footer">数据来自 Yahoo Finance · 每日自动更新 · 仅供参考不构成投资建议</div>
</div>

<div class="tooltip" id="tooltip" style="position:absolute;background:#2a2e39;border:1px solid var(--border);border-radius:8px;padding:8px 12px;font-size:12px;color:#e2e8f0;pointer-events:none;opacity:0;transition:opacity .15s;z-index:10;box-shadow:0 4px 12px rgba(0,0,0,0.15);white-space:nowrap"></div>

<script>
const DATA = __DATA_JSON__;

const RISE = "#089981";
const FALL = "#f23645";
const TEXT = "#d1d4dc";
const TEXT2 = "#868993";
const TEXT4 = "#434651";
const BORDER = "#2a2e39";

// 根据当日涨跌设置全局光晕颜色
const GLOW = DATA.index.change >= 0 ? RISE : FALL;
document.documentElement.style.setProperty("--glow-color", GLOW);
document.documentElement.style.setProperty("--glow-border", GLOW + "40");
document.documentElement.style.setProperty("--badge-bg", GLOW + "1A");
document.documentElement.style.setProperty("--badge-color", GLOW);
document.documentElement.style.setProperty("--badge-border", GLOW + "33");

// KPI 卡片涨跌色
const kpiPrice = document.getElementById("kpiPrice");
const kpiUpDown = document.getElementById("kpiUpDown");
const kpiTrend = document.getElementById("kpiTrend");
if(DATA.index.change >= 0){
  kpiPrice.classList.add("up"); kpiUpDown.classList.add("up"); kpiTrend.classList.add("up");
} else {
  kpiPrice.classList.add("down"); kpiUpDown.classList.add("down"); kpiTrend.classList.add("down");
}

function colorForChange(c){return c>=0?RISE:FALL}
function fmtPct(c){return(c>=0?"+":"")+c.toFixed(2)+"%"}
function svgEl(tag,attrs){const el=document.createElementNS("http://www.w3.org/2000/svg",tag);for(let k in attrs)el.setAttribute(k,attrs[k]);return el}

const HISTORY_DATES = __HISTORY_DATES__;
const IS_HISTORY = __IS_HISTORY__;

// 美股开盘状态判断（基于客户端实时时间）
function getMarketStatus() {
    const now = new Date();
    const utc = now.getTime() + now.getTimezoneOffset() * 60000;
    const beijing = new Date(utc + 8 * 3600000);
    const day = beijing.getDay();
    if (day === 0 || day === 6) return "已收盘";

    const year = beijing.getFullYear();
    // 夏令时：3月第二个周日 - 11月第一个周日
    const dstStart = new Date(year, 2, 14 - new Date(year, 2, 1).getDay());
    const dstEnd = new Date(year, 10, 7 - new Date(year, 10, 1).getDay());
    const isDST = beijing >= dstStart && beijing < dstEnd;

    const hour = beijing.getHours();
    const minute = beijing.getMinutes();
    const timeVal = hour + minute / 60;
    const openTime = isDST ? 21.5 : 22.5;   // 21:30 / 22:30
    const closeTime = isDST ? 28 : 29;       // 次日04:00 / 05:00

    if (timeVal >= openTime && timeVal < closeTime) return "开盘中";
    return "已收盘";
}

// 前后日导航
(function() {
    const btnPrev = document.getElementById("btnPrev");
    const btnNext = document.getElementById("btnNext");
    if (!btnPrev || !btnNext) return;

    const path = window.location.pathname;
    const isHistory = path.includes("/history/");
    let currentDate;

    if (isHistory) {
        const m = path.match(/history\\/(\\d{4}-\\d{2}-\\d{2})/);
        currentDate = m ? m[1] : DATA.date;
    } else {
        currentDate = DATA.date;
    }

    const idx = HISTORY_DATES.indexOf(currentDate);
    if (idx === -1) return;

    if (idx > 0) {
        const prevDate = HISTORY_DATES[idx - 1];
        btnPrev.disabled = false;
        btnPrev.onclick = () => {
            location.href = isHistory ? "./" + prevDate + ".html" : "./history/" + prevDate + ".html";
        };
    }

    if (idx < HISTORY_DATES.length - 1) {
        const nextDate = HISTORY_DATES[idx + 1];
        btnNext.disabled = false;
        if (nextDate === DATA.date && isHistory) {
            btnNext.onclick = () => location.href = "../index.html";
        } else {
            btnNext.onclick = () => {
                location.href = isHistory ? "./" + nextDate + ".html" : "./history/" + nextDate + ".html";
            };
        }
    }
})();

// 填充 KPI
(function(){
  const idx=DATA.index;
  document.getElementById("dateStr").textContent=DATA.date;
  document.getElementById("idxPrice").textContent=idx.price?idx.price.toLocaleString():"估算中";
  const chgEl=document.getElementById("idxChange");
  chgEl.textContent=fmtPct(idx.change)+(idx.price?" ("+(idx.price-idx.prev_close).toFixed(2)+")":"");
  chgEl.className="kpi-sub "+(idx.change>=0?"up":"down");
  document.getElementById("upDown").innerHTML=idx.up+' <span style="color:var(--text-tertiary)">/</span> '+idx.down;
  document.getElementById("stockCount").textContent=idx.total;
  const hist=DATA.history;
  if(hist.length>=2){
    const c30=((hist[hist.length-1]-hist[0])/hist[0]*100).toFixed(2);
    const t30=document.getElementById("trend30d");
    t30.textContent=(c30>=0?"+":"")+c30+"%";
    t30.style.color=c30>=0?RISE:FALL;
    document.getElementById("trendRange").textContent=Math.round(hist[0]).toLocaleString()+" -> "+Math.round(hist[hist.length-1]).toLocaleString();
  } else {
    document.getElementById("trend30d").textContent="--";
    document.getElementById("trendRange").textContent="数据暂缺";
  }
  if(idx.total<80){document.getElementById("dataStatus").textContent="部分缺失";document.getElementById("dataStatus").style.color=FALL}
})();

// AI 行情总结
(function(){
  if(DATA.ai_summary){
    document.getElementById("aiSummaryText").textContent = DATA.ai_summary;
    document.getElementById("aiSummaryBox").style.display = "block";
  }
})();

// 个股饼图
(function(){
  const svg=document.getElementById("stockPie");
  const data=DATA.pie_stocks;
  const total=data.reduce((a,b)=>a+b.weight,0);
  const cx=140,cy=130,r=90,ir=45;
  let ang=-Math.PI/2;
  data.forEach(d=>{
    const a=(d.weight/total)*Math.PI*2;
    const x1=cx+r*Math.cos(ang),y1=cy+r*Math.sin(ang);
    const x2=cx+r*Math.cos(ang+a),y2=cy+r*Math.sin(ang+a);
    const ix1=cx+ir*Math.cos(ang),iy1=cy+ir*Math.sin(ang);
    const ix2=cx+ir*Math.cos(ang+a),iy2=cy+ir*Math.sin(ang+a);
    const large=a>Math.PI?1:0;
    const path="M "+ix1+" "+iy1+" L "+x1+" "+y1+" A "+r+" "+r+" 0 "+large+" 1 "+x2+" "+y2+" L "+ix2+" "+iy2+" A "+ir+" "+ir+" 0 "+large+" 0 "+ix1+" "+iy1;
    const fill=colorForChange(d.change);
    const slice=svgEl("path",{d:path,fill:fill,opacity:.85,stroke:"var(--bg)","stroke-width":1.5});
    slice.style.cursor="pointer";
    slice.addEventListener("mouseenter",e=>showTip(e,d.ticker+" "+d.name+"<br>权重 "+d.weight+"% - "+fmtPct(d.change)));
    slice.addEventListener("mouseleave",hideTip);
    svg.appendChild(slice);
    ang+=a;
  });
  svg.appendChild(svgEl("text",{x:cx,y:cy-6,"text-anchor":"middle",fill:TEXT,"font-size":14,"font-weight":800})).textContent="NDX";
  svg.appendChild(svgEl("text",{x:cx,y:cy+14,"text-anchor":"middle",fill:GLOW,"font-size":13,"font-weight":700})).textContent=fmtPct(DATA.index.change);
  // 外圈光晕
  svg.appendChild(svgEl("circle",{cx:cx,cy:cy,r:95,fill:"none",stroke:GLOW,"stroke-width":18,opacity:.08}));
  const leg=document.getElementById("stockLegend");
  data.slice(0,8).forEach(d=>{
    const item=document.createElement("div");item.className="legend-item";
    item.innerHTML='<span class="legend-dot" style="background:'+colorForChange(d.change)+'"></span><span>'+d.ticker+" "+fmtPct(d.change)+"</span>";
    leg.appendChild(item);
  });
})();

// 行业饼图
(function(){
  const svg=document.getElementById("sectorPie");
  const data=DATA.sectors;
  const total=data.reduce((a,b)=>a+b.weight,0);
  const cx=140,cy=130,r=90,ir=45;
  let ang=-Math.PI/2;
  data.forEach(d=>{
    const a=(d.weight/total)*Math.PI*2;
    const x1=cx+r*Math.cos(ang),y1=cy+r*Math.sin(ang);
    const x2=cx+r*Math.cos(ang+a),y2=cy+r*Math.sin(ang+a);
    const ix1=cx+ir*Math.cos(ang),iy1=cy+ir*Math.sin(ang);
    const ix2=cx+ir*Math.cos(ang+a),iy2=cy+ir*Math.sin(ang+a);
    const large=a>Math.PI?1:0;
    const path="M "+ix1+" "+iy1+" L "+x1+" "+y1+" A "+r+" "+r+" 0 "+large+" 1 "+x2+" "+y2+" L "+ix2+" "+iy2+" A "+ir+" "+ir+" 0 "+large+" 0 "+ix1+" "+iy1;
    const fill=colorForChange(d.change);
    const slice=svgEl("path",{d:path,fill:fill,opacity:.8,stroke:"var(--bg)","stroke-width":1.5});
    slice.style.cursor="pointer";
    slice.addEventListener("mouseenter",e=>showTip(e,d.name+"<br>权重 "+d.weight+"% - "+d.count+"只 - 平均 "+fmtPct(d.change)));
    slice.addEventListener("mouseleave",hideTip);
    svg.appendChild(slice);
    ang+=a;
  });
  svg.appendChild(svgEl("text",{x:cx,y:cy-6,"text-anchor":"middle",fill:TEXT,"font-size":14,"font-weight":800})).textContent="行业";
  // 外圈光晕
  svg.appendChild(svgEl("circle",{cx:cx,cy:cy,r:95,fill:"none",stroke:GLOW,"stroke-width":18,opacity:.08}));
  const leg=document.getElementById("sectorLegend");
  data.forEach(d=>{
    const item=document.createElement("div");item.className="legend-item";
    item.innerHTML='<span class="legend-dot" style="background:'+colorForChange(d.change)+'"></span><span>'+d.name+" "+d.weight+"%</span>";
    leg.appendChild(item);
  });
})();

// 涨跌分布柱图
(function(){
  const svg=document.getElementById("distChart");
  const labels=DATA.bins.labels;
  const counts=DATA.bins.counts;
  const max=Math.max(...counts);
  const W=400,H=220,padL=40,padB=30,padT=20,padR=20;
  const bw=(W-padL-padR)/labels.length-4;
  for(let i=0;i<=4;i++){const y=padT+(H-padT-padB)*(1-i/4);svg.appendChild(svgEl("line",{x1:padL,y1:y,x2:W-padR,y2:y,stroke:BORDER,"stroke-width":.5}));svg.appendChild(svgEl("text",{x:padL-6,y:y+4,"text-anchor":"end",fill:TEXT4,"font-size":10})).textContent=Math.round(max*i/4)}
  labels.forEach((lbl,i)=>{
    const h=(counts[i]/max)*(H-padT-padB);
    const x=padL+i*(W-padL-padR)/labels.length+2;
    const y=H-padB-h;
    const isUp=i>=4;
    const bar=svgEl("rect",{x:x,y:y,width:bw,height:h||1,rx:4,fill:isUp?RISE:FALL,opacity:.9});
    bar.style.cursor="pointer";
    bar.addEventListener("mouseenter",e=>showTip(e,lbl+": "+counts[i]+"只"));
    bar.addEventListener("mouseleave",hideTip);
    svg.appendChild(bar);
    svg.appendChild(svgEl("text",{x:x+bw/2,y:H-padB+14,"text-anchor":"middle",fill:TEXT2,"font-size":10,"font-weight":600})).textContent=lbl;
    if(counts[i]>0){svg.appendChild(svgEl("text",{x:x+bw/2,y:y-6,"text-anchor":"middle",fill:isUp?RISE:FALL,"font-size":11,"font-weight":700})).textContent=counts[i]}
  });
  const zeroX=padL+4*(W-padL-padR)/labels.length;
  svg.appendChild(svgEl("line",{x1:zeroX,y1:padT,x2:zeroX,y2:H-padB,stroke:TEXT,"stroke-width":1,"stroke-dasharray":"4,4",opacity:.3}));
})();

// 行业柱图 - 零轴居中，上涨文字在左bar在右，下跌文字在右bar在左
(function(){
  const svg = document.getElementById("sectorBar");
  const data = DATA.sectors
    .filter(d => typeof d.change === 'number' && !isNaN(d.change))
    .map(d => ({...d}));

  if(data.length === 0){
    svg.appendChild(svgEl("text", {x:200, y:160, "text-anchor":"middle", fill:TEXT4, "font-size":14}))
       .textContent = "行业数据暂缺";
    return;
  }

  data.sort((a,b) => b.change - a.change);
  const W = 400, H = 320, padT = 16, padB = 16, textGap = 60;
  const zeroX = W / 2;
  const maxC = Math.max(...data.map(d => Math.abs(d.change)), 0.01);
  const scale = (W / 2 - textGap - 10) / maxC;
  const rowH = (H - padT - padB) / data.length;
  const barH = Math.min(rowH - 10, 22);

  // 零轴线
  svg.appendChild(svgEl("line", {
    x1: zeroX, y1: padT, x2: zeroX, y2: H - padB,
    stroke: BORDER, "stroke-width": 1, "stroke-dasharray": "3,3", opacity: .5
  }));

  data.forEach((d, i) => {
    const y = padT + i * rowH + (rowH - barH) / 2;
    const w = Math.max(Math.abs(d.change) * scale, 3);
    const isUp = d.change >= 0;
    const c = colorForChange(d.change);
    const x = isUp ? zeroX : zeroX - w;

    const bar = svgEl("rect", {
      x: x, y: y, width: w, height: barH, rx: 3,
      fill: c, opacity: .9
    });
    bar.style.cursor = "pointer";
    bar.addEventListener("mouseenter", e => showTip(e, d.name + "<br>平均 " + fmtPct(d.change)));
    bar.addEventListener("mouseleave", hideTip);
    svg.appendChild(bar);

    if(isUp){
      // 上涨：行业名在左(zero轴左侧)，数值在bar右侧
      svg.appendChild(svgEl("text", {
        x: zeroX - 8, y: y + barH/2 + 4,
        "text-anchor": "end", fill: TEXT2, "font-size": 11, "font-weight": 600
      })).textContent = d.name;
      svg.appendChild(svgEl("text", {
        x: zeroX + w + 6, y: y + barH/2 + 4,
        "text-anchor": "start", fill: c, "font-size": 11, "font-weight": 700
      })).textContent = fmtPct(d.change);
    } else {
      // 下跌：数值在bar左侧，行业名在右(zero轴右侧)
      svg.appendChild(svgEl("text", {
        x: zeroX - w - 6, y: y + barH/2 + 4,
        "text-anchor": "end", fill: c, "font-size": 11, "font-weight": 700
      })).textContent = fmtPct(d.change);
      svg.appendChild(svgEl("text", {
        x: zeroX + 8, y: y + barH/2 + 4,
        "text-anchor": "start", fill: TEXT2, "font-size": 11, "font-weight": 600
      })).textContent = d.name;
    }
  });
})();

// 走势线图
(function(){
  const svg=document.getElementById("trendLine");
  const data=DATA.history;
  if(data.length<2){svg.appendChild(svgEl("text",{x:400,y:120,"text-anchor":"middle",fill:TEXT4,"font-size":14})).textContent="历史数据暂缺";return}
  const W=800,H=240,padL=50,padB=30,padT=30,padR=30;
  const min=Math.min(...data),max=Math.max(...data);
  const range=max-min||1;
  const x=i=>padL+i*(W-padL-padR)/(data.length-1);
  const y=v=>padT+(max-v)/range*(H-padT-padB);
  let areaD="M "+x(0)+" "+y(data[0]);
  data.forEach((v,i)=>areaD+=" L "+x(i)+" "+y(v));
  areaD+=" L "+x(data.length-1)+" "+(H-padB)+" L "+x(0)+" "+(H-padB)+" Z";
  svg.appendChild(svgEl("path",{d:areaD,fill:GLOW,opacity:.06}));
  let lineD="M "+x(0)+" "+y(data[0]);
  data.forEach((v,i)=>lineD+=" L "+x(i)+" "+y(v));
  svg.appendChild(svgEl("path",{d:lineD,fill:"none",stroke:GLOW,"stroke-width":2.5,"stroke-linecap":"round","stroke-linejoin":"round"}));
  data.forEach((v,i)=>{
    const c=svgEl("circle",{cx:x(i),cy:y(v),r:3,fill:"var(--bg)",stroke:GLOW,"stroke-width":1.5});
    c.style.cursor="pointer";
    const daysAgo = data.length - i;
    const dayLabel = daysAgo === 1 ? "今日" : daysAgo + "天前";
    c.addEventListener("mouseenter",e=>showTip(e,dayLabel+"<br>收盘 "+Math.round(v).toLocaleString()));
    c.addEventListener("mouseleave",hideTip);
    svg.appendChild(c);
  });
  svg.appendChild(svgEl("text",{x:padL,y:H-8,fill:TEXT4,"font-size":10,"font-weight":600})).textContent="30日前";
  svg.appendChild(svgEl("text",{x:W-padR,y:H-8,"text-anchor":"end",fill:TEXT4,"font-size":10,"font-weight":600})).textContent="今日";
  svg.appendChild(svgEl("text",{x:padL-10,y:padT+4,"text-anchor":"end",fill:TEXT4,"font-size":10})).textContent=Math.round(max).toLocaleString();
  svg.appendChild(svgEl("text",{x:padL-10,y:H-padB,"text-anchor":"end",fill:TEXT4,"font-size":10})).textContent=Math.round(min).toLocaleString();
})();

// 股票网格
(function(){
  const grid=document.getElementById("stockGrid");
  DATA.stocks.forEach(s=>{
    const cell=document.createElement("div");
    cell.className="stock-cell";
    const c=colorForChange(s.change);
    cell.style.border="1px solid "+c+"30";
    cell.style.color=c;
    cell.innerHTML='<div style="font-weight:800;font-size:13px">'+s.ticker+'</div><div style="font-size:11px;opacity:.9">'+fmtPct(s.change)+"</div>";
    cell.addEventListener("mouseenter",e=>showTip(e,s.ticker+" "+s.name+"<br>权重 "+s.weight+"% - "+fmtPct(s.change)+" - "+s.sector));
    cell.addEventListener("mouseleave",hideTip);
    grid.appendChild(cell);
  });
})();

// 主题切换
function toggleTheme(){
  const root=document.documentElement;
  const icon=document.getElementById("theme-icon");
  if(root.classList.contains("light")){root.classList.remove("light");icon.innerHTML='<circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>'}
  else{root.classList.add("light");icon.innerHTML='<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>'}
}

// 跟随系统主题
if(window.matchMedia&&window.matchMedia("(prefers-color-scheme: light)").matches){
  document.documentElement.classList.add("light");
  document.getElementById("theme-icon").innerHTML='<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>';
}

const tip=document.getElementById("tooltip");
function showTip(e,html){
  tip.innerHTML=html;
  tip.style.opacity="1";
  // 先让浏览器渲染以获取正确尺寸
  const tw=tip.offsetWidth, th=tip.offsetHeight;
  let left=e.pageX-tw/2;
  let top=e.pageY-th-14;
  // 边界保护
  if(left<8)left=8;
  if(left+tw>document.documentElement.scrollWidth-8)left=document.documentElement.scrollWidth-tw-8;
  if(top<window.scrollY+8)top=e.pageY+14;
  tip.style.left=left+"px";tip.style.top=top+"px";
}
function hideTip(){tip.style.opacity="0"}
</script>
</body></html>"""


def get_existing_history_dates():
    """获取已存在的历史日期列表"""
    history_dir = os.path.join(OUTPUT_DIR, "history")
    if not os.path.exists(history_dir):
        return []
    dates = []
    for f in os.listdir(history_dir):
        if f.endswith(".json") and len(f) == 15:
            try:
                datetime.strptime(f[:10], "%Y-%m-%d")
                dates.append(f[:10])
            except:
                pass
    return sorted(dates)


def manage_history(data, html_content):
    """管理历史快照，滚动保留5个交易日。非交易日不生成新快照。"""
    history_dir = os.path.join(OUTPUT_DIR, "history")
    os.makedirs(history_dir, exist_ok=True)

    date_str = data["date"]

    # 保存 JSON 原始数据
    json_file = os.path.join(history_dir, f"{date_str}.json")
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    # 保存 HTML 快照
    history_file = os.path.join(history_dir, f"{date_str}.html")
    with open(history_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"  历史快照: {history_file}")

    # 扫描所有 JSON 文件，按日期排序
    files = []
    for f in os.listdir(history_dir):
        if f.endswith(".json") and len(f) == 15:
            try:
                d = datetime.strptime(f[:10], "%Y-%m-%d")
                files.append((d, f[:10]))
            except:
                pass

    files.sort(key=lambda x: x[0])

    # 保留最近5个，删除旧的
    removed = []
    while len(files) > 5:
        old_date = files[0][1]
        for ext in [".json", ".html"]:
            old_file = os.path.join(history_dir, old_date + ext)
            try:
                if os.path.exists(old_file):
                    os.remove(old_file)
                    removed.append(old_file)
            except Exception as e:
                print(f"  删除失败 {old_file}: {e}")
        files.pop(0)

    for r in removed:
        print(f"  删除旧快照: {os.path.basename(r)}")

    return [f[1] for f in files]


def generate_html(data, is_history=False, history_dates=None):
    jd = json.dumps(data, ensure_ascii=False)
    all_dates = sorted(set((history_dates or []) + [data["date"]]))
    hd = json.dumps(all_dates, ensure_ascii=False)
    html = HTML_TEMPLATE.replace("__DATA_JSON__", jd).replace("__HISTORY_DATES__", hd).replace("__IS_HISTORY__", "true" if is_history else "false")
    return html



def generate_summary(data):
    """本地生成行情总结，完全免费"""
    idx = data["index"]
    sectors = data["sectors"]
    stocks = data["stocks"]

    if not stocks or not sectors:
        return None

    sorted_stocks = sorted(stocks, key=lambda x: x["change"], reverse=True)
    top3_up = sorted_stocks[:3]
    top3_down = sorted_stocks[-3:][::-1]
    sorted_sectors = sorted(sectors, key=lambda x: x["change"], reverse=True)

    up_str = f"{idx['up']}涨{idx['down']}跌"
    trend = "收涨" if idx['change'] >= 0 else "收跌"
    pct = f"{'+' if idx['change'] >= 0 else ''}{idx['change']:.2f}%"

    # 情绪词
    if idx['change'] >= 1.5:
        mood = "强势"
    elif idx['change'] >= 0.5:
        mood = "偏强"
    elif idx['change'] >= -0.5:
        mood = "震荡"
    elif idx['change'] >= -1.5:
        mood = "偏弱"
    else:
        mood = "承压"

    # 行业描述
    lead_sector = sorted_sectors[0]
    lag_sector = sorted_sectors[-1]
    sector_text = f"{lead_sector['name']}领涨({lead_sector['change']:+.2f}%)"
    if lead_sector['name'] != lag_sector['name']:
        sector_text += f"，{lag_sector['name']}领跌({lag_sector['change']:+.2f}%)"

    # 龙头描述
    leaders = f"{top3_up[0]['ticker']}({top3_up[0]['change']:+.2f}%)"
    if len(top3_up) > 1:
        leaders += f"、{top3_up[1]['ticker']}({top3_up[1]['change']:+.2f}%)"

    # 组装
    lines = [
        f"纳指100今日{trend}{pct}，{up_str}，整体走势{mood}。",
        f"行业层面，{sector_text}。",
        f"个股方面，{leaders}表现亮眼；{top3_down[0]['ticker']}({top3_down[0]['change']:+.2f}%)承压。",
    ]

    # 展望
    if idx['change'] >= 1 and idx['up'] >= 70:
        lines.append("市场情绪积极，短期有望延续强势。")
    elif idx['change'] <= -1 and idx['down'] >= 70:
        lines.append("避险情绪升温，短期或继续震荡整理。")
    else:
        lines.append("板块分化明显，建议关注结构性机会。")

    summary = "".join(lines)
    print(f"  行情总结: {summary[:60]}...")
    return summary


def fmt_pct(c):
    return f"{'+' if c >= 0 else ''}{c:.2f}%"

def main():
    print("=" * 50)
    print("纳指100 Dashboard 数据更新")
    print("=" * 50)
    ensure_dir()
    print("[1/4] 抓取数据...")
    data = build_data()

    # 检查数据质量：成分股少于80只视为非交易日/数据异常，不更新历史快照
    is_trading_day = data["index"]["total"] >= 80

    print("[2/4] 生成临时 HTML...")
    temp_html = generate_html(data, is_history=False, history_dates=get_existing_history_dates())

    history_dates = get_existing_history_dates()
    if is_trading_day:
        print("[3/4] 管理历史快照...")
        history_dates = manage_history(data, temp_html)
        print("  保留日期: " + str(history_dates))
    else:
        print("[3/4] 数据不完整，跳过历史快照更新")

    print("[4/4] 生成最终页面...")

    # 生成 index.html（最新）
    html = generate_html(data, is_history=False, history_dates=history_dates)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print("  输出: " + OUTPUT_FILE)

    # 重新生成所有历史页面（更新导航链接）
    if history_dates:
        history_dir = os.path.join(OUTPUT_DIR, "history")
        for date_str in history_dates:
            json_file = os.path.join(history_dir, date_str + ".json")
            if not os.path.exists(json_file):
                continue
            with open(json_file, "r", encoding="utf-8") as f:
                old_data = json.load(f)
            old_html = generate_html(old_data, is_history=True, history_dates=history_dates)
            with open(os.path.join(history_dir, date_str + ".html"), "w", encoding="utf-8") as f:
                f.write(old_html)
        print("  更新 " + str(len(history_dates)) + " 个历史页面导航")

    print("完成！日期: " + data["date"] + " | 成分股: " + str(data["index"]["total"]) + " 只 | 涨跌: " + str(data["index"]["change"]) + "%")
    return 0
if __name__ == "__main__":
    sys.exit(main())
