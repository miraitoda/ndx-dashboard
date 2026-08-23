#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Nasdaq-100 Auto Updater
=======================

Logic:
1. Nasdaq API: fetch current constituents (ticker + name)
2. Schwab: fetch top 20 official QQQ weights
3. Built-in estimates: remaining ~82 stocks proportional weights
4. Normalize to 100%, write ndx_components.py

Dependencies: requests, beautifulsoup4
"""

import os
import re
import shutil
import logging
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup


# ============================================================
# Config
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = BASE_DIR / "ndx_components.py"
BACKUP_DIR = BASE_DIR / "backup_ndx"
LOG_FILE = BASE_DIR / "update_ndx.log"

NASDAQ_URL = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"
SCHWAB_URL = (
    "https://www.schwab.wallst.com/schwab/Prospect/research/etfs/schwabETF/index.asp"
    "?symbol=QQQ&type=holdings"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


# ============================================================
# Built-in fallback estimates for remaining ~82 stocks
# Used when Schwab fetch fails, or for stocks outside top 20
# Snapshot: 2026-08-16 (proportional estimates)
# ============================================================

FALLBACK_ESTIMATES = {
    "SHOP": 1.15, "QCOM": 1.05, "TXN": 0.95, "ADBE": 0.90,
    "KLAC": 0.88, "INTU": 0.85, "APP": 0.82, "ARM": 0.78,
    "SBUX": 0.75, "PDD": 0.72, "ABNB": 0.70, "ADP": 0.68,
    "CEG": 0.65, "DASH": 0.62, "MELI": 0.60, "MAR": 0.58,
    "CSX": 0.56, "CMCSA": 0.55, "DDOG": 0.53, "MNST": 0.52,
    "CDNS": 0.50, "REGN": 0.48, "LITE": 0.47, "MDLZ": 0.46,
    "SNPS": 0.45, "CTAS": 0.44, "ROST": 0.43, "NBIS": 0.42,
    "HON": 0.41, "ORLY": 0.40, "WBD": 0.39, "MPWR": 0.38,
    "PCAR": 0.37, "AEP": 0.36, "TER": 0.35, "BKR": 0.34,
    "NXPI": 0.33, "FAST": 0.32, "CRWV": 0.31, "FANG": 0.30,
    "ALAB": 0.29, "ADSK": 0.28, "PYPL": 0.27, "HONA": 0.26,
    "RKLB": 0.25, "AXON": 0.24, "XEL": 0.23, "WDAY": 0.22,
    "CCEP": 0.21, "EXC": 0.20, "FER": 0.19, "TTWO": 0.18,
    "TRI": 0.17, "ODFL": 0.16, "IDXX": 0.15, "PAYX": 0.14,
    "MCHP": 0.13, "KDP": 0.12, "ROP": 0.11, "MSTR": 0.10,
    "DXCM": 0.09, "GEHC": 0.08, "ALNY": 0.07, "KHC": 0.06,
    "CPRT": 0.05, "SNDK": 0.65, "LIN": 0.62, "CRWD": 0.60,
    "STX": 0.58, "MRVL": 0.55, "TMUS": 0.54, "PEP": 0.52,
    "ADI": 0.50, "WDC": 0.48, "GILD": 0.45, "BKNG": 0.42,
    "ISRG": 0.40, "VRTX": 0.38, "FTNT": 0.36, "AMGN": 0.58,
    "ASML": 0.92, "SPCX": 0.01,
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

NAME_MAP = {
    "AAPL": "Apple Inc.", "AMAT": "Applied Materials Inc", "AMGN": "Amgen Inc",
    "CMCSA": "Comcast Corp", "INTC": "Intel Corp", "KLAC": "KLA Corporation",
    "PCAR": "Paccar Inc", "CTAS": "Cintas Corp", "PAYX": "Paychex Inc",
    "LRCX": "Lam Research Corp", "NVDA": "Nvidia Corp", "AVGO": "Broadcom Inc",
    "CSCO": "Cisco Systems Inc", "COST": "Costco Wholesale Corp", "TXN": "Texas Instruments",
    "QCOM": "Qualcomm Inc", "ADP": "Automatic Data Processing", "ISRG": "Intuitive Surgical Inc",
    "MAR": "Marriott International", "CSX": "CSX Corporation", "GILD": "Gilead Sciences Inc",
    "MELI": "Mercado Libre Inc", "MDLZ": "Mondelez International", "ADI": "Analog Devices Inc",
    "REGN": "Regeneron Pharmaceuticals", "VRTX": "Vertex Pharmaceuticals", "SNPS": "Synopsys Inc",
    "DXCM": "DexCom Inc", "KDP": "Keurig Dr Pepper Inc", "CPRT": "Copart Inc",
    "MSFT": "Microsoft Corp", "AMZN": "Amazon.com Inc", "GOOGL": "Alphabet Inc Class A",
    "GOOG": "Alphabet Inc Class C", "META": "Meta Platforms Inc", "TSLA": "Tesla Inc",
    "NFLX": "Netflix Inc", "ADBE": "Adobe Inc", "INTU": "Intuit Inc",
    "BKNG": "Booking Holdings Inc", "PYPL": "PayPal Holdings Inc", "WDAY": "Workday Inc",
    "ABNB": "Airbnb Inc", "DASH": "DoorDash Inc", "DDOG": "Datadog Inc",
    "APP": "Applovin Corp", "MSTR": "Strategy Inc", "ALNY": "Alnylam Pharmaceuticals",
    "KHC": "Kraft Heinz Co", "GEHC": "GE HealthCare Technologies", "MU": "Micron Technology Inc",
    "AMD": "Advanced Micro Devices", "ASML": "ASML Holding NV", "PLTR": "Palantir Technologies Inc",
    "PANW": "Palo Alto Networks Inc", "ARM": "Arm Holdings plc", "WDC": "Western Digital Corp",
    "FTNT": "Fortinet Inc", "CEG": "Constellation Energy Corp", "ROP": "Roper Technologies Inc",
    "LITE": "Lumentum Holdings Inc", "NBIS": "Nebius Group NV", "HON": "Honeywell International Inc",
    "ORLY": "O'Reilly Automotive Inc", "WBD": "Warner Bros Discovery Inc", "MPWR": "Monolithic Power Systems Inc",
    "AEP": "American Electric Power Co", "TER": "Teradyne Inc", "BKR": "Baker Hughes Co",
    "NXPI": "NXP Semiconductors NV", "FAST": "Fastenal Co", "CRWV": "CoreWeave Inc",
    "FANG": "Diamondback Energy Inc", "ALAB": "Astera Labs Inc", "ADSK": "Autodesk Inc",
    "HONA": "Honeywell Aerospace Inc", "RKLB": "Rocket Lab Corp", "AXON": "Axon Enterprise Inc",
    "XEL": "Xcel Energy Inc", "CCEP": "Coca-Cola Europacific Partners", "EXC": "Exelon Corp",
    "FER": "Ferrovial NV", "TTWO": "Take-Two Interactive Software", "TRI": "Thomson Reuters Corp",
    "ODFL": "Old Dominion Freight Line", "IDXX": "Idexx Laboratories Inc", "MCHP": "Microchip Technology Inc",
    "SBUX": "Starbucks Corp", "PDD": "PDD Holdings Inc", "MNST": "Monster Beverage Corp",
    "CDNS": "Cadence Design Systems", "ROST": "Ross Stores Inc", "SHOP": "Shopify Inc",
    "TMUS": "T-Mobile US Inc", "PEP": "PepsiCo Inc", "LIN": "Linde plc",
    "CRWD": "CrowdStrike Holdings Inc", "STX": "Seagate Technology Holdings", "MRVL": "Marvell Technology Inc",
    "SNDK": "Sandisk Corp", "SPCX": "Space Exploration Technologies Corp",
}


# ============================================================
# NEW: Company name cleaner (post-processing)
# ============================================================

def clean_company_name(name):
    """
    Remove common suffixes like 'Common Stock', 'Inc.', 'Corp.', 'Class A', etc.
    """
    if not name:
        return ""
    # Pattern matches suffixes at the end of the string
    suffixes = [
        r"Common Stock", r"Common", r"Capital Stock",
        r"Inc\.?", r"Corp\.?", r"Corporation", r"Company", r"Co\.?",
        r"Class [A-C]", r"Class A", r"Class B", r"Class C",
        r"Holdings", r"plc", r"NV", r"Ltd\.?", r"Limited",
        r"Technologies", r"International", r"Group", r"Enterprises?",
    ]
    # Build regex: optional leading space, case-insensitive, at end
    pattern = r"\s*(?:" + "|".join(suffixes) + r")\s*$"
    cleaned = re.sub(pattern, "", name, flags=re.I).strip()
    # If result is empty, return original (fallback)
    return cleaned if cleaned else name


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
    return re.sub(r"\s+", " ", str(name).strip().replace('"', "'"))


# ============================================================
# Read old
# ============================================================

def parse_old_components():
    if not OUTPUT_FILE.exists():
        return {}
    try:
        content = OUTPUT_FILE.read_text(encoding="utf-8")
        pattern = re.compile(
            r'\(\s*"([^"]+)"\s*,\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*([\d.]+)\s*\)'
        )
        result = {}
        for m in pattern.finditer(content):
            t = clean_ticker(m.group(1))
            if t:
                result[t] = {
                    "name": clean_name(m.group(2)),
                    "sector": m.group(3),
                    "weight": float(m.group(4)),
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
            if ticker:
                result[ticker] = {"name": name}
        if len(result) < 90:
            raise RuntimeError("Nasdaq returned only %d stocks" % len(result))
        logging.info("Nasdaq: %d constituents", len(result))
        return result
    except Exception as e:
        logging.exception("Nasdaq fetch failed: %s", e)
        return {}


# ============================================================
# Fetch Schwab top 20 weights
# ============================================================

def fetch_schwab_weights():
    """Scrape top 20 QQQ holdings weights from Schwab official page."""
    logging.info("Fetching top 20 weights from Schwab...")
    try:
        response = session.get(SCHWAB_URL, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        tables = soup.find_all("table")
        if len(tables) < 2:
            raise RuntimeError("Schwab holdings table not found")
        # Second table contains the holdings
        table = tables[1]
        rows = table.find_all("tr")
        weights = {}
        for row in rows[1:]:  # skip header
            cols = row.find_all("td")
            if len(cols) >= 3:
                ticker = cols[0].get_text(strip=True).upper()
                weight_text = cols[2].get_text(strip=True).replace("%", "")
                try:
                    weight = float(weight_text)
                    if weight > 0:
                        weights[ticker] = round(weight, 2)
                except ValueError:
                    continue
        if len(weights) < 10:
            raise RuntimeError("Schwab returned only %d weights" % len(weights))
        logging.info("Schwab: %d weights (top 20)", len(weights))
        return weights
    except Exception as e:
        logging.exception("Schwab fetch failed: %s", e)
        return {}


# ============================================================
# Build weights: Schwab top 20 + fallback estimates for rest
# ============================================================

def build_weights(constituents):
    """
    1. Try to fetch top 20 from Schwab
    2. Fill remaining stocks from FALLBACK_ESTIMATES
    3. Normalize to 100%
    """
    # Step 1: Schwab top 20
    schwab_weights = fetch_schwab_weights()
    if schwab_weights:
        logging.info("Using Schwab top 20 weights")
        top20 = schwab_weights
    else:
        logging.warning("Schwab failed, using built-in top 20 fallback")
        # Extract top 20 from FALLBACK_ESTIMATES
        top20_tickers = sorted(
            FALLBACK_ESTIMATES, key=FALLBACK_ESTIMATES.get, reverse=True
        )[:20]
        top20 = {t: FALLBACK_ESTIMATES[t] for t in top20_tickers}

    # Step 2: Fill remaining stocks
    matched = dict(top20)
    remaining = [t for t in constituents if t not in matched]
    remaining_estimates = {t: FALLBACK_ESTIMATES.get(t, 0.01) for t in remaining}

    # Calculate budget for remaining stocks
    top20_sum = sum(matched.values())
    remaining_budget = 100.0 - top20_sum
    remaining_total = sum(remaining_estimates.values())

    for t in remaining:
        if remaining_total > 0:
            ratio = remaining_estimates[t] / remaining_total
            matched[t] = round(remaining_budget * ratio, 2)
        else:
            matched[t] = round(remaining_budget / len(remaining), 2)

    # Step 3: Normalize to exactly 100%
    total = sum(matched.values())
    for t in matched:
        matched[t] = round(matched[t] / total * 100, 2)
    diff = round(100.0 - sum(matched.values()), 2)
    if diff != 0:
        max_t = max(matched, key=matched.get)
        matched[max_t] = round(matched[max_t] + diff, 2)

    return matched


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
    total = sum(v["weight"] for v in data.values())
    logging.info("Total weight: %.2f%%", total)
    if total < 99.9 or total > 100.1:
        logging.error("Total weight abnormal: %.2f%%", total)
        return False
    mx = max(v["weight"] for v in data.values())
    if mx > 25:
        logging.error("Max weight abnormal: %.2f%%", mx)
        return False
    logging.info("Validation passed")
    return True


# ============================================================
# Merge
# ============================================================

def build_final_data(constituents, weights, old_data):
    final = {}
    old_tickers = set(old_data.keys())
    new_tickers = set(constituents.keys())
    added = sorted(new_tickers - old_tickers)
    removed = sorted(old_tickers - new_tickers)

    for ticker, info in constituents.items():
        # Determine raw name from API, old data, or NAME_MAP
        raw_name = info["name"] or old_data.get(ticker, {}).get("name") or NAME_MAP.get(ticker, ticker)
        # Apply post-processing to clean suffixes
        clean_name_final = clean_company_name(raw_name)

        sector = old_data.get(ticker, {}).get("sector") or SECTOR_MAP.get(ticker, "Unknown")
        final[ticker] = {
            "name": clean_name_final,
            "sector": sector,
            "weight": weights.get(ticker, 0.01),
        }

    logging.info("Added: %d", len(added))
    logging.info("Removed: %d", len(removed))
    if added:
        logging.info("Added stocks: %s", ", ".join(added))
    if removed:
        logging.info("Removed stocks: %s", ", ".join(removed))
    return final


# ============================================================
# Backup
# ============================================================

def backup_old_file():
    if not OUTPUT_FILE.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bf = BACKUP_DIR / "ndx_components_{}.py".format(ts)
    shutil.copy2(OUTPUT_FILE, bf)
    logging.info("Backup saved: %s", bf)
    backups = sorted(BACKUP_DIR.glob("ndx_components_*.py"), key=lambda x: x.stat().st_mtime, reverse=True)
    for old in backups[30:]:
        try:
            old.unlink()
        except Exception:
            pass


# ============================================================
# Write
# ============================================================

def write_components(data):
    items = sorted(data.items(), key=lambda x: x[1]["weight"], reverse=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# Nasdaq-100 Constituents (Auto-Updated)",
        "# Updated: {}".format(now),
        "# Source: Nasdaq API + Schwab Official Top 20 + Estimates",
        "#",
        "STOCKS = [",
    ]
    for ticker, item in items:
        lines.append('    ("{}", "{}", "{}", {:.2f}),'.format(
            ticker, item["name"], item["sector"], item["weight"]
        ))
    lines.append("]")
    lines.append("")
    lines.append("SECTORS = sorted(set(s[2] for s in STOCKS))")
    lines.append("")
    lines.append('LAST_UPDATE = "{}"'.format(now))
    lines.append('DATA_SOURCE = "Nasdaq + Schwab"')
    content = "\n".join(lines)
    tmp = OUTPUT_FILE.with_suffix(".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(OUTPUT_FILE)
        logging.info("Wrote: %s (%d stocks)", OUTPUT_FILE, len(items))
        return True
    except Exception as e:
        logging.exception("Write failed: %s", e)
        if tmp.exists():
            try:
                tmp.unlink()
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
        print("Nasdaq fetch failed. ndx_components.py NOT modified.")
        return 1

    weights = build_weights(constituents)
    logging.info("Built weights for %d stocks", len(weights))

    final_data = build_final_data(constituents, weights, old_data)

    if not validate_data(final_data):
        print("Validation failed. ndx_components.py NOT modified.")
        return 1

    backup_old_file()
    if not write_components(final_data):
        print("Write failed.")
        return 1

    print()
    print("=" * 65)
    print(" Update Successful")
    print("=" * 65)
    print("  Constituents: {}".format(len(final_data)))
    print("  Output: {}".format(OUTPUT_FILE))
    print("=" * 65)
    logging.info("========== Update successful ==========")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
