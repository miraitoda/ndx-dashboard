#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
纳指100每日收盘 Dashboard 数据抓取脚本
用法: python fetch_data.py
输出: docs/index.html（自包含单页，可直接部署到 GitHub Pages）
"""

import json
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
    """分批获取多只股票当日数据"""
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
            stocks.append({"ticker": ticker, "name": name, "sector": sector, "weight": weight, "change": change})
        except Exception as e:
            print(f"  处理失败 {ticker}: {e}")

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

    return {
        "index": index_info, "stocks": stocks, "pie_stocks": pie,
        "sectors": sector_list, "bins": {"labels": labels, "counts": counts},
        "history": history, "date": datetime.now().strftime("%Y-%m-%d"),
    }


# HTML 模板 - 用占位符 __DATA_JSON__ 注入数据
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>纳指100 - 每日收盘</title>
<style>
:root{--bg:#fafafa;--card:#fff;--text:#1f1f1f;--text2:#5a5a5a;--text3:#888;--text4:#aaa;--border:#e5e5e5;--rise:#16a34a;--fall:#dc2626}
@media(prefers-color-scheme:dark){:root{--bg:#0f0f0f;--card:#1a1a1a;--text:#e8e8e8;--text2:#a0a0a0;--text3:#777;--text4:#555;--border:#2a2a2a;--rise:#22c55e;--fall:#ef4444}}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--text);padding:16px;line-height:1.5}
.container{max-width:1100px;margin:0 auto}
.header{display:flex;align-items:baseline;gap:12px;margin-bottom:20px;flex-wrap:wrap}
.header h1{font-size:22px;font-weight:600}
.header .date{font-size:13px;color:var(--text3)}
.header .badge{font-size:12px;padding:2px 10px;border-radius:6px;background:rgba(22,163,74,.12);color:var(--rise)}
.kpi-row{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}
.kpi{background:var(--card);padding:16px;border:1px solid var(--border);border-radius:12px}
.kpi-label{font-size:12px;color:var(--text3);margin-bottom:4px}
.kpi-value{font-size:30px;font-weight:600;font-variant-numeric:tabular-nums}
.kpi-sub{font-size:13px;margin-top:4px;font-variant-numeric:tabular-nums}
.kpi-sub.up{color:var(--rise)}.kpi-sub.down{color:var(--rise)}.kpi-sub.down{color:var(--fall)}
.charts-row{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}
.chart-box{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px}
.chart-title{font-size:14px;font-weight:500;margin-bottom:6px;color:var(--text2)}
.chart-sub{font-size:11px;color:var(--text4);margin-bottom:10px}
.full-row{margin-bottom:20px}
.tooltip{position:absolute;background:var(--card);border:1px solid var(--border);border-radius:8px;padding:8px 12px;font-size:12px;pointer-events:none;opacity:0;transition:opacity .15s;z-index:10;box-shadow:0 4px 12px rgba(0,0,0,.15);white-space:nowrap}
.legend{display:flex;flex-wrap:wrap;gap:8px 14px;margin-top:10px;font-size:11px}
.legend-item{display:flex;align-items:center;gap:4px}
.legend-dot{width:8px;height:8px;border-radius:2px}
.stock-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(85px,1fr));gap:4px;margin-top:10px}
.stock-cell{padding:5px 6px;border-radius:6px;font-size:11px;text-align:center;cursor:pointer;transition:transform .1s,box-shadow .1s;background:var(--card)}
.stock-cell:hover{transform:scale(1.06);box-shadow:0 2px 8px rgba(0,0,0,.08)}
.footer{text-align:center;font-size:11px;color:var(--text4);margin-top:24px;padding-bottom:20px}
@media(max-width:720px){.charts-row{grid-template-columns:1fr}.kpi-row{grid-template-columns:repeat(2,1fr)}.kpi-value{font-size:24px}}
</style>
</head>
<body>
<div class="container">
<div class="header"><h1>纳斯达克100 - 收盘概览</h1><span class="date" id="dateStr"></span><span class="badge">已收盘</span></div>
<div class="kpi-row">
<div class="kpi"><div class="kpi-label">指数点位</div><div class="kpi-value" id="idxPrice">--</div><div class="kpi-sub" id="idxChange">--</div></div>
<div class="kpi"><div class="kpi-label">涨跌家数</div><div class="kpi-value" style="font-size:22px" id="upDown">--</div><div class="kpi-sub" style="color:var(--text3)">涨 / 跌</div></div>
<div class="kpi"><div class="kpi-label">30日走势</div><div class="kpi-value" id="trend30d">--</div><div class="kpi-sub" style="color:var(--text3)" id="trendRange">--</div></div>
<div class="kpi"><div class="kpi-label">数据状态</div><div class="kpi-value" style="font-size:22px" id="dataStatus">正常</div><div class="kpi-sub" style="color:var(--text3)">成分股 <span id="stockCount">--</span> 只</div></div>
</div>
<div class="charts-row">
<div class="chart-box"><div class="chart-title">个股权重饼图（Top 15 + 其他）</div><div class="chart-sub">绿色=上涨，红色=下跌，面积=权重</div><svg id="stockPie" viewBox="0 0 320 280" style="width:100%;height:auto"></svg><div class="legend" id="stockLegend"></div></div>
<div class="chart-box"><div class="chart-title">行业权重饼图</div><div class="chart-sub">绿色=上涨，红色=下跌，面积=权重</div><svg id="sectorPie" viewBox="0 0 320 280" style="width:100%;height:auto"></svg><div class="legend" id="sectorLegend"></div></div>
</div>
<div class="charts-row">
<div class="chart-box"><div class="chart-title">涨跌分布柱图</div><div class="chart-sub">100支成分股按涨跌幅区间分布</div><svg id="distChart" viewBox="0 0 400 220" style="width:100%;height:auto"></svg></div>
<div class="chart-box"><div class="chart-title">行业表现柱图</div><div class="chart-sub">各行业按权重加权平均涨跌幅</div><svg id="sectorBar" viewBox="0 0 400 220" style="width:100%;height:auto"></svg></div>
</div>
<div class="full-row chart-box"><div class="chart-title">纳指100 - 近30日走势线图</div><div class="chart-sub">每日收盘价连线</div><svg id="trendLine" viewBox="0 0 800 240" style="width:100%;height:auto"></svg></div>
<div class="chart-box" style="margin-top:16px"><div class="chart-title">100支成分股涨跌一览</div><div class="chart-sub">鼠标悬停查看详情</div><div class="stock-grid" id="stockGrid"></div></div>
<div class="footer">数据来自 Yahoo Finance - 每日自动更新 - 仅供参考不构成投资建议</div>
<div class="tooltip" id="tooltip"></div>
</div>
<script>
const DATA = __DATA_JSON__;
const RISE=getComputedStyle(document.documentElement).getPropertyValue("--rise").trim()||"#16a34a";
const FALL=getComputedStyle(document.documentElement).getPropertyValue("--fall").trim()||"#dc2626";
const TEXT=getComputedStyle(document.documentElement).getPropertyValue("--text").trim()||"#1f1f1f";
const TEXT2=getComputedStyle(document.documentElement).getPropertyValue("--text2").trim()||"#5a5a5a";
const TEXT4=getComputedStyle(document.documentElement).getPropertyValue("--text4").trim()||"#aaaaaa";
const BORDER=getComputedStyle(document.documentElement).getPropertyValue("--border").trim()||"#e5e5e5";
function colorForChange(c){return c>=0?RISE:FALL}
function fmtPct(c){return(c>=0?"+":"")+c.toFixed(2)+"%"}
function svgEl(tag,attrs){const el=document.createElementNS("http://www.w3.org/2000/svg",tag);for(let k in attrs)el.setAttribute(k,attrs[k]);return el}
(function(){const idx=DATA.index;document.getElementById("dateStr").textContent=DATA.date;document.getElementById("idxPrice").textContent=idx.price?idx.price.toLocaleString():"估算中";const chgEl=document.getElementById("idxChange");chgEl.textContent=fmtPct(idx.change)+(idx.price?" ("+(idx.price-idx.prev_close).toFixed(2)+")":"");chgEl.className="kpi-sub "+(idx.change>=0?"up":"down");document.getElementById("upDown").innerHTML=idx.up+' <span style="color:var(--text4)">/</span> '+idx.down;document.getElementById("stockCount").textContent=idx.total;const hist=DATA.history;if(hist.length>=2){const c30=((hist[hist.length-1]-hist[0])/hist[0]*100).toFixed(2);const t30=document.getElementById("trend30d");t30.textContent=(c30>=0?"+":"")+c30+"%";t30.style.color=c30>=0?RISE:FALL;document.getElementById("trendRange").textContent=Math.round(hist[0]).toLocaleString()+" -> "+Math.round(hist[hist.length-1]).toLocaleString()}else{document.getElementById("trend30d").textContent="--";document.getElementById("trendRange").textContent="数据暂缺"}if(idx.total<80){document.getElementById("dataStatus").textContent="部分缺失";document.getElementById("dataStatus").style.color=FALL}})();
(function(){const svg=document.getElementById("stockPie");const data=DATA.pie_stocks;const total=data.reduce((a,b)=>a+b.weight,0);const cx=140,cy=130,r=90,ir=45;let ang=-Math.PI/2;data.forEach(d=>{const a=(d.weight/total)*Math.PI*2;const x1=cx+r*Math.cos(ang),y1=cy+r*Math.sin(ang);const x2=cx+r*Math.cos(ang+a),y2=cy+r*Math.sin(ang+a);const ix1=cx+ir*Math.cos(ang),iy1=cy+ir*Math.sin(ang);const ix2=cx+ir*Math.cos(ang+a),iy2=cy+ir*Math.sin(ang+a);const large=a>Math.PI?1:0;const path="M "+ix1+" "+iy1+" L "+x1+" "+y1+" A "+r+" "+r+" 0 "+large+" 1 "+x2+" "+y2+" L "+ix2+" "+iy2+" A "+ir+" "+ir+" 0 "+large+" 0 "+ix1+" "+iy1;const fill=colorForChange(d.change);const slice=svgEl("path",{d:path,fill:fill,opacity:.85,stroke:"var(--bg)","stroke-width":1.5});slice.style.cursor="pointer";slice.addEventListener("mouseenter",e=>showTip(e,d.ticker+" "+d.name+"<br>权重 "+d.weight+"% - "+fmtPct(d.change)));slice.addEventListener("mouseleave",hideTip);svg.appendChild(slice);ang+=a});svg.appendChild(svgEl("text",{x:cx,y:cy-6,"text-anchor":"middle",fill:TEXT,"font-size":14,"font-weight":600})).textContent="NDX";svg.appendChild(svgEl("text",{x:cx,y:cy+14,"text-anchor":"middle",fill:colorForChange(DATA.index.change),"font-size":13,"font-weight":600})).textContent=fmtPct(DATA.index.change);const leg=document.getElementById("stockLegend");data.slice(0,8).forEach(d=>{const item=document.createElement("div");item.className="legend-item";item.innerHTML='<span class="legend-dot" style="background:'+colorForChange(d.change)+'"></span><span>'+d.ticker+" "+fmtPct(d.change)+"</span>";leg.appendChild(item)})})();
(function(){const svg=document.getElementById("sectorPie");const data=DATA.sectors;const total=data.reduce((a,b)=>a+b.weight,0);const cx=140,cy=130,r=90,ir=45;let ang=-Math.PI/2;data.forEach(d=>{const a=(d.weight/total)*Math.PI*2;const x1=cx+r*Math.cos(ang),y1=cy+r*Math.sin(ang);const x2=cx+r*Math.cos(ang+a),y2=cy+r*Math.sin(ang+a);const ix1=cx+ir*Math.cos(ang),iy1=cy+ir*Math.sin(ang);const ix2=cx+ir*Math.cos(ang+a),iy2=cy+ir*Math.sin(ang+a);const large=a>Math.PI?1:0;const path="M "+ix1+" "+iy1+" L "+x1+" "+y1+" A "+r+" "+r+" 0 "+large+" 1 "+x2+" "+y2+" L "+ix2+" "+iy2+" A "+ir+" "+ir+" 0 "+large+" 0 "+ix1+" "+iy1;const fill=colorForChange(d.change);const slice=svgEl("path",{d:path,fill:fill,opacity:.8,stroke:"var(--bg)","stroke-width":1.5});slice.style.cursor="pointer";slice.addEventListener("mouseenter",e=>showTip(e,d.name+"<br>权重 "+d.weight+"% - "+d.count+"只 - 平均 "+fmtPct(d.change)));slice.addEventListener("mouseleave",hideTip);svg.appendChild(slice);ang+=a});svg.appendChild(svgEl("text",{x:cx,y:cy-6,"text-anchor":"middle",fill:TEXT,"font-size":14,"font-weight":600})).textContent="行业";svg.appendChild(svgEl("text",{x:cx,y:cy+14,"text-anchor":"middle",fill:TEXT2,"font-size":11})).textContent=data.length+"个板块";const leg=document.getElementById("sectorLegend");data.forEach(d=>{const item=document.createElement("div");item.className="legend-item";item.innerHTML='<span class="legend-dot" style="background:'+colorForChange(d.change)+'"></span><span>'+d.name+" "+d.weight+"%</span>";leg.appendChild(item)})})();
(function(){const svg=document.getElementById("distChart");const labels=DATA.bins.labels;const counts=DATA.bins.counts;const max=Math.max(...counts);const W=400,H=220,padL=40,padB=30,padT=20,padR=20;const bw=(W-padL-padR)/labels.length-4;for(let i=0;i<=4;i++){const y=padT+(H-padT-padB)*(1-i/4);svg.appendChild(svgEl("line",{x1:padL,y1:y,x2:W-padR,y2:y,stroke:BORDER,"stroke-width":.5}));svg.appendChild(svgEl("text",{x:padL-6,y:y+4,"text-anchor":"end",fill:TEXT4,"font-size":10})).textContent=Math.round(max*i/4)}labels.forEach((lbl,i)=>{const h=(counts[i]/max)*(H-padT-padB);const x=padL+i*(W-padL-padR)/labels.length+2;const y=H-padB-h;const isUp=i>=4;const bar=svgEl("rect",{x:x,y:y,width:bw,height:h||1,rx:3,fill:isUp?RISE:FALL,opacity:.85});bar.style.cursor="pointer";bar.addEventListener("mouseenter",e=>showTip(e,lbl+": "+counts[i]+"只"));bar.addEventListener("mouseleave",hideTip);svg.appendChild(bar);svg.appendChild(svgEl("text",{x:x+bw/2,y:H-padB+14,"text-anchor":"middle",fill:TEXT2,"font-size":10})).textContent=lbl;if(counts[i]>0){svg.appendChild(svgEl("text",{x:x+bw/2,y:y-6,"text-anchor":"middle",fill:isUp?RISE:FALL,"font-size":10,"font-weight":500})).textContent=counts[i]}});const zeroX=padL+4*(W-padL-padR)/labels.length;svg.appendChild(svgEl("line",{x1:zeroX,y1:padT,x2:zeroX,y2:H-padB,stroke:TEXT,"stroke-width":1,"stroke-dasharray":"3,3",opacity:.3}))})();
(function(){const svg=document.getElementById("sectorBar");const data=DATA.sectors;const W=400,H=220,padL=60,padB=30,padT=20,padR=20;const maxC=Math.max(...data.map(d=>Math.abs(d.change)),.01);const scale=(H-padT-padB)/2/maxC;const zeroY=padT+(H-padT-padB)/2;svg.appendChild(svgEl("line",{x1:padL,y1:zeroY,x2:W-padR,y2:zeroY,stroke:BORDER,"stroke-width":1}));data.forEach((d,i)=>{const h=Math.max(Math.abs(d.change)*scale,2);const y=d.change>=0?zeroY-h:zeroY;const x=padL+8;const bw=W-padL-padR-16;const bar=svgEl("rect",{x:x,y:y,width:bw,height:h,rx:3,fill:colorForChange(d.change),opacity:.8});bar.style.cursor="pointer";bar.addEventListener("mouseenter",e=>showTip(e,d.name+"<br>平均 "+fmtPct(d.change)));bar.addEventListener("mouseleave",hideTip);svg.appendChild(bar);svg.appendChild(svgEl("text",{x:padL-6,y:y+h/2+4,"text-anchor":"end",fill:TEXT2,"font-size":10})).textContent=d.name;svg.appendChild(svgEl("text",{x:x+bw+4,y:y+h/2+4,fill:colorForChange(d.change),"font-size":10,"font-weight":500})).textContent=fmtPct(d.change)})})();
(function(){const svg=document.getElementById("trendLine");const data=DATA.history;if(data.length<2){svg.appendChild(svgEl("text",{x:400,y:120,"text-anchor":"middle",fill:TEXT4,"font-size":14})).textContent="历史数据暂缺";return}const W=800,H=240,padL=50,padB=30,padT=30,padR=30;const min=Math.min(...data),max=Math.max(...data);const range=max-min||1;const x=i=>padL+i*(W-padL-padR)/(data.length-1);const y=v=>padT+(max-v)/range*(H-padT-padB);let areaD="M "+x(0)+" "+y(data[0]);data.forEach((v,i)=>areaD+=" L "+x(i)+" "+y(v));areaD+=" L "+x(data.length-1)+" "+(H-padB)+" L "+x(0)+" "+(H-padB)+" Z";svg.appendChild(svgEl("path",{d:areaD,fill:colorForChange(DATA.index.change),opacity:.06}));let lineD="M "+x(0)+" "+y(data[0]);data.forEach((v,i)=>lineD+=" L "+x(i)+" "+y(v));svg.appendChild(svgEl("path",{d:lineD,fill:"none",stroke:colorForChange(DATA.index.change),"stroke-width":2,"stroke-linecap":"round","stroke-linejoin":"round"}));data.forEach((v,i)=>{const c=svgEl("circle",{cx:x(i),cy:y(v),r:3,fill:"var(--bg)",stroke:colorForChange(DATA.index.change),"stroke-width":1.5});c.style.cursor="pointer";c.addEventListener("mouseenter",e=>showTip(e,(i+1)+"天前<br>收盘 "+Math.round(v).toLocaleString()));c.addEventListener("mouseleave",hideTip);svg.appendChild(c)});svg.appendChild(svgEl("text",{x:padL,y:H-8,fill:TEXT4,"font-size":10})).textContent="30日前";svg.appendChild(svgEl("text",{x:W-padR,y:H-8,"text-anchor":"end",fill:TEXT4,"font-size":10})).textContent="今日";svg.appendChild(svgEl("text",{x:padL-10,y:padT+4,"text-anchor":"end",fill:TEXT4,"font-size":10})).textContent=Math.round(max).toLocaleString();svg.appendChild(svgEl("text",{x:padL-10,y:H-padB,"text-anchor":"end",fill:TEXT4,"font-size":10})).textContent=Math.round(min).toLocaleString()})();
(function(){const grid=document.getElementById("stockGrid");DATA.stocks.forEach(s=>{const cell=document.createElement("div");cell.className="stock-cell";const c=colorForChange(s.change);cell.style.border="1px solid "+c+"40";cell.style.color=c;cell.innerHTML='<div style="font-weight:600;font-size:12px">'+s.ticker+'</div><div style="font-size:10px;opacity:.85">'+fmtPct(s.change)+"</div>";cell.addEventListener("mouseenter",e=>showTip(e,s.ticker+" "+s.name+"<br>权重 "+s.weight+"% - "+fmtPct(s.change)+" - "+s.sector));cell.addEventListener("mouseleave",hideTip);grid.appendChild(cell)})})();
const tip=document.getElementById("tooltip");
function showTip(e,html){tip.innerHTML=html;tip.style.opacity="1";const rect=e.target.getBoundingClientRect();const host=document.querySelector(".container").getBoundingClientRect();let left=rect.left-host.left+rect.width/2-tip.offsetWidth/2;let top=rect.top-host.top-tip.offsetHeight-8;if(left<0)left=0;if(top<0)top=rect.bottom-host.top+8;tip.style.left=left+"px";tip.style.top=top+"px"}
function hideTip(){tip.style.opacity="0"}
</script>
</body>
</html>"""


def generate_html(data):
    jd = json.dumps(data, ensure_ascii=False)
    return HTML_TEMPLATE.replace("__DATA_JSON__", jd)


def main():
    print("=" * 50)
    print("纳指100 Dashboard 数据更新")
    print("=" * 50)
    ensure_dir()
    print("\n[1/3] 抓取数据...")
    data = build_data()
    print("\n[2/3] 生成 HTML...")
    html = generate_html(data)
    print("\n[3/3] 写入文件...")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n完成！输出: {OUTPUT_FILE}")
    print(f"日期: {data['date']}")
    print(f"成分股: {data['index']['total']} 只")
    print(f"指数涨跌: {data['index']['change']}%")
    print(f"上涨/下跌: {data['index']['up']} / {data['index']['down']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
