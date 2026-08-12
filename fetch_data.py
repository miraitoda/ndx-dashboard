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


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>纳指100 · NDX DASHBOARD</title>
<style>
:root{
  --bg-deep:#0a0520;
  --bg-mid:#120a2e;
  --bg-surface:rgba(18,10,46,0.75);
  --neon:#a3ff12;
  --neon-dim:rgba(163,255,18,0.6);
  --neon-faint:rgba(163,255,18,0.15);
  --neon-glow:rgba(163,255,18,0.08);
  --rise:#00ff88;
  --fall:#ff3366;
  --text:#e8e8e8;
  --text-secondary:#8888aa;
  --text-tertiary:#444466;
  --border:rgba(163,255,18,0.12);
  --border-strong:rgba(163,255,18,0.25);
}
.light{
  --bg-deep:#f0f0f5;
  --bg-mid:#e8e8f0;
  --bg-surface:rgba(255,255,255,0.85);
  --neon:#2d9e00;
  --neon-dim:rgba(45,158,0,0.7);
  --neon-faint:rgba(45,158,0,0.12);
  --neon-glow:rgba(45,158,0,0.06);
  --rise:#089981;
  --fall:#f23645;
  --text:#1a1a2e;
  --text-secondary:#555577;
  --text-tertiary:#9999aa;
  --border:rgba(45,158,0,0.15);
  --border-strong:rgba(45,158,0,0.3);
}
*{box-sizing:border-box;margin:0;padding:0}
body{
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue","PingFang SC","Microsoft YaHei",sans-serif;
  background:var(--bg-deep);
  color:var(--text);
  line-height:1.5;
  overflow-x:hidden;
}

