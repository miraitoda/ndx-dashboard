#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
手动补录脚本：抓取过去30个自然日的历史数据
============================================
- 自动计算过去30个自然日（含今天）
- 不开盘的日期自动跳过
- 每个成功日期保留30日走势历史
"""

import os
import sys
import json
import math
import time
from datetime import datetime, timedelta
from collections import defaultdict

import yfinance as yf

from ndx_components import STOCKS
from fetch_data import generate_html, generate_summary, ensure_dir

OUTPUT_DIR = "docs"
DAYS_BACK = 30  # 过去30个自然日


def get_target_dates():
    """生成过去30个自然日的日期列表（从今天往前推）。"""
    today = datetime.now().date()
    dates = []
    for i in range(DAYS_BACK):
        d = today - timedelta(days=i)
        dates.append(d.strftime("%Y-%m-%d"))
    return dates


def fetch_history_data(start_date, end_date):
    tickers = [s[0] for s in STOCKS]
    print(f"\n下载 {start_date} ~ {end_date} 的个股数据...")
    all_data = {}
    batch_size = 10
    total_batches = (len(tickers) - 1) // batch_size + 1

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        print(f"  批次 {i // batch_size + 1}/{total_batches}...")
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
    date = datetime.strptime(date_str, "%Y-%m-%d").date()
    if not raw_data:
        return None

    sample_df = None
    for ticker in [s[0] for s in STOCKS]:
        if ticker in raw_data:
            sample_df = raw_data[ticker]
            break
    if sample_df is None or sample_df.empty:
        return None

    all_dates = sorted(set(
        d.tz_localize(None).date() if hasattr(d, 'tz_localize') else d.date()
        for d in sample_df.index
    ))

    if date not in all_dates:
        print(f"  {date_str} 无数据（跳过，可用: {all_dates[0]} ~ {all_dates[-1]}）")
        return None

    idx = all_dates.index(date)
    if idx == 0:
        print(f"  {date_str} 是第一个数据点，无前一日对比，跳过")
        return None

    prev_date = all_dates[idx - 1]
    print(f"  对比: {date_str} vs {prev_date}")

    stocks = []
    for ticker, name, sector, weight in STOCKS:
        if ticker not in raw_data:
            continue
        df = raw_data[ticker]
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
            stocks.append({"ticker": ticker, "name": name, "sector": sector, "weight": weight, "change": change})
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

    # 30日走势历史：从该日期往前推最多30个交易日
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
            print(f"  history: {len(history)} 天")
        except ValueError:
            pass

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

    print("  生成 AI 总结...")
    result["ai_summary"] = generate_summary(result, "overview")
    result["ai_stocks"] = generate_summary(result, "stocks")
    result["ai_sectors"] = generate_summary(result, "sectors")
    result["ai_distribution"] = generate_summary(result, "distribution")
    result["ai_industry"] = generate_summary(result, "industry")
    result["ai_trend"] = generate_summary(result, "trend")

    return result


def save_history(data, all_dates):
    history_dir = os.path.join(OUTPUT_DIR, "history")
    os.makedirs(history_dir, exist_ok=True)
    date_str = data["date"]

    json_file = os.path.join(history_dir, f"{date_str}.json")
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    # 与 fetch_data.py 的 generate_html 签名保持一致
    html = generate_html(data, all_dates, is_history=True)
    html_file = os.path.join(history_dir, f"{date_str}.html")
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  已保存: {html_file}")


def main():
    target_dates = get_target_dates()
    print("=" * 50)
    print(f"手动补录：过去 {DAYS_BACK} 个自然日")
    print(f"目标日期: {target_dates[0]} ~ {target_dates[-1]}")
    print("=" * 50)

    ensure_dir()

    # 计算下载范围：最早日期往前推40天，确保30日历史数据完整
    dates_dt = [datetime.strptime(d, "%Y-%m-%d") for d in target_dates]
    start = (min(dates_dt) - timedelta(days=40)).strftime("%Y-%m-%d")
    end = (max(dates_dt) + timedelta(days=1)).strftime("%Y-%m-%d")

    raw_data = fetch_history_data(start, end)
    if not raw_data:
        print("\n数据下载失败")
        return 1

    ndx_hist = fetch_index_history_range(start, end)

    all_dates = []
    for date_str in target_dates:
        print(f"\n处理 {date_str}...")
        data = build_data_for_date(date_str, raw_data, ndx_hist)
        if data:
            all_dates.append(date_str)
            save_history(data, all_dates)
        else:
            print(f"  → 跳过 {date_str}（不开盘或无数据）")

    if not all_dates:
        print("\n没有成功生成任何快照")
        return 1

    all_dates.sort()
    print(f"\n更新导航: {all_dates}")

    # 重新生成所有历史页面（更新导航链接）
    history_dir = os.path.join(OUTPUT_DIR, "history")
    for date_str in all_dates:
        json_file = os.path.join(history_dir, f"{date_str}.json")
        if not os.path.exists(json_file):
            continue
        with open(json_file, "r", encoding="utf-8") as f:
            old_data = json.load(f)
        html = generate_html(old_data, all_dates, is_history=True)
        with open(os.path.join(history_dir, f"{date_str}.html"), "w", encoding="utf-8") as f:
            f.write(html)

    print(f"\n{'=' * 50}")
    print(f"完成！成功 {len(all_dates)} 天，跳过 {DAYS_BACK - len(all_dates)} 天")
    print(f"位置: {history_dir}")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
