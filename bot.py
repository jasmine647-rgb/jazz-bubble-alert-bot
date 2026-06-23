"""
Pump/Dip Alert Bot
------------------
Watches your CoinMarketCap "Invo" watchlist and sends a Telegram alert
whenever a coin's 1-hour price change crosses +/- THRESHOLD_PCT.

Strategy context: a big 1h move = volatility spike. You then watch for a
pullback / reversal after the pump or dip.

Setup:
  1. pip install -r requirements.txt
  2. Copy .env.example to .env and fill in the 3 values.
  3. python bot.py
"""

import os
import time
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# ---- Config (from .env) ----
CMC_API_KEY = os.getenv("CMC_API_KEY", "").strip()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

THRESHOLD_PCT = float(os.getenv("THRESHOLD_PCT", "5"))      # alert when |1h change| >= this
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "180"))        # how often to check (3 min)
COOLDOWN_MINUTES = int(os.getenv("COOLDOWN_MINUTES", "60")) # don't re-alert same coin within this window

# Your "Invo" watchlist (CoinMarketCap coin IDs) pulled from your config export.
# Note: the very long numeric IDs in your export look like custom/user list entries,
# not CMC coin IDs, so they're excluded here. Edit this list freely.
WATCHLIST_IDS = [
    1, 2, 52, 74, 131, 328, 512, 1027, 1321, 1376, 1437, 1586, 1698, 1720,
    1785, 1831, 1839, 1958, 1975, 2010, 2280, 2586, 3602, 3773, 3794, 3964,
    4030, 4157, 4172, 4642, 4705, 4847, 4944, 5426, 5567, 5617, 5632, 5690,
    5692, 5805, 5994, 6210, 6535, 6538, 6636, 6758, 6783, 7080, 7083, 7186,
    7226, 7278, 7334, 8000, 8290, 8646, 8916, 9481, 10603, 10688, 10804,
    11840, 11841, 11857, 13502, 13631, 13855, 14806, 18069, 18876, 19843,
    20362, 20396, 20947, 21159, 21259, 21794, 22691, 22861, 22974, 23095,
    23121, 23149, 24091, 24478, 24911, 25028, 26997, 27075, 28066, 28081,
    28177, 28230, 28301, 28321, 28324, 28541, 28752, 28782, 28850, 28932,
    28933, 29073, 29210, 29270, 29420, 29587, 29743, 29814, 29835, 29870,
    30171, 30372, 30449, 30494, 30712, 30843, 32195, 32521, 32956, 33093,
    33440, 33597, 33788,
]

CMC_URL = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"

# Persisted cooldown state. On GitHub Actions each run is a fresh machine, so we
# load/save the last-alert times from a small JSON file (committed back by the
# workflow) to avoid re-alerting the same coin every run.
import json
STATE_FILE = os.getenv("STATE_FILE", "state.json")
# coin_id (str) -> ISO timestamp of last alert
_last_alert = {}


def load_state():
    global _last_alert
    try:
        with open(STATE_FILE, "r") as f:
            _last_alert = json.load(f)
    except Exception:
        _last_alert = {}


def save_state():
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(_last_alert, f)
    except Exception as e:
        print(f"[state save error] {e}")


def fetch_quotes(ids):
    """Return CMC quote data for the given coin IDs."""
    headers = {"X-CMC_PRO_API_KEY": CMC_API_KEY, "Accept": "application/json"}
    params = {"id": ",".join(str(i) for i in ids), "convert": "USD"}
    r = requests.get(CMC_URL, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("data", {})


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, data=payload, timeout=20)
    except Exception as e:
        print(f"[telegram error] {e}")


def on_cooldown(coin_id):
    last = _last_alert.get(str(coin_id))
    if not last:
        return False
    try:
        last_dt = datetime.fromisoformat(last)
    except Exception:
        return False
    age_min = (datetime.now(timezone.utc) - last_dt).total_seconds() / 60
    return age_min < COOLDOWN_MINUTES


CG_SEARCH_URL = "https://api.coingecko.com/api/v3/search"
CG_TICKERS_URL = "https://api.coingecko.com/api/v3/coins/{id}/tickers"

# symbol -> coingecko id (cached so we don't re-search every loop)
_cg_id_cache = {}