/* ===== 霓虹网格背景层 ===== */
.grid-bg{
  position:fixed;
  inset:0;
  background:
    linear-gradient(rgba(163,255,18,0.04) 1px,transparent 1px),
    linear-gradient(90deg,rgba(163,255,18,0.04) 1px,transparent 1px),
    linear-gradient(180deg,#0a0520 0%,#120a2e 100%);
  background-size:40px 40px,40px 40px,100% 100%;
  z-index:0;
  animation:gridPulse 4s ease-in-out infinite;
}

/* 底部透视网格 */
.floor-grid{
  position:fixed;
  bottom:0;
  left:-20%;
  right:-20%;
  height:180px;
  background:
    linear-gradient(0deg,rgba(163,255,18,0.07) 1px,transparent 1px),
    linear-gradient(90deg,rgba(163,255,18,0.07) 1px,transparent 1px);
  background-size:30px 30px,30px 30px;
  transform:perspective(500px) rotateX(60deg);
  transform-origin:bottom center;
  opacity:0.35;
  z-index:0;
  animation:floorFlow 10s linear infinite;
  pointer-events:none;
}

/* 扫描线 */
.scan-line{
  position:fixed;
  left:0;
  right:0;
  height:2px;
  background:linear-gradient(90deg,transparent,var(--neon),transparent);
  z-index:1000;
  animation:scanMove 4s linear infinite;
  box-shadow:0 0 30px var(--neon);
  pointer-events:none;
}

/* 浮动粒子 */
.particle{
  position:fixed;
  background:var(--neon);
  border-radius:50%;
  z-index:0;
  pointer-events:none;
}

/* ===== 布局 ===== */
.container{
  position:relative;
  z-index:1;
  max-width:1200px;
  margin:0 auto;
  padding:24px;
}

/* ===== Toolbar ===== */
.toolbar{
  position:sticky;
  top:0;
  z-index:100;
  display:flex;
  justify-content:space-between;
  align-items:center;
  padding:12px 24px;
  background:rgba(10,5,32,0.88);
  backdrop-filter:blur(20px);
  border-bottom:1px solid var(--border);
  box-shadow:0 0 40px rgba(163,255,18,0.05);
}
.logo{
  font-size:18px;
  font-weight:800;
  color:var(--neon);
  letter-spacing:2px;
  text-shadow:0 0 10px rgba(163,255,18,0.3);
}
.logo span{
  color:var(--text-secondary);
  font-weight:500;
}
.nav-btns{display:flex;gap:8px}
.nav-btn{
  padding:6px 14px;
  border-radius:8px;
  border:1px solid var(--border);
  background:rgba(163,255,18,0.05);
  color:var(--text-secondary);
  font-size:13px;
  font-weight:600;
  cursor:pointer;
  transition:all 0.2s;
  font-family:inherit;
}
.nav-btn:hover:not(:disabled){
  border-color:var(--neon);
  color:var(--neon);
  background:rgba(163,255,18,0.1);
  box-shadow:0 0 15px rgba(163,255,18,0.15);
}
.nav-btn:disabled{opacity:0.3;cursor:not-allowed}
.icon-btn{
  display:flex;
  align-items:center;
  justify-content:center;
  width:36px;
  height:36px;
  border-radius:10px;
  border:1px solid var(--border);
  background:rgba(163,255,18,0.05);
  color:var(--text-secondary);
  cursor:pointer;
  transition:all 0.2s;
}
.icon-btn:hover{
  border-color:var(--neon);
  color:var(--neon);
  background:rgba(163,255,18,0.1);
  box-shadow:0 0 15px rgba(163,255,18,0.15);
}

/* ===== Ticker ===== */
.ticker-bar{
  width:100%;
  height:38px;
  background:rgba(10,5,32,0.92);
  border-bottom:1px solid var(--border);
  overflow:hidden;
  display:flex;
  align-items:center;
  position:relative;
  z-index:90;
}
.ticker-bar-bottom{
  position:fixed;
  bottom:0;
  left:0;
  z-index:90;
  width:100vw;
  border-bottom:none;
  border-top:1px solid var(--border);
}
.ticker-track{
  display:flex;
  white-space:nowrap;
  animation:tickerScroll 60s linear infinite;
}
.ticker-track-reverse{animation-direction:reverse}
.ticker-item{
  display:inline-flex;
  align-items:center;
  padding:0 16px;
  font-size:13px;
  font-weight:600;
  font-variant-numeric:tabular-nums;
  flex-shrink:0;
}
.ticker-name{color:var(--text-secondary);margin-right:6px}
.ticker-change{font-weight:700}
.ticker-sep{color:var(--border);margin-left:16px}

/* ===== Hero ===== */
.hero{
  position:relative;
  padding:48px 0 36px;
  margin-bottom:32px;
  text-align:center;
}
.hero h1{
  font-size:52px;
  font-weight:900;
  letter-spacing:-2px;
  color:var(--neon);
  text-shadow:0 0 20px rgba(163,255,18,0.3),0 0 60px rgba(163,255,18,0.1);
  margin-bottom:12px;
}
.hero .meta{
  display:inline-flex;
  align-items:center;
  gap:16px;
  font-size:14px;
  color:var(--text-secondary);
}
.hero .badge{
  font-size:11px;
  padding:4px 14px;
  border-radius:20px;
  background:rgba(163,255,18,0.08);
  color:var(--neon);
  border:1px solid var(--border);
  font-weight:700;
  letter-spacing:0.5px;
}

/* ===== AI Summary ===== */
.ai-summary{
  background:var(--bg-surface);
  border:1px solid var(--border);
  border-radius:16px;
  padding:22px 28px;
  margin-bottom:32px;
  position:relative;
  overflow:hidden;
  backdrop-filter:blur(10px);
  animation:glowPulse 3s ease-in-out infinite;
}
.ai-summary::before{
  content:"";
  position:absolute;
  top:0;
  left:0;
  right:0;
  height:2px;
  background:linear-gradient(90deg,transparent,var(--neon),transparent);
}
.ai-label{
  display:flex;
  align-items:center;
  gap:8px;
  font-size:12px;
  color:var(--neon);
  font-weight:700;
  margin-bottom:10px;
  text-transform:uppercase;
  letter-spacing:1px;
}
.ai-summary p{
  margin:0;
  font-size:15px;
  line-height:1.7;
  color:var(--text-secondary);
  font-weight:500;
}
.chart-summary{
  margin-top:14px;
  padding:12px 16px;
  border-radius:10px;
  background:rgba(163,255,18,0.03);
  border-left:3px solid var(--neon);
  font-size:13px;
  line-height:1.6;
  color:var(--text-secondary);
  font-weight:500;
}

/* ===== KPI ===== */
.kpi-row{
  display:grid;
  grid-template-columns:repeat(4,1fr);
  gap:16px;
  margin-bottom:32px;
}
.kpi{
  background:var(--bg-surface);
  border:1px solid var(--border);
  border-radius:16px;
  padding:28px 24px;
  position:relative;
  overflow:hidden;
  backdrop-filter:blur(10px);
  transition:all 0.3s ease;
  animation:glowPulse 3s ease-in-out infinite;
}
.kpi:hover{
  transform:translateY(-3px);
  border-color:var(--border-strong);
  box-shadow:0 8px 32px rgba(163,255,18,0.1),0 0 20px rgba(163,255,18,0.05);
}
.kpi::before{
  content:"";
  position:absolute;
  top:0;
  left:0;
  right:0;
  height:2px;
  background:linear-gradient(90deg,transparent,var(--neon),transparent);
}
.kpi-label{
  font-size:11px;
  color:var(--text-tertiary);
  margin-bottom:12px;
  text-transform:uppercase;
  letter-spacing:2px;
  font-weight:700;
}
.kpi-value{
  font-size:42px;
  font-weight:900;
  font-variant-numeric:tabular-nums;
  line-height:1;
  letter-spacing:-1.5px;
  color:var(--text);
  animation:numberGlow 2s ease-in-out infinite;
}
.kpi-sub{
  font-size:16px;
  margin-top:12px;
  font-weight:700;
  font-variant-numeric:tabular-nums;
}
.kpi-sub.up{color:var(--rise);text-shadow:0 0 10px rgba(0,255,136,0.3)}
.kpi-sub.down{color:var(--fall);text-shadow:0 0 10px rgba(255,51,102,0.3)}

/* ===== Charts ===== */
.charts-row{
  display:grid;
  grid-template-columns:1fr 1fr;
  gap:20px;
  margin-bottom:32px;
}
.chart-box{
  background:var(--bg-surface);
  border:1px solid var(--border);
  border-radius:20px;
  padding:28px;
  position:relative;
  overflow:hidden;
  backdrop-filter:blur(10px);
  transition:all 0.3s ease;
  animation:glowPulse 3s ease-in-out infinite;
}
.chart-box:hover{
  transform:translateY(-2px);
  border-color:var(--border-strong);
  box-shadow:0 8px 32px rgba(163,255,18,0.08);
}
.chart-box::before{
  content:"";
  position:absolute;
  top:0;
  left:0;
  right:0;
  height:2px;
  background:linear-gradient(90deg,transparent,var(--neon),transparent);
}
.chart-title{
  font-size:18px;
  font-weight:800;
  margin-bottom:6px;
  color:var(--text);
  letter-spacing:-0.3px;
}
.chart-sub{
  font-size:12px;
  color:var(--text-tertiary);
  margin-bottom:16px;
  font-weight:500;
}
.full-row{margin-bottom:32px}
.legend{
  display:flex;
  flex-wrap:wrap;
  gap:10px 18px;
  margin-top:14px;
  font-size:12px;
}
.legend-item{
  display:flex;
  align-items:center;
  gap:6px;
  color:var(--text-secondary);
  font-weight:600;
}
.legend-dot{width:10px;height:10px;border-radius:3px}

/* ===== Stock Grid ===== */
.stock-grid{
  display:grid;
  grid-template-columns:repeat(auto-fill,minmax(95px,1fr));
  gap:6px;
  margin-top:14px;
}
.stock-cell{
  padding:8px 10px;
  border-radius:10px;
  font-size:12px;
  text-align:center;
  cursor:pointer;
  transition:all 0.15s;
  background:rgba(163,255,18,0.03);
  border:1px solid var(--border);
  font-weight:700;
}
.stock-cell:hover{
  transform:translateY(-3px) scale(1.02);
  box-shadow:0 8px 24px rgba(163,255,18,0.15);
  border-color:var(--neon);
}

/* ===== Footer ===== */
.footer{
  text-align:center;
  font-size:12px;
  color:var(--text-tertiary);
  margin-top:40px;
  padding:24px;
  border-top:1px solid var(--border);
}

/* ===== Tooltip ===== */
.tooltip{
  position:absolute;
  background:rgba(18,10,46,0.95);
  border:1px solid var(--border);
  border-radius:10px;
  padding:10px 14px;
  font-size:12px;
  color:var(--text);
  pointer-events:none;
  opacity:0;
  transition:opacity .15s;
  z-index:1000;
  box-shadow:0 4px 20px rgba(0,0,0,0.3),0 0 15px rgba(163,255,18,0.1);
  backdrop-filter:blur(10px);
  white-space:nowrap;
}

/* ===== Animations ===== */
@keyframes gridPulse{
  0%,100%{opacity:1}
  50%{opacity:0.6}
}
@keyframes scanMove{
  0%{top:0;opacity:0}
  10%{opacity:1}
  90%{opacity:1}
  100%{top:100vh;opacity:0}
}
@keyframes floorFlow{
  0%{background-position:0 0,0 0}
  100%{background-position:0 30px,30px 0}
}
@keyframes glowPulse{
  0%,100%{box-shadow:0 0 5px rgba(163,255,18,0.05),inset 0 0 5px rgba(163,255,18,0.02)}
  50%{box-shadow:0 0 20px rgba(163,255,18,0.12),inset 0 0 10px rgba(163,255,18,0.05)}
}
@keyframes numberGlow{
  0%,100%{text-shadow:0 0 5px rgba(163,255,18,0.2)}
  50%{text-shadow:0 0 15px rgba(163,255,18,0.4),0 0 30px rgba(163,255,18,0.1)}
}
@keyframes tickerScroll{
  0%{transform:translateX(0)}
  100%{transform:translateX(-50%)}
}
@keyframes floatParticle{
  0%{opacity:0;transform:translateY(0) scale(0)}
  20%{opacity:0.8;transform:translateY(-10px) scale(1)}
  80%{opacity:0.4;transform:translateY(-50px) scale(0.7)}
  100%{opacity:0;transform:translateY(-80px) scale(0)}
}

/* ===== Responsive ===== */
@media(max-width:720px){
  .charts-row{grid-template-columns:1fr}
  .kpi-row{grid-template-columns:repeat(2,1fr)}
  .kpi-value{font-size:32px}
  .hero h1{font-size:36px}
  .container{padding:16px}
}
</style></head><body>

<!-- 背景特效层 -->
<div class="grid-bg"></div>
<div class="floor-grid"></div>
<div class="scan-line"></div>
<div class="particle" style="width:3px;height:3px;top:15%;left:20%;animation:floatParticle 6s ease-in-out infinite"></div>
<div class="particle" style="width:2px;height:2px;top:35%;left:75%;animation:floatParticle 8s ease-in-out infinite 1s"></div>
<div class="particle" style="width:4px;height:4px;top:55%;left:45%;animation:floatParticle 7s ease-in-out infinite 2s"></div>
<div class="particle" style="width:2px;height:2px;top:70%;left:85%;animation:floatParticle 9s ease-in-out infinite 3s"></div>
<div class="particle" style="width:3px;height:3px;top:25%;left:10%;animation:floatParticle 5s ease-in-out infinite 1.5s"></div>

<!-- 顶部行情条 -->
<div class="ticker-bar" id="tickerTop"></div>

<!-- Toolbar -->
<div class="toolbar">
  <div style="display:flex;align-items:center;gap:16px">
    <div class="logo">NDX <span>DASHBOARD</span></div>
    <div class="nav-btns">
      <button class="nav-btn" id="btnPrev" disabled>← 前一日</button>
      <button class="nav-btn" id="btnToday" style="display:none">今天</button>
      <button class="nav-btn" id="btnNext" disabled>后一日 →</button>
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:10px">
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
  <!-- Hero -->
  <div class="hero">
    <h1>纳斯达克100</h1>
    <div class="meta">
      <span id="dateStr"></span>
      <span class="badge" id="statusBadge">已收盘</span>
    </div>
  </div>

  <!-- AI Summary -->
  <div class="ai-summary" id="aiSummaryBox" style="display:none">
    <div class="ai-label">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
      <span>行情总结</span>
    </div>
    <p id="aiSummaryText"></p>
  </div>

  <!-- KPI Row -->
  <div class="kpi-row">
    <div class="kpi" id="kpiPrice">
      <div class="kpi-label">指数点位</div>
      <div class="kpi-value" id="idxPrice">--</div>
      <div class="kpi-sub" id="idxChange">--</div>
    </div>
    <div class="kpi" id="kpiUpDown">
      <div class="kpi-label">涨跌家数</div>
      <div class="kpi-value" style="font-size:28px" id="upDown">--</div>
      <div class="kpi-sub" style="color:var(--text-tertiary)">涨 / 跌</div>
    </div>
    <div class="kpi" id="kpiTrend">
      <div class="kpi-label">30日走势</div>
      <div class="kpi-value" id="trend30d">--</div>
      <div class="kpi-sub" style="color:var(--text-tertiary)" id="trendRange">--</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">数据状态</div>
      <div class="kpi-value" style="font-size:28px" id="dataStatus">正常</div>
      <div class="kpi-sub" style="color:var(--text-tertiary)">成分股 <span id="stockCount">--</span> 只</div>
    </div>
  </div>

  <!-- Charts Row 1: Pies -->
  <div class="charts-row">
    <div class="chart-box">
      <div class="chart-title">个股权重饼图（Top 15 + 其他）</div>
      <div class="chart-sub">绿色=上涨，红色=下跌，面积=权重</div>
      <svg id="stockPie" viewBox="0 0 320 280" style="width:100%;height:auto"></svg>
      <div class="legend" id="stockLegend"></div>
      <div class="chart-summary" id="aiStocksBox" style="display:none"><p></p></div>
    </div>
    <div class="chart-box">
      <div class="chart-title">行业权重饼图</div>
      <div class="chart-sub">绿色=上涨，红色=下跌，面积=权重</div>
      <svg id="sectorPie" viewBox="0 0 320 280" style="width:100%;height:auto"></svg>
      <div class="legend" id="sectorLegend"></div>
      <div class="chart-summary" id="aiSectorsBox" style="display:none"><p></p></div>
    </div>
  </div>

  <!-- Charts Row 2: Bars -->
  <div class="charts-row">
    <div class="chart-box">
      <div class="chart-title">涨跌分布柱图</div>
      <div class="chart-sub">100支成分股按涨跌幅区间分布</div>
      <svg id="distChart" viewBox="0 0 400 220" style="width:100%;height:auto"></svg>
      <div class="chart-summary" id="aiDistBox" style="display:none"><p></p></div>
    </div>
    <div class="chart-box">
      <div class="chart-title">行业表现柱图</div>
      <div class="chart-sub">各行业按权重加权平均涨跌幅</div>
      <svg id="sectorBar" viewBox="0 0 400 320" style="width:100%;height:auto"></svg>
      <div class="chart-summary" id="aiIndustryBox" style="display:none"><p></p></div>
    </div>
  </div>

  <!-- Trend Line -->
  <div class="full-row chart-box">
    <div class="chart-title">纳指100 · 近30日走势</div>
    <div class="chart-sub">每日收盘价连线</div>
    <svg id="trendLine" viewBox="0 0 800 240" style="width:100%;height:auto"></svg>
    <div class="chart-summary" id="aiTrendBox" style="display:none"><p></p></div>
  </div>

  <!-- Stock Grid -->
  <div class="chart-box">
    <div class="chart-title">100支成分股涨跌一览</div>
    <div class="chart-sub">鼠标悬停查看详情</div>
    <div class="stock-grid" id="stockGrid"></div>
  </div>

  <div class="footer">数据来自 Yahoo Finance · 每日自动更新 · 仅供参考不构成投资建议</div>
</div>

<!-- Bottom Ticker -->
<div class="ticker-bar ticker-bar-bottom" id="tickerBottom"></div>

<!-- Tooltip -->
<div class="tooltip" id="tooltip"></div>

<script>
const DATA = __DATA_JSON__;

// ===== 霓虹风格颜色系统 =====
const RISE = "#00ff88";
const FALL = "#ff3366";
const TEXT = "#e8e8e8";
const TEXT2 = "#8888aa";
const TEXT4 = "#444466";
const BORDER = "rgba(163,255,18,0.12)";
const NEON = "#a3ff12";

// 根据当日涨跌设置全局光晕
const GLOW = DATA.index.change >= 0 ? RISE : FALL;

// KPI 卡片涨跌标记
const kpiPrice = document.getElementById("kpiPrice");
const kpiUpDown = document.getElementById("kpiUpDown");
const kpiTrend = document.getElementById("kpiTrend");
if(DATA.index.change >= 0){
  kpiPrice.classList.add("up"); kpiUpDown.classList.add("up"); kpiTrend.classList.add("up");
} else {
  kpiPrice.classList.add("down"); kpiUpDown.classList.add("down"); kpiTrend.classList.add("down");
}

function colorForChange(c){ return c >= 0 ? RISE : FALL; }
function fmtPct(c){ return (c >= 0 ? "+" : "") + c.toFixed(2) + "%"; }
function svgEl(tag, attrs){
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for(let k in attrs) el.setAttribute(k, attrs[k]);
  return el;
}

const HISTORY_DATES = __HISTORY_DATES__;
const IS_HISTORY = __IS_HISTORY__;

// ===== 美股开盘状态判断 =====
function getMarketStatus(){
  const now = new Date();
  const utc = now.getTime() + now.getTimezoneOffset() * 60000;
  const beijing = new Date(utc + 8 * 3600000);
  const day = beijing.getDay();
  if(day === 0 || day === 6) return "已收盘";

  const year = beijing.getFullYear();
  const dstStart = new Date(year, 2, 14 - new Date(year, 2, 1).getDay());
  const dstEnd = new Date(year, 10, 7 - new Date(year, 10, 1).getDay());
  const isDST = beijing >= dstStart && beijing < dstEnd;

  const hour = beijing.getHours();
  const minute = beijing.getMinutes();
  const timeVal = hour + minute / 60;
  const openTime = isDST ? 21.5 : 22.5;
  const closeTime = isDST ? 28 : 29;

  if(timeVal >= openTime && timeVal < closeTime) return "开盘中";
  return "已收盘";
}

// ===== 前后日导航 =====
(function(){
  const btnPrev = document.getElementById("btnPrev");
  const btnNext = document.getElementById("btnNext");
  const btnToday = document.getElementById("btnToday");
  if(!btnPrev || !btnNext) return;

  const path = window.location.pathname;
  const isHistory = path.includes("/history/");
  let currentDate;

  if(isHistory){
    const m = path.match(/history\/(\d{4}-\d{2}-\d{2})/);
    currentDate = m ? m[1] : DATA.date;
    if(btnToday){
      btnToday.style.display = "inline-block";
      btnToday.onclick = () => location.href = "../index.html";
    }
  } else {
    currentDate = DATA.date;
  }

  const idx = HISTORY_DATES.indexOf(currentDate);
  if(idx === -1) return;

  if(idx > 0){
    const prevDate = HISTORY_DATES[idx - 1];
    btnPrev.disabled = false;
    btnPrev.onclick = () => {
      location.href = isHistory ? "./" + prevDate + ".html" : "./history/" + prevDate + ".html";
    };
  }

  if(idx < HISTORY_DATES.length - 1){
    const nextDate = HISTORY_DATES[idx + 1];
    btnNext.disabled = false;
    if(nextDate === DATA.date && isHistory){
      btnNext.onclick = () => location.href = "../index.html";
    } else {
      btnNext.onclick = () => {
        location.href = isHistory ? "./" + nextDate + ".html" : "./history/" + nextDate + ".html";
      };
    }
  }
})();

// ===== 填充 KPI =====
(function(){
  const idx = DATA.index;
  document.getElementById("dateStr").textContent = DATA.date;
  document.getElementById("statusBadge").textContent = getMarketStatus();
  document.getElementById("idxPrice").textContent = idx.price ? idx.price.toLocaleString() : "估算中";
  const chgEl = document.getElementById("idxChange");
  chgEl.textContent = fmtPct(idx.change) + (idx.price ? " (" + (idx.price - idx.prev_close).toFixed(2) + ")" : "");
  chgEl.className = "kpi-sub " + (idx.change >= 0 ? "up" : "down");
  document.getElementById("upDown").innerHTML = idx.up + ' <span style="color:var(--text-tertiary)">/</span> ' + idx.down;
  document.getElementById("stockCount").textContent = idx.total;

  const hist = DATA.history;
  if(hist.length >= 2){
    const c30 = ((hist[hist.length - 1] - hist[0]) / hist[0] * 100).toFixed(2);
    const t30 = document.getElementById("trend30d");
    t30.textContent = (c30 >= 0 ? "+" : "") + c30 + "%";
    t30.style.color = c30 >= 0 ? RISE : FALL;
    document.getElementById("trendRange").textContent = Math.round(hist[0]).toLocaleString() + " -> " + Math.round(hist[hist.length - 1]).toLocaleString();
  } else {
    document.getElementById("trend30d").textContent = "--";
    document.getElementById("trendRange").textContent = "数据暂缺";
  }

  if(idx.total < 80){
    document.getElementById("dataStatus").textContent = "部分缺失";
    document.getElementById("dataStatus").style.color = FALL;
  }
})();

// ===== AI 行情总结 - 6个独立总结 =====
(function(){
  const summaries = [
    {key: "ai_summary", box: "aiSummaryBox", text: "aiSummaryText"},
    {key: "ai_stocks", box: "aiStocksBox", text: null},
    {key: "ai_sectors", box: "aiSectorsBox", text: null},
    {key: "ai_distribution", box: "aiDistBox", text: null},
    {key: "ai_industry", box: "aiIndustryBox", text: null},
    {key: "ai_trend", box: "aiTrendBox", text: null}
  ];
  summaries.forEach(s => {
    if(DATA[s.key]){
      const box = document.getElementById(s.box);
      if(box){
        const el = s.text ? document.getElementById(s.text) : box.querySelector("p");
        if(el) el.textContent = DATA[s.key];
        box.style.display = "block";
      }
    }
  });
})();

// ===== 个股饼图 =====
(function(){
  const svg = document.getElementById("stockPie");
  const data = DATA.pie_stocks;
  const total = data.reduce((a,b) => a + b.weight, 0);
  const cx = 140, cy = 130, r = 90, ir = 45;
  let ang = -Math.PI / 2;

  data.forEach(d => {
    const a = (d.weight / total) * Math.PI * 2;
    const x1 = cx + r * Math.cos(ang), y1 = cy + r * Math.sin(ang);
    const x2 = cx + r * Math.cos(ang + a), y2 = cy + r * Math.sin(ang + a);
    const ix1 = cx + ir * Math.cos(ang), iy1 = cy + ir * Math.sin(ang);
    const ix2 = cx + ir * Math.cos(ang + a), iy2 = cy + ir * Math.sin(ang + a);
    const large = a > Math.PI ? 1 : 0;
    const path = "M " + ix1 + " " + iy1 + " L " + x1 + " " + y1 + " A " + r + " " + r + " 0 " + large + " 1 " + x2 + " " + y2 + " L " + ix2 + " " + iy2 + " A " + ir + " " + ir + " 0 " + large + " 0 " + ix1 + " " + iy1;
    const fill = colorForChange(d.change);
    const slice = svgEl("path", {d: path, fill: fill, opacity: 0.85, stroke: "var(--bg-deep)", "stroke-width": 1.5});
    slice.style.cursor = "pointer";
    slice.addEventListener("mouseenter", e => showTip(e, d.ticker + " " + d.name + "<br>权重 " + d.weight + "% - " + fmtPct(d.change)));
    slice.addEventListener("mouseleave", hideTip);
    svg.appendChild(slice);
    ang += a;
  });

  svg.appendChild(svgEl("text", {x: cx, y: cy - 6, "text-anchor": "middle", fill: TEXT, "font-size": 14, "font-weight": 800})).textContent = "NDX";
  svg.appendChild(svgEl("text", {x: cx, y: cy + 14, "text-anchor": "middle", fill: GLOW, "font-size": 13, "font-weight": 700})).textContent = fmtPct(DATA.index.change);

  // 外圈霓虹光晕
  svg.appendChild(svgEl("circle", {cx: cx, cy: cy, r: 95, fill: "none", stroke: GLOW, "stroke-width": 18, opacity: 0.08}));

  const leg = document.getElementById("stockLegend");
  data.slice(0, 8).forEach(d => {
    const item = document.createElement("div");
    item.className = "legend-item";
    item.innerHTML = '<span class="legend-dot" style="background:' + colorForChange(d.change) + '"></span><span>' + d.ticker + " " + fmtPct(d.change) + "</span>";
    leg.appendChild(item);
  });
})();

// ===== 行业饼图 =====
(function(){
  const svg = document.getElementById("sectorPie");
  const data = DATA.sectors;
  const total = data.reduce((a,b) => a + b.weight, 0);
  const cx = 140, cy = 130, r = 90, ir = 45;
  let ang = -Math.PI / 2;

  data.forEach(d => {
    const a = (d.weight / total) * Math.PI * 2;
    const x1 = cx + r * Math.cos(ang), y1 = cy + r * Math.sin(ang);
    const x2 = cx + r * Math.cos(ang + a), y2 = cy + r * Math.sin(ang + a);
    const ix1 = cx + ir * Math.cos(ang), iy1 = cy + ir * Math.sin(ang);
    const ix2 = cx + ir * Math.cos(ang + a), iy2 = cy + ir * Math.sin(ang + a);
    const large = a > Math.PI ? 1 : 0;
    const path = "M " + ix1 + " " + iy1 + " L " + x1 + " " + y1 + " A " + r + " " + r + " 0 " + large + " 1 " + x2 + " " + y2 + " L " + ix2 + " " + iy2 + " A " + ir + " " + ir + " 0 " + large + " 0 " + ix1 + " " + iy1;
    const fill = colorForChange(d.change);
    const slice = svgEl("path", {d: path, fill: fill, opacity: 0.8, stroke: "var(--bg-deep)", "stroke-width": 1.5});
    slice.style.cursor = "pointer";
    slice.addEventListener("mouseenter", e => showTip(e, d.name + "<br>权重 " + d.weight + "% - " + d.count + "只 - 平均 " + fmtPct(d.change)));
    slice.addEventListener("mouseleave", hideTip);
    svg.appendChild(slice);
    ang += a;
  });

  svg.appendChild(svgEl("text", {x: cx, y: cy - 6, "text-anchor": "middle", fill: TEXT, "font-size": 14, "font-weight": 800})).textContent = "行业";
  svg.appendChild(svgEl("circle", {cx: cx, cy: cy, r: 95, fill: "none", stroke: GLOW, "stroke-width": 18, opacity: 0.08}));

  const leg = document.getElementById("sectorLegend");
  data.forEach(d => {
    const item = document.createElement("div");
    item.className = "legend-item";
    item.innerHTML = '<span class="legend-dot" style="background:' + colorForChange(d.change) + '"></span><span>' + d.name + " " + d.weight + "%</span>";
    leg.appendChild(item);
  });
})();

// ===== 涨跌分布柱图 =====
(function(){
  const svg = document.getElementById("distChart");
  const labels = DATA.bins.labels;
  const counts = DATA.bins.counts;
  const max = Math.max(...counts);
  const W = 400, H = 220, padL = 40, padB = 30, padT = 20, padR = 20;
  const bw = (W - padL - padR) / labels.length - 4;

  for(let i = 0; i <= 4; i++){
    const y = padT + (H - padT - padB) * (1 - i / 4);
    svg.appendChild(svgEl("line", {x1: padL, y1: y, x2: W - padR, y2: y, stroke: "rgba(163,255,18,0.06)", "stroke-width": 0.5}));
    svg.appendChild(svgEl("text", {x: padL - 6, y: y + 4, "text-anchor": "end", fill: TEXT4, "font-size": 10})).textContent = Math.round(max * i / 4);
  }

  labels.forEach((lbl, i) => {
    const h = (counts[i] / max) * (H - padT - padB);
    const x = padL + i * (W - padL - padR) / labels.length + 2;
    const y = H - padB - h;
    const isUp = i >= 4;
    const bar = svgEl("rect", {x: x, y: y, width: bw, height: h || 1, rx: 4, fill: isUp ? RISE : FALL, opacity: 0.9});
    bar.style.cursor = "pointer";
    bar.addEventListener("mouseenter", e => showTip(e, lbl + ": " + counts[i] + "只"));
    bar.addEventListener("mouseleave", hideTip);
    svg.appendChild(bar);
    svg.appendChild(svgEl("text", {x: x + bw / 2, y: H - padB + 14, "text-anchor": "middle", fill: TEXT2, "font-size": 10, "font-weight": 600})).textContent = lbl;
    if(counts[i] > 0){
      svg.appendChild(svgEl("text", {x: x + bw / 2, y: y - 6, "text-anchor": "middle", fill: isUp ? RISE : FALL, "font-size": 11, "font-weight": 700})).textContent = counts[i];
    }
  });

  const zeroX = padL + 4 * (W - padL - padR) / labels.length;
  svg.appendChild(svgEl("line", {x1: zeroX, y1: padT, x2: zeroX, y2: H - padB, stroke: TEXT, "stroke-width": 1, "stroke-dasharray": "4,4", opacity: 0.3}));
})();

// ===== 行业表现柱图 - 零轴居中 =====
(function(){
  const svg = document.getElementById("sectorBar");
  const data = DATA.sectors
    .filter(d => typeof d.change === 'number' && !isNaN(d.change))
    .map(d => ({...d}));

  if(data.length === 0){
    svg.appendChild(svgEl("text", {x: 200, y: 160, "text-anchor": "middle", fill: TEXT4, "font-size": 14})).textContent = "行业数据暂缺";
    return;
  }

  data.sort((a,b) => b.change - a.change);
  const W = 400, H = 320, padT = 16, padB = 16, textGap = 60;
  const zeroX = W / 2;
  const maxC = Math.max(...data.map(d => Math.abs(d.change)), 0.01);
  const scale = (W / 2 - textGap - 10) / maxC;
  const rowH = (H - padT - padB) / data.length;
  const barH = Math.min(rowH - 10, 22);

  svg.appendChild(svgEl("line", {
    x1: zeroX, y1: padT, x2: zeroX, y2: H - padB,
    stroke: "rgba(163,255,18,0.1)", "stroke-width": 1, "stroke-dasharray": "3,3", opacity: 0.5
  }));

  data.forEach((d, i) => {
    const y = padT + i * rowH + (rowH - barH) / 2;
    const w = Math.max(Math.abs(d.change) * scale, 3);
    const isUp = d.change >= 0;
    const c = colorForChange(d.change);
    const x = isUp ? zeroX : zeroX - w;

    const bar = svgEl("rect", {x: x, y: y, width: w, height: barH, rx: 3, fill: c, opacity: 0.9});
    bar.style.cursor = "pointer";
    bar.addEventListener("mouseenter", e => showTip(e, d.name + "<br>平均 " + fmtPct(d.change)));
    bar.addEventListener("mouseleave", hideTip);
    svg.appendChild(bar);

    if(isUp){
      svg.appendChild(svgEl("text", {x: zeroX - 8, y: y + barH / 2 + 4, "text-anchor": "end", fill: TEXT2, "font-size": 11, "font-weight": 600})).textContent = d.name;
      svg.appendChild(svgEl("text", {x: zeroX + w + 6, y: y + barH / 2 + 4, "text-anchor": "start", fill: c, "font-size": 11, "font-weight": 700})).textContent = fmtPct(d.change);
    } else {
      svg.appendChild(svgEl("text", {x: zeroX - w - 6, y: y + barH / 2 + 4, "text-anchor": "end", fill: c, "font-size": 11, "font-weight": 700})).textContent = fmtPct(d.change);
      svg.appendChild(svgEl("text", {x: zeroX + 8, y: y + barH / 2 + 4, "text-anchor": "start", fill: TEXT2, "font-size": 11, "font-weight": 600})).textContent = d.name;
    }
  });
})();

// ===== 走势线图 =====
(function(){
  const svg = document.getElementById("trendLine");
  const data = DATA.history;
  if(data.length < 2){
    svg.appendChild(svgEl("text", {x: 400, y: 120, "text-anchor": "middle", fill: TEXT4, "font-size": 14})).textContent = "历史数据暂缺";
    return;
  }

  const W = 800, H = 240, padL = 50, padB = 30, padT = 30, padR = 30;
  const min = Math.min(...data), max = Math.max(...data);
  const range = max - min || 1;
  const x = i => padL + i * (W - padL - padR) / (data.length - 1);
  const y = v => padT + (max - v) / range * (H - padT - padB);

  let areaD = "M " + x(0) + " " + y(data[0]);
  data.forEach((v, i) => areaD += " L " + x(i) + " " + y(v));
  areaD += " L " + x(data.length - 1) + " " + (H - padB) + " L " + x(0) + " " + (H - padB) + " Z";

  svg.appendChild(svgEl("path", {d: areaD, fill: GLOW, opacity: 0.08}));

  let lineD = "M " + x(0) + " " + y(data[0]);
  data.forEach((v, i) => lineD += " L " + x(i) + " " + y(v));

  // 霓虹发光线条（双层）
  svg.appendChild(svgEl("path", {d: lineD, fill: "none", stroke: GLOW, "stroke-width": 4, opacity: 0.3, "stroke-linecap": "round", "stroke-linejoin": "round"}));
  svg.appendChild(svgEl("path", {d: lineD, fill: "none", stroke: GLOW, "stroke-width": 2, "stroke-linecap": "round", "stroke-linejoin": "round"}));

  data.forEach((v, i) => {
    const c = svgEl("circle", {cx: x(i), cy: y(v), r: 3, fill: "var(--bg-deep)", stroke: GLOW, "stroke-width": 1.5});
    c.style.cursor = "pointer";
    const daysAgo = data.length - i;
    const dayLabel = daysAgo === 1 ? "今日" : daysAgo + "天前";
    c.addEventListener("mouseenter", e => showTip(e, dayLabel + "<br>收盘 " + Math.round(v).toLocaleString()));
    c.addEventListener("mouseleave", hideTip);
    svg.appendChild(c);
  });

  svg.appendChild(svgEl("text", {x: padL, y: H - 8, fill: TEXT4, "font-size": 10, "font-weight": 600})).textContent = "30日前";
  svg.appendChild(svgEl("text", {x: W - padR, y: H - 8, "text-anchor": "end", fill: TEXT4, "font-size": 10, "font-weight": 600})).textContent = "今日";
  svg.appendChild(svgEl("text", {x: padL - 10, y: padT + 4, "text-anchor": "end", fill: TEXT4, "font-size": 10})).textContent = Math.round(max).toLocaleString();
  svg.appendChild(svgEl("text", {x: padL - 10, y: H - padB, "text-anchor": "end", fill: TEXT4, "font-size": 10})).textContent = Math.round(min).toLocaleString();
})();

// ===== 股票网格 =====
(function(){
  const grid = document.getElementById("stockGrid");
  DATA.stocks.forEach(s => {
    const cell = document.createElement("div");
    cell.className = "stock-cell";
    const c = colorForChange(s.change);
    cell.style.border = "1px solid " + c + "30";
    cell.style.color = c;
    cell.innerHTML = '<div style="font-weight:800;font-size:13px">' + s.ticker + '</div><div style="font-size:11px;opacity:.9">' + fmtPct(s.change) + "</div>";
    cell.addEventListener("mouseenter", e => showTip(e, s.ticker + " " + s.name + "<br>权重 " + s.weight + "% - " + fmtPct(s.change) + " - " + s.sector));
    cell.addEventListener("mouseleave", hideTip);
    grid.appendChild(cell);
  });
})();

// ===== 滚动行情条 =====
(function(){
  const topStocks = DATA.stocks.slice().sort((a,b) => Math.abs(b.change) - Math.abs(a.change));
  const bottomStocks = DATA.stocks.slice().sort(() => Math.random() - 0.5);

  function buildTicker(id, stocks, reverse){
    const bar = document.getElementById(id);
    if(!bar) return;
    const track = document.createElement('div');
    track.className = 'ticker-track' + (reverse ? ' ticker-track-reverse' : '');
    let html = '';
    stocks.forEach(s => {
      const c = colorForChange(s.change);
      html += '<span class="ticker-item"><span class="ticker-name">' + s.ticker + '</span><span class="ticker-change" style="color:' + c + '">' + fmtPct(s.change) + '</span><span class="ticker-sep">|</span></span>';
    });
    track.innerHTML = html + html;
    bar.appendChild(track);
  }
  buildTicker('tickerTop', topStocks, false);
  buildTicker('tickerBottom', bottomStocks, true);
})();

// ===== 主题切换 =====
function toggleTheme(){
  const root = document.documentElement;
  const icon = document.getElementById("theme-icon");
  if(root.classList.contains("light")){
    root.classList.remove("light");
    icon.innerHTML = '<circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>';
  } else {
    root.classList.add("light");
    icon.innerHTML = '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>';
  }
}

// 跟随系统主题
if(window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches){
  document.documentElement.classList.add("light");
  document.getElementById("theme-icon").innerHTML = '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>';
}

// ===== Tooltip =====
const tip = document.getElementById("tooltip");
function showTip(e, html){
  tip.innerHTML = html;
  tip.style.opacity = "1";
  const tw = tip.offsetWidth, th = tip.offsetHeight;
  let left = e.pageX - tw / 2;
  let top = e.pageY - th - 14;
  if(left < 8) left = 8;
  if(left + tw > document.documentElement.scrollWidth - 8) left = document.documentElement.scrollWidth - tw - 8;
  if(top < window.scrollY + 8) top = e.pageY + 14;
  tip.style.left = left + "px";
  tip.style.top = top + "px";
}
function hideTip(){ tip.style.opacity = "0"; }
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


import random

# 随机话术库
OVERVIEW_OPENINGS = [
    "纳指100今日{trend}{pct}，{up_str}，整体走势{mood}。",
    "今日纳指100{trend}{pct}，{up_str}，市场{mood}。",
    "纳指100收盘{trend}{pct}，{up_str}，全天{mood}运行。",
    "今日美股科技股{trend}{pct}，{up_str}，整体{mood}。",
]

OVERVIEW_SECTORS = [
    "行业层面，{sector_text}。",
    "板块方面，{sector_text}。",
    "从行业看，{sector_text}。",
    "分行业看，{sector_text}。",
]

OVERVIEW_STOCKS = [
    "个股方面，{leaders}表现亮眼；{laggards}承压。",
    "权重股中，{leaders}强势，{laggards}走弱。",
    "龙头表现分化，{leaders}领涨，{laggards}领跌。",
    "成分股中，{leaders}表现突出，{laggards}跌幅居前。",
]

OVERVIEW_OUTLOOKS = [
    "市场情绪积极，短期有望延续强势。",
    "避险情绪升温，短期或继续震荡整理。",
    "板块分化明显，建议关注结构性机会。",
    "资金轮动加速，短期或维持震荡格局。",
    "市场信心尚可，关注后续量能配合。",
    "多空分歧加大，建议控制仓位观望。",
]

STOCKS_TEMPLATES = [
    "权重股分化明显，{leaders}强势领涨，{laggards}大幅回调。指数整体{trend_text}。",
    "龙头表现割裂，{leaders}逆势走强，{laggards}承压下行。指数{trend_text}。",
    "成分股涨跌互现，{leaders}表现亮眼，{laggards}拖累指数。整体{trend_text}。",
]

SECTORS_TEMPLATES = [
    "行业轮动加速，{lead}获资金青睐，{lag}资金流出明显。板块分化加剧，结构性特征突出。",
    "板块分化显著，{lead}逆势走强，{lag}持续承压。资金呈现明显的避险偏好。",
    "从行业看，{lead}领涨，{lag}领跌。资金在板块间快速切换，轮动格局明显。",
]

DIST_TEMPLATES = [
    "市场情绪偏暖，普涨格局下{up}只个股上涨，仅{down}只下跌，赚钱效应较好。",
    "市场情绪偏冷，普跌格局下{down}只个股下跌，仅{up}只上涨，亏钱效应扩散。",
    "市场情绪分化，{up}涨{down}跌，暴涨{extreme_up}只、暴跌{extreme_down}只，结构性行情特征明显。",
    "涨跌家数接近，{up}涨{down}跌，市场处于均衡状态，等待方向选择。",
]

INDUSTRY_TEMPLATES = [
    "{lead}板块表现最强，{lag}板块承压。行业间分化显著，建议关注强势板块机会。",
    "{lead}逆势领涨，{lag}持续走弱。板块间资金博弈激烈，结构性机会与风险并存。",
    "行业表现分化，{lead}一枝独秀，{lag}跌幅居前。建议聚焦强势板块，回避弱势领域。",
]

TREND_TEMPLATES = [
    "近30日纳指100强势上行{c30:+.2f}%，趋势明确。近5日{recent5:+.2f}%，短期 momentum 良好，关注能否延续。",
    "近30日纳指100下行{c30:+.2f}%，趋势偏弱。近5日{recent5:+.2f}%，短期或存在超跌反弹机会。",
    "近30日纳指100区间震荡({c30:+.2f}%)，但近5日反弹{recent5:+.2f}%，短期有企稳迹象。",
    "近30日纳指100区间震荡({c30:+.2f}%)，近5日回调{recent5:+.2f}%，短期承压关注支撑。",
    "近30日纳指100横盘整理({c30:+.2f}%)，近5日波动有限{recent5:+.2f}%，等待方向选择。",
]


def generate_summary(data, summary_type="overview"):
    """生成行情总结，纯本地生成，随机话术组合，效果自然。"""
    idx = data["index"]
    sectors = data["sectors"]
    stocks = data["stocks"]

    if not stocks or not sectors:
        return None

    sorted_stocks = sorted(stocks, key=lambda x: x["change"], reverse=True)
    top3_up = sorted_stocks[:3]
    top3_down = sorted_stocks[-3:][::-1]
    sorted_sectors = sorted(sectors, key=lambda x: x["change"], reverse=True)

    up_str = str(idx['up']) + "涨" + str(idx['down']) + "跌"
    trend = "收涨" if idx['change'] >= 0 else "收跌"
    pct = ("+" if idx['change'] >= 0 else "") + f"{idx['change']:.2f}%"

    if idx['change'] >= 1.5: mood = random.choice(["强势", "强劲", " bullish"])
    elif idx['change'] >= 0.5: mood = random.choice(["偏强", "积极", "向好"])
    elif idx['change'] >= -0.5: mood = random.choice(["震荡", "胶着", "盘整"])
    elif idx['change'] >= -1.5: mood = random.choice(["偏弱", "疲软", "承压"])
    else: mood = random.choice(["承压", "低迷", "走弱"])

    lead = sorted_sectors[0]
    lag = sorted_sectors[-1]

    if summary_type == "overview":
        sector_text = lead['name'] + "领涨(" + f"{lead['change']:+.2f}%" + ")"
        if lead['name'] != lag['name']:
            sector_text += "，" + lag['name'] + "领跌(" + f"{lag['change']:+.2f}%" + ")"

        leaders = top3_up[0]['ticker'] + "(" + f"{top3_up[0]['change']:+.2f}%" + ")"
        laggards = top3_down[0]['ticker'] + "(" + f"{top3_down[0]['change']:+.2f}%" + ")"

        lines = [
            random.choice(OVERVIEW_OPENINGS).format(trend=trend, pct=pct, up_str=up_str, mood=mood),
            random.choice(OVERVIEW_SECTORS).format(sector_text=sector_text),
            random.choice(OVERVIEW_STOCKS).format(leaders=leaders, laggards=laggards),
        ]

        if idx['change'] >= 1 and idx['up'] >= 70:
            lines.append("市场情绪积极，短期有望延续强势。")
        elif idx['change'] <= -1 and idx['down'] >= 70:
            lines.append("避险情绪升温，短期或继续震荡整理。")
        else:
            lines.append(random.choice(OVERVIEW_OUTLOOKS))

        summary = "".join(lines)

    elif summary_type == "stocks":
        leaders = top3_up[0]['ticker'] + "(" + f"{top3_up[0]['change']:+.2f}%" + ")"
        if len(top3_up) > 1:
            leaders += "、" + top3_up[1]['ticker'] + "(" + f"{top3_up[1]['change']:+.2f}%" + ")"
        laggards = top3_down[0]['ticker'] + "(" + f"{top3_down[0]['change']:+.2f}%" + ")"
        if len(top3_down) > 1:
            laggards += "、" + top3_down[1]['ticker'] + "(" + f"{top3_down[1]['change']:+.2f}%" + ")"
        trend_text = "受权重股支撑" if idx['change'] >= 0 else "受权重股拖累"
        summary = random.choice(STOCKS_TEMPLATES).format(leaders=leaders, laggards=laggards, trend_text=trend_text)

    elif summary_type == "sectors":
        summary = random.choice(SECTORS_TEMPLATES).format(
            lead=lead['name'] + "(" + f"{lead['change']:+.2f}%" + ")",
            lag=lag['name'] + "(" + f"{lag['change']:+.2f}%" + ")"
        )

    elif summary_type == "distribution":
        bins = data.get("bins", {})
        counts = bins.get("counts", [])
        extreme_up = sum(counts[6:]) if len(counts) > 6 else 0
        extreme_down = sum(counts[:2]) if len(counts) > 2 else 0

        if idx['up'] >= 70:
            summary = DIST_TEMPLATES[0].format(up=idx['up'], down=idx['down'])
        elif idx['down'] >= 70:
            summary = DIST_TEMPLATES[1].format(up=idx['up'], down=idx['down'])
        else:
            summary = random.choice(DIST_TEMPLATES[2:]).format(
                up=idx['up'], down=idx['down'], extreme_up=extreme_up, extreme_down=extreme_down
            )

    elif summary_type == "industry":
        summary = random.choice(INDUSTRY_TEMPLATES).format(
            lead=lead['name'] + "(" + f"{lead['change']:+.2f}%" + ")",
            lag=lag['name'] + "(" + f"{lag['change']:+.2f}%" + ")"
        )

    elif summary_type == "trend":
        hist = data.get("history", [])
        if len(hist) < 5:
            return "历史数据不足，无法分析趋势。"
        c30 = round((hist[-1] - hist[0]) / hist[0] * 100, 2)
        recent5 = round((hist[-1] - hist[-5]) / hist[-5] * 100, 2)

        if c30 >= 5:
            summary = TREND_TEMPLATES[0].format(c30=c30, recent5=recent5)
        elif c30 <= -5:
            summary = TREND_TEMPLATES[1].format(c30=c30, recent5=recent5)
        else:
            if recent5 >= 2:
                summary = TREND_TEMPLATES[2].format(c30=c30, recent5=recent5)
            elif recent5 <= -2:
                summary = TREND_TEMPLATES[3].format(c30=c30, recent5=recent5)
            else:
                summary = TREND_TEMPLATES[4].format(c30=c30, recent5=recent5)

    else:
        return None

    print(f"  [本地 {summary_type}]: {summary[:60]}...")
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

    html = generate_html(data, is_history=False, history_dates=history_dates)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print("  输出: " + OUTPUT_FILE)

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
