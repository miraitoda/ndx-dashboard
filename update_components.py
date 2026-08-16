#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Nasdaq-100 Auto Updater
=======================

Data sources:
- Nasdaq API: current Nasdaq-100 constituents (ticker + name)
- Slickcharts: QQQ weights via HTML scraping
- Built-in fallback: cached weights + sector mapping (last resort)

Features:
- Auto-add/remove constituents
- Auto-backup
- Data validation
- Full logging
- Works on GitHub Actions (no Tiingo/Yahoo 403 issues)
"""

import os
import re
import json
import shutil
import logging
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup


# ============================================================
# Configuration
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

OUTPUT_FILE = BASE_DIR / "ndx_components.py"
BACKUP_DIR = BASE_DIR / "backup_ndx"
LOG_FILE = BASE_DIR / "update_ndx.log"

NASDAQ_URL = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"
SLICKCHARTS_URL = "https://www.slickcharts.com/nasdaq100"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/151.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/",
}


# ============================================================
# Built-in fallback data (2026-08-16 snapshot)
# Used when Slickcharts scraping fails
# ============================================================

FALLBACK_WEIGHTS = {
    "NVDA": 12.96, "AAPL": 10.61, "MSFT": 8.74, "AMZN": 6.73,
    "GOOGL": 5.18, "GOOG": 4.84, "AVGO": 4.44, "SPCX": 4.39,
    "META": 3.57, "TSLA": 3.21, "MU": 2.61, "WMT": 2.18,
    "AMD": 2.00, "ASML": 1.68, "INTC": 1.23, "CSCO": 1.05,
    "COST": 1.01, "PLTR": 0.99, "LRCX": 0.99, "AMAT": 0.96,
    "NFLX": 0.77, "PANW": 0.74, "ARM": 0.71, "KLAC": 0.63,
    "TXN": 0.61, "SNDK": 0.57, "AMGN": 0.53, "LIN": 0.53,
    "CRWD": 0.53, "STX": 0.52, "MRVL": 0.47, "SHOP": 0.47,
    "TMUS": 0.47, "PEP": 0.46, "ADI": 0.45, "WDC": 0.42,
    "QCOM": 0.41, "GILD": 0.41, "BKNG": 0.38, "ISRG": 0.33,
    "VRTX": 0.30, "SBUX": 0.29, "PDD": 0.29, "FTNT": 0.28,
    "ABNB": 0.26, "ADP": 0.26, "APP": 0.25, "ADBE": 0.25,
    "CEG": 0.24, "INTU": 0.22, "DASH": 0.22, "MELI": 0.22,
    "MAR": 0.22, "CSX": 0.22, "CMCSA": 0.22, "DDOG": 0.22,
    "MNST": 0.22, "CDNS": 0.21, "REGN": 0.20, "LITE": 0.20,
    "MDLZ": 0.19, "SNPS": 0.19, "CTAS": 0.19, "ROST": 0.19,
    "NBIS": 0.18, "HON": 0.18, "ORLY": 0.18, "WBD": 0.17,
    "MPWR": 0.16, "PCAR": 0.16, "AEP": 0.16, "TER": 0.16,
    "BKR": 0.15, "NXPI": 0.14, "FAST": 0.14, "CRWV": 0.14,
    "FANG": 0.13, "ALAB": 0.13, "ADSK": 0.13, "PYPL": 0.13,
    "HONA": 0.13, "RKLB": 0.12, "AXON": 0.12, "XEL": 0.12,
    "WDAY": 0.12, "CCEP": 0.11, "EXC": 0.11, "FER": 0.11,
    "TTWO": 0.11, "TRI": 0.11, "ODFL": 0.10, "IDXX": 0.10,
    "PAYX": 0.10, "MCHP": 0.10, "KDP": 0.10, "ROP": 0.09,
    "MSTR": 0.09, "DXCM": 0.08, "GEHC": 0.08, "ALNY": 0.07,
    "KHC": 0.07, "CPRT": 0.07,
}

SECTOR_MAP = {
    "NVDA": "Technology", "AAPL": "Technology", "MSFT": "Technology",
    "AVGO": "Technology", "MU": "Technology", "AMD": "Technology",
    "ASML": "Technology", "INTC": "Technology", "CSCO": "Technology",
    "AMAT": "Technology", "LRCX": "Technology", "ARM": "Technology",
    "KLAC": "Technology", "TXN": "Technology", "SNDK": "Technology",
    "MRVL": "Technology", "ADI": "Technology", "WDC": "Technology",
    "QCOM": "Technology", "FTNT": "Technology", "APP": "Technology",
    "ADBE": "Technology", "CDNS": "Technology", "SNPS": "Technology",
    "MPWR": "Technology", "TER": "Technology", "NXPI": "Technology",
    "MCHP": "Technology", "ALAB": "Technology", "ADSK": "Technology",
    "PYPL": "Technology", "WDAY": "Technology", "DDOG": "Technology",
    "LITE": "Technology", "NBIS": "Communication Services",
    "CRWV": "Technology", "PLTR": "Technology", "PANW": "Technology",
    "CRWD": "Technology", "INTU": "Technology", "MSTR": "Technology",
    "GOOGL": "Communication Services", "GOOG": "Communication Services",
    "META": "Communication Services", "NFLX": "Communication Services",
    "CMCSA": "Communication Services", "TTWO": "Communication Services",
    "TRI": "Communication Services", "WBD": "Communication Services",
    "TMUS": "Communication Services",
    "AMZN": "Consumer Discretionary", "TSLA": "Consumer Discretionary",
    "WMT": "Consumer Discretionary", "COST": "Consumer Discretionary",
    "SBUX": "Consumer Discretionary", "PDD": "Consumer Discretionary",
    "ABNB": "Consumer Discretionary", "DASH": "Consumer Discretionary",
    "MELI": "Consumer Discretionary", "MAR": "Consumer Discretionary",
    "ROST": "Consumer Discretionary", "BKNG": "Consumer Discretionary",
    "ORLY": "Consumer Discretionary", "SPCX": "Industrials",
    "SHOP": "Consumer Discretionary",
    "PEP": "Consumer Staples", "MNST": "Consumer Staples",
    "MDLZ": "Consumer Staples", "KDP": "Consumer Staples",
    "CCEP": "Consumer Staples", "KHC": "Consumer Staples",
    "AMGN": "Health Care", "GILD": "Health Care", "ISRG": "Health Care",
    "VRTX": "Health Care", "REGN": "Health Care", "IDXX": "Health Care",
    "DXCM": "Health Care", "GEHC": "Health Care", "ALNY": "Health Care",
    "LIN": "Industrials", "STX": "Industrials", "ADP": "Industrials",
    "CSX": "Industrials", "CTAS": "Industrials", "ODFL": "Industrials",
    "PCAR": "Industrials", "FAST": "Industrials", "HON": "Industrials",
    "HONA": "Industrials", "BKR": "Industrials", "FER": "Industrials",
    "RKLB": "Industrials", "AXON": "Industrials", "ROP": "Industrials",
    "CPRT": "Industrials", "PAYX": "Industrials",
    "CEG": "Utilities", "AEP": "Utilities", "XEL": "Utilities",
    "EXC": "Utilities", "FANG": "Energy",
}


# ============================================================
# Logging
# ============================================================

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    encoding="utf-8",
)

console = logging.StreamHandler()
console.setLevel(logging.INFO)
console.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
logging.getLogger().addHandler(console)

session = requests.Session()
session.headers.update(HEADERS)


# ============================================================
# Utils
# ============================================================

def clean_ticker(ticker):
    if not ticker:
        return None
    ticker = str(ticker).strip().upper().replace(".", "-")
    if not re.match(r"^[A-Z0-9\-]+$", ticker):
        return None
    return ticker


def clean_name(name):
    if not name:
        return ""
    name = str(name).strip().replace('"', "'")
    name = re.sub(r"\s+", " ", name)
    return name


# ============================================================
# Read old components
# ============================================================

def parse_old_components():
    if not OUTPUT_FILE.exists():
        logging.warning("Old file not found: %s", OUTPUT_FILE)
        return {}
    try:
        content = OUTPUT_FILE.read_text(encoding="utf-8")
        pattern = re.compile(
            r'\(\s*"([^"]+)"\s*,\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*([\d.]+)\s*\)'
        )
        result = {}
        for match in pattern.finditer(content):
            ticker = clean_ticker(match.group(1))
            if not ticker:
                continue
            result[ticker] = {
                "name": clean_name(match.group(2)),
                "sector": match.group(3),
                "weight": float(match.group(4)),
            }
        logging.info("Read old data: %d stocks", len(result))
        return result
    except Exception as e:
        logging.exception("Failed to read old file: %s", e)
        return {}


# ============================================================
# Fetch Nasdaq constituents
# ============================================================

def fetch_nasdaq_constituents():
    logging.info("Fetching Nasdaq-100 constituents from Nasdaq API...")
    try:
        response = session.get(NASDAQ_URL, timeout=30)
        response.raise_for_status()
        data = response.json()
        rows = None
        if "data" in data:
            d = data["data"]
            if isinstance(d, dict) and "data" in d:
                rows = d["data"].get("rows", [])
            elif isinstance(d, list):
                rows = d
            else:
                rows = d.get("rows", [])
        if not rows:
            raise RuntimeError("Nasdaq returned empty data")
        result = {}
        for row in rows:
            ticker = clean_ticker(row.get("symbol"))
            name = clean_name(row.get("companyName") or row.get("name"))
            if not ticker:
                continue
            result[ticker] = {"name": name}
        if len(result) < 90:
            raise RuntimeError("Nasdaq returned only %d stocks" % len(result))
        logging.info("Nasdaq: %d constituents", len(result))
        return result
    except Exception as e:
        logging.exception("Nasdaq fetch failed: %s", e)
        return {}


# ============================================================
# Fetch Slickcharts weights
# ============================================================

def fetch_slickcharts_weights():
    logging.info("Fetching weights from Slickcharts...")
    try:
        response = session.get(SLICKCHARTS_URL, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.find("table", class_="table")
        if not table:
            raise RuntimeError("Slickcharts table not found")
        weights = {}
        for row in table.find("tbody").find_all("tr"):
            cols = row.find_all("td")
            if len(cols) < 4:
                continue
            ticker = clean_ticker(cols[2].get_text(strip=True))
            weight_text = cols[3].get_text(strip=True).replace("%", "")
            if not ticker:
                continue
            try:
                weight = float(weight_text)
                if weight > 0:
                    weights[ticker] = round(weight, 2)
            except ValueError:
                continue
        if len(weights) < 80:
            raise RuntimeError("Slickcharts returned only %d weights" % len(weights))
        logging.info("Slickcharts: %d weights", len(weights))
        return weights
    except Exception as e:
        logging.exception("Slickcharts fetch failed: %s", e)
        return {}


# ============================================================
# Get weights (primary + fallback)
# ============================================================

def fetch_weights():
    weights = fetch_slickcharts_weights()
    if weights:
        return weights
    logging.warning("Slickcharts failed, using built-in fallback weights...")
    return dict(FALLBACK_WEIGHTS)


# ============================================================
# Validation
# ============================================================

def validate_data(data):
    if not data:
        logging.error("Final data is empty")
        return False
    count = len(data)
    logging.info("Validating: %d stocks", count)
    if count < 95 or count > 110:
        logging.error("Stock count abnormal: %d", count)
        return False
    for ticker, item in data.items():
        if item["weight"] <= 0:
            logging.error("%s weight abnormal: %.2f", ticker, item["weight"])
            return False
    total_weight = sum(item["weight"] for item in data.values())
    logging.info("Total weight: %.2f%%", total_weight)
    if total_weight < 85 or total_weight > 115:
        logging.error("Total weight abnormal: %.2f%%", total_weight)
        return False
    max_weight = max(item["weight"] for item in data.values())
    if max_weight > 25:
        logging.error("Max weight abnormal: %.2f%%", max_weight)
        return False
    logging.info("Validation passed")
    return True


# ============================================================
# Merge data
# ============================================================

def build_final_data(constituents, weights, old_data):
    final = {}
    old_tickers = set(old_data.keys())
    new_tickers = set(constituents.keys())
    added = sorted(new_tickers - old_tickers)
    removed = sorted(old_tickers - new_tickers)
    fallback = []
    for ticker, info in constituents.items():
        name = info["name"]
        if ticker in weights:
            weight = weights[ticker]
        elif ticker in old_data:
            weight = old_data[ticker]["weight"]
            fallback.append(ticker)
            logging.warning("%s: using old weight %.2f%% (no new data)", ticker, weight)
        elif ticker in FALLBACK_WEIGHTS:
            weight = FALLBACK_WEIGHTS[ticker]
            fallback.append(ticker)
            logging.warning("%s: using fallback weight %.2f%%", ticker, weight)
        else:
            logging.warning("%s: new constituent but no weight, skipping", ticker)
            continue
        if not name and ticker in old_data:
            name = old_data[ticker]["name"]
        sector = old_data[ticker]["sector"] if ticker in old_data else SECTOR_MAP.get(ticker, "Unknown")
        final[ticker] = {
            "name": name,
            "sector": sector,
            "weight": round(float(weight), 2),
        }
    logging.info("Added: %d", len(added))
    logging.info("Removed: %d", len(removed))
    logging.info("Fallback weights: %d", len(fallback))
    if added:
        logging.info("Added stocks: %s", ", ".join(added))
    if removed:
        logging.info("Removed stocks: %s", ", ".join(removed))
    still_missing = [t for t, v in final.items() if v["sector"] == "Unknown"]
    if still_missing:
        logging.warning("Unknown sector for: %s", ", ".join(still_missing))
    return final


# ============================================================
# Backup
# ============================================================

def backup_old_file():
    if not OUTPUT_FILE.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # FIX: use format() instead of % to avoid PosixPath TypeError
    backup_file = BACKUP_DIR / "ndx_components_{}.py".format(timestamp)
    shutil.copy2(OUTPUT_FILE, backup_file)
    logging.info("Backup saved: %s", backup_file)
    backups = sorted(BACKUP_DIR.glob("ndx_components_*.py"), key=lambda x: x.stat().st_mtime, reverse=True)
    for old_backup in backups[30:]:
        try:
            old_backup.unlink()
        except Exception:
            pass


# ============================================================
# Write file
# ============================================================

def write_components(data):
    sorted_items = sorted(data.items(), key=lambda x: x[1]["weight"], reverse=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# Nasdaq-100 Constituents (Auto-Updated)",
        "# Updated: {}".format(now),
        "# Source: Nasdaq API + Slickcharts (with built-in fallback)",
        "#",
        "STOCKS = [",
    ]
    for ticker, item in sorted_items:
        line = '    ("{}", "{}", "{}", {:.2f}),'.format(
            ticker, item["name"], item["sector"], item["weight"]
        )
        lines.append(line)
    lines.append("]")
    lines.append("")
    lines.append("SECTORS = sorted(set(s[2] for s in STOCKS))")
    lines.append("")
    lines.append('LAST_UPDATE = "{}"'.format(now))
    lines.append('DATA_SOURCE = "Nasdaq + Slickcharts"')
    content = "\n".join(lines)
    temp_file = OUTPUT_FILE.with_suffix(".tmp")
    try:
        temp_file.write_text(content, encoding="utf-8")
        temp_file.replace(OUTPUT_FILE)
        logging.info("Successfully wrote: %s (%d stocks)", OUTPUT_FILE, len(sorted_items))
        return True
    except Exception as e:
        logging.exception("Write failed: %s", e)
        if temp_file.exists():
            try:
                temp_file.unlink()
            except Exception:
                pass
        return False


# ============================================================
# Main
# ============================================================

def main():
    print()
    print("=" * 65)
    print(" Nasdaq-100 Auto Updater")
    print("=" * 65)
    logging.info("========== Update started ==========")
    old_data = parse_old_components()
    constituents = fetch_nasdaq_constituents()
    if not constituents:
        logging.error("Failed to fetch Nasdaq constituents")
        print("Nasdaq constituents fetch failed")
        print("ndx_components.py will NOT be modified")
        return 1
    weights = fetch_weights()
    if not weights:
        logging.error("Failed to fetch weights from all sources")
        print("All weight sources failed")
        print("ndx_components.py will NOT be modified")
        return 1
    final_data = build_final_data(constituents, weights, old_data)
    if not validate_data(final_data):
        logging.error("Data validation failed")
        print("Data validation failed")
        print("ndx_components.py will NOT be modified")
        return 1
    backup_old_file()
    if not write_components(final_data):
        print("Write failed")
        return 1
    print()
    print("=" * 65)
    print(" Nasdaq-100 Update Successful")
    print("=" * 65)
    print("  Constituents: {}".format(len(final_data)))
    print("  Output: {}".format(OUTPUT_FILE))
    print("=" * 65)
    logging.info("========== Update successful ==========")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