def _coingecko_id(name, symbol):
    """Resolve a CoinGecko coin id from a symbol/name (free, no key)."""
    key = symbol.upper()
    if key in _cg_id_cache:
        return _cg_id_cache[key]
    try:
        r = requests.get(CG_SEARCH_URL, params={"query": symbol}, timeout=20)
        r.raise_for_status()
        coins = r.json().get("coins", [])
        # Prefer an exact symbol match, then fall back to name match.
        match = next((c for c in coins if c.get("symbol", "").upper() == key), None)
        if not match:
            match = next((c for c in coins if c.get("name", "").lower() == name.lower()), None)
        cg_id = match.get("id") if match else None
        _cg_id_cache[key] = cg_id
        return cg_id
    except Exception:
        return None


def get_exchanges(name, symbol):
    """List of exchanges trading this coin, via CoinGecko (free, no API key)."""
    cg_id = _coingecko_id(name, symbol)
    if not cg_id:
        return []
    try:
        r = requests.get(CG_TICKERS_URL.format(id=cg_id), timeout=20)
        r.raise_for_status()
        tickers = r.json().get("tickers", [])
        names = []
        for t in tickers:
            ex = t.get("market", {}).get("name")
            if ex and ex not in names:
                names.append(ex)
        return names
    except Exception:
        return []


def tradingview_link(symbol):
    """Link that opens a search/chart for the symbol on TradingView."""
    return f"https://www.tradingview.com/chart/?symbol={symbol}USDT"


def build_card(name, symbol, rank, change_1h, exchanges):
    """Format an alert that mirrors the Crypto Bubbles Monitor card."""
    arrow = "🟢" if change_1h > 0 else "🔴"
    if exchanges:
        ex_line = ", ".join(exchanges[:12])
        if len(exchanges) > 12:
            ex_line += f", +{len(exchanges) - 12} more"
    else:
        ex_line = "—"
    tv = tradingview_link(symbol)
    return (
        f"{arrow} <b>Crypto Bubbles Monitor</b>\n\n"
        f"<b>Rank</b>\n{rank}\n\n"
        f"<b>Name</b>\n{name}\n\n"
        f"<b>Symbol</b>\n{symbol}\n\n"
        f"<b>1 hour percent change:</b>\n{change_1h:+.1f}%\n\n"
        f"<b>Exchanges</b>\n{ex_line}\n\n"
        f"📊 <b>Chart</b>\n<a href=\"{tv}\">Open in TradingView</a>"
    )


def check_once():
    try:
        data = fetch_quotes(WATCHLIST_IDS)
    except Exception as e:
        print(f"[fetch error] {e}")
        return

    hits = 0
    for coin_id, info in data.items():
        try:
            usd = info["quote"]["USD"]
            change_1h = usd.get("percent_change_1h")
            price = usd.get("price")
            symbol = info.get("symbol", "?")
            name = info.get("name", "?")
            if change_1h is None:
                continue
            if abs(change_1h) >= THRESHOLD_PCT and not on_cooldown(coin_id):
                rank = info.get("cmc_rank", "?")
                exchanges = get_exchanges(name, symbol)
                msg = build_card(name, symbol, rank, change_1h, exchanges)
                send_telegram(msg)
                _last_alert[str(coin_id)] = datetime.now(timezone.utc).isoformat()
                hits += 1
                print(f"ALERT {symbol} {change_1h:+.2f}%")
        except Exception as e:
            print(f"[parse error] {coin_id}: {e}")

    stamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{stamp}] checked {len(data)} coins, {hits} alert(s)")


def main():
    missing = [k for k, v in {
        "CMC_API_KEY": CMC_API_KEY,
        "TELEGRAM_TOKEN": TELEGRAM_TOKEN,
        "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
    }.items() if not v]
    if missing:
        raise SystemExit(f"Missing in .env: {', '.join(missing)}")

    load_state()

    # RUN_MODE=once -> single check then exit (used by GitHub Actions schedule).
    # Default -> continuous loop (used when running on your own PC).
    if os.getenv("RUN_MODE", "").lower() == "once":
        check_once()
        save_state()
        return

    print(f"Pump/Dip bot started. Threshold ±{THRESHOLD_PCT}% (1h), "
          f"polling every {POLL_SECONDS}s, cooldown {COOLDOWN_MINUTES}m.")
    send_telegram(f"✅ Pump/Dip bot online. Alerting on ±{THRESHOLD_PCT}% 1h moves.")

    while True:
        check_once()
        save_state()
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
