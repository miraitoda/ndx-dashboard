#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
临时脚本：补录前4个交易日历史数据（GitHub Actions 专用版）
============================================================
用法：
  1. 把本文件放到项目根目录（和 fetch_data.py 同级）
  2. 提交到 main 分支
  3. 在 GitHub Actions 里运行（或本地运行）
  4. 跑完后删除本文件

说明：
- 一次性下载 10 天的数据（覆盖 4 个目标日期及其前一日）
- 每批 10 只股票，批次间 sleep 2 秒，降低触发 Yahoo Finance 限流风险
- 如果抓取失败，脚本会提示错误，可稍后重试
"""

import os
import sys
import json
import math
import time
from datetime import datetime, timedelta
from collections import defaultdict

import yfinance as yf

# 从项目导入（确保在同一目录）
from ndx_components import STOCKS
from fetch_data import generate_html, generate_summary, ensure_dir

# 前4个交易日（2026-08-12 往前推，跳过周末）
TARGET_DATES = ['2026-08-11', '2026-08-10', '2026-08-07', '2026-08-06']
OUTPUT_DIR = "docs"


def fetch_history_data(start_date, end_date):
    """抓取一段历史数据，返回 {ticker: DataFrame}"""
    tickers = [s[0] for s in STOCKS]
    print(f"\n下载 {start_date} ~ {end_date} 的个股数据...")

    all_data = {}
    batch_size = 10
    total_batches = (len(tickers) - 1) // batch_size + 1

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        print(f"  批次 {i // batch_size + 1}/{total_batches}: {', '.join(batch[:3])}...")
        try:
            data = yf.download(
                " ".join(batch),
                start=start_date,
                end=end_date,
                interval="1d",
                progress=False,
                threads=True,
                group_by="ticker"
            )
            if data.empty:
                print(f"    返回空数据")
                continue
            if len(batch) == 1:
                all_data[batch[0]] = data
            else:
                for ticker in batch:
                    if ticker in data.columns.get_level_values(0):
                        all_data[ticker] = data[ticker]
        except Exception as e:
            print(f"    失败: {e}")
        time.sleep(2)

    print(f"  成功下载 {len(all_data)}/{len(tickers)} 只股票")
    return all_data


def fetch_index_history_range(start_date, end_date):
    """抓取指数历史数据"""
    print(f"\n下载 {start_date} ~ {end_date} 的 ^NDX 数据...")
    try:
        t = yf.Ticker("^NDX")
        hist = t.history(start=start_date, end=end_date)
        print(f"  成功: {len(hist)} 条记录")
        return hist
    except Exception as e:
        print(f"  指数历史失败: {e}")
        return None


def build_data_for_date(date_str, raw_data, ndx_hist):
    """从已下载的数据中提取特定日期的数据"""
    date = datetime.strptime(date_str, "%Y-%m-%d").date()

    if not raw_data:
        print(f"  无原始数据")
        return None

    # 获取所有日期（取第一只有效股票）
    sample_df = None
    for ticker in [s[0] for s in STOCKS]:
        if ticker in raw_data:
            sample_df = raw_data[ticker]
            break

    if sample_df is None or sample_df.empty:
        print(f"  样本数据为空")
        return None

    # 处理时区：yfinance 返回的索引可能是 tz-aware
    all_dates = sorted(set(
        d.tz_localize(None).date() if hasattr(d, 'tz_localize') else d.date()
        for d in sample_df.index
    ))

    if date not in all_dates:
        print(f"  {date_str} 不在下载的数据中（可用日期: {all_dates[0]} ~ {all_dates[-1]}）")
        return None

    idx = all_dates.index(date)
    if idx == 0:
        print(f"  {date_str} 是第一个数据点，无前一日对比")
        return None

    prev_date = all_dates[idx - 1]
    print(f"  对比: {date_str} vs {prev_date}")

    stocks = []
    for ticker, name, sector, weight in STOCKS:
        if ticker not in raw_data:
            continue
        df = raw_data[ticker]

        # 处理时区
        df_dates = [d.tz_localize(None).date() if hasattr(d, 'tz_localize') else d.date() for d in df.index]
        df_indexed = df.copy()
        df_indexed['__date__'] = df_dates

        target_rows = df_indexed[df_indexed['__date__'] == date]
        prev_rows = df_indexed[df_indexed['__date__'] == prev_date]

        if target_rows.empty or prev_rows.empty:
            continue

        try:
            close = float(target_rows["Close"].iloc[-1])
            prev_close = float(prev_rows["Close"].iloc[-1])
            change = round((close - prev_close) / prev_close * 100, 2)
            if math.isnan(change):
                continue
            stocks.append({
                "ticker": ticker, "name": name, "sector": sector,
                "weight": weight, "change": change
            })
        except Exception as e:
            print(f"    处理失败 {ticker}: {e}")

    if len(stocks) < 50:
        print(f"  警告: 仅 {len(stocks)} 只有效数据，跳过")
        return None

    # 指数数据
    if ndx_hist is not None and not ndx_hist.empty:
        ndx_dates = [
            d.tz_localize(None).date() if hasattr(d, 'tz_localize') else d.date()
            for d in ndx_hist.index
        ]
        ndx_hist_copy = ndx_hist.copy()
        ndx_hist_copy['__date__'] = ndx_dates

        target_ndx = ndx_hist_copy[ndx_hist_copy['__date__'] == date]
        prev_ndx = ndx_hist_copy[ndx_hist_copy['__date__'] == prev_date]

        if not target_ndx.empty and not prev_ndx.empty:
            price = float(target_ndx["Close"].iloc[-1])
            prev_close = float(prev_ndx["Close"].iloc[-1])
            change = round((price - prev_close) / prev_close * 100, 2)
            index_info = {"price": round(price, 2), "prev_close": round(prev_close, 2), "change": change}
        else:
            total_weight = sum(s["weight"] for s in stocks)
            weighted_change = sum(s["weight"] * s["change"] for s in stocks) / total_weight
            index_info = {"price": 0, "prev_close": 0, "change": round(weighted_change, 2)}
    else:
        total_weight = sum(s["weight"] for s in stocks)
        weighted_change = sum(s["weight"] * s["change"] for s in stocks) / total_weight
        index_info = {"price": 0, "prev_close": 0, "change": round(weighted_change, 2)}

    up = sum(1 for s in stocks if s["change"] > 0)
    down = sum(1 for s in stocks if s["change"] < 0)
    flat = sum(1 for s in stocks if s["change"] == 0)
    index_info.update({"up": up, "down": down, "flat": flat, "total": len(stocks)})

    # 行业统计
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

    # 分布
    bins = [(-999, -3), (-3, -2), (-2, -1), (-1, 0), (0, 1), (1, 2), (2, 3), (3, 999)]
    labels = ["<-3%", "-3~-2%", "-2~-1%", "-1~0%", "0~1%", "1~2%", "2~3%", ">3%"]
    counts = [0] * len(bins)
    for s in stocks:
        c = s["change"]
        for i, (lo, hi) in enumerate(bins):
            if (lo <= c < hi) or (hi == 999 and c >= lo) or (lo == -999 and c < hi):
                counts[i] += 1
                break

    # 30日历史（从已下载的指数数据中提取）
    history = []
    if ndx_hist is not None and not ndx_hist.empty:
        ndx_dates = [
            d.tz_localize(None).date() if hasattr(d, 'tz_localize') else d.date()
            for d in ndx_hist.index
        ]
        try:
            date_idx = ndx_dates.index(date)
            start_idx = max(0, date_idx - 29)
            hist_slice = ndx_hist.iloc[start_idx:date_idx + 1]
            history = [round(float(c), 2) for c in hist_slice["Close"].tolist()]
        except ValueError:
            pass

    # pie
    sorted_w = sorted(stocks, key=lambda x: -x["weight"])
    top15 = sorted_w[:15]
    others = sorted_w[15:]
    ow = sum(s["weight"] for s in others)
    oc = sum(s["weight"] * s["change"] for s in others) / ow if ow > 0 else 0
    pie = top15 + [{"ticker": "其他", "name": f"其他{len(others)}只", "sector": "", "weight": round(ow, 2), "change": round(oc, 2)}]

    result = {
        "index": index_info, "stocks": stocks, "pie_stocks": pie,
        "sectors": sector_list, "bins": {"labels": labels, "counts": counts},
        "history": history, "date": date_str,
    }

    # AI 总结
    print("  生成 AI 总结...")
    result["ai_summary"] = generate_summary(result, "overview")
    result["ai_stocks"] = generate_summary(result, "stocks")
    result["ai_sectors"] = generate_summary(result, "sectors")
    result["ai_distribution"] = generate_summary(result, "distribution")
    result["ai_industry"] = generate_summary(result, "industry")
    result["ai_trend"] = generate_summary(result, "trend")

    return result


def save_history(data, all_dates):
    """保存历史快照"""
    history_dir = os.path.join(OUTPUT_DIR, "history")
    os.makedirs(history_dir, exist_ok=True)
    date_str = data["date"]

    json_file = os.path.join(history_dir, f"{date_str}.json")
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    html = generate_html(data, is_history=True, history_dates=all_dates)
    html_file = os.path.join(history_dir, f"{date_str}.html")
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  已保存: {html_file}")


def main():
    print("=" * 50)
    print("补录历史数据（前4个交易日）")
    print("=" * 50)

    ensure_dir()

    # 计算下载范围：从最早日期的前7天到最晚日期的后1天
    dates = [datetime.strptime(d, "%Y-%m-%d") for d in TARGET_DATES]
    start = (min(dates) - timedelta(days=7)).strftime("%Y-%m-%d")
    end = (max(dates) + timedelta(days=1)).strftime("%Y-%m-%d")

    # 下载数据
    raw_data = fetch_history_data(start, end)
    if not raw_data:
        print("\n数据下载失败，请检查网络或稍后重试")
        print("提示：如果频繁触发限流，可增大批次间隔时间（修改 time.sleep(2) 为更大值）")
        return 1

    ndx_hist = fetch_index_history_range(start, end)

    # 为每个目标日期生成快照
    all_dates = []
    for date_str in TARGET_DATES:
        print(f"\n处理 {date_str}...")
        data = build_data_for_date(date_str, raw_data, ndx_hist)
        if data:
            all_dates.append(date_str)

    if not all_dates:
        print("\n没有成功生成任何快照")
        return 1

    all_dates.sort()
    print(f"\n更新导航链接: {all_dates}")

    # 重新生成所有历史页面（更新导航）
    history_dir = os.path.join(OUTPUT_DIR, "history")
    for date_str in all_dates:
        json_file = os.path.join(history_dir, f"{date_str}.json")
        if not os.path.exists(json_file):
            continue
        with open(json_file, "r", encoding="utf-8") as f:
            old_data = json.load(f)
        html = generate_html(old_data, is_history=True, history_dates=all_dates)
        with open(os.path.join(history_dir, f"{date_str}.html"), "w", encoding="utf-8") as f:
            f.write(html)

    print(f"\n{'=' * 50}")
    print(f"完成！共生成 {len(all_dates)} 个历史快照")
    print(f"位置: {history_dir}")
    print("跑完后可删除本文件 fetch_past_dates.py")
    print('=' * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
