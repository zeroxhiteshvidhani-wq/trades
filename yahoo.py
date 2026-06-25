"""
pmClient/yahoo.py
──────────────────
Yahoo Finance live quote + history fetcher, powered by yfinance.

Why your old Yahoo feed wasn't working (most likely):
  1. Symbols like "RELIANCE" or "NIFTY 50" were sent straight to yfinance.
     Yahoo needs ".NS" suffixes for NSE equities and special tickers for
     indices (^NSEI, ^NSEBANK) — without this, yfinance returns empty data
     and your app silently fell back to simulated candles.
  2. `Ticker.fast_info` occasionally returns None/empty fields — needs a
     fallback to `.history()`.

This module fixes both, and NEVER raises — it always returns either a
populated dict / DataFrame or {"error": "..."} so callers can branch safely.
"""

import time
from datetime import datetime

import yfinance as yf

# ───────────────────────────────────────────
# SYMBOL MAPPING — internal name -> Yahoo ticker (indices need this;
# yfinance has no generic way to guess these from a plain name)
# ───────────────────────────────────────────
YAHOO_SYMBOL_MAP = {
    "NIFTY 50": "^NSEI",
    "NIFTY50": "^NSEI",
    "NIFTY": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "FINNIFTY": "NIFTY_FIN_SERVICE.NS",
    "SENSEX": "^BSESN",
    "MIDCPNIFTY": "^NSEMDCP50",
}

# Small in-process caches so a Streamlit rerun loop doesn't hammer Yahoo
# with a fresh request for the same symbol every 100ms.
_QUOTE_CACHE = {}
_CACHE_TTL_SECONDS = 5

# Once we figure out which Yahoo ticker actually has data for an internal
# symbol (e.g. "RELIANCE" -> "RELIANCE.NS", but "AAPL" -> "AAPL" as-is),
# we remember it so we don't re-probe Yahoo on every rerun.
_SYMBOL_RESOLUTION_CACHE = {}


def to_yahoo_symbol(symbol: str) -> str:
    """
    Quick, network-free guess at a Yahoo ticker. Used only as a label/
    fallback; `_resolve_yahoo_symbol` below does the verified version that
    fetch_yahoo_quote / fetch_yahoo_history actually rely on.
    """
    if not symbol:
        return symbol
    key = symbol.strip().upper()
    if key in YAHOO_SYMBOL_MAP:
        return YAHOO_SYMBOL_MAP[key]
    if "." in symbol or "^" in symbol or "-" in symbol:
        return symbol
    return f"{key}.NS"


def _resolve_yahoo_symbol(symbol: str):
    """
    Figure out which Yahoo ticker actually returns data for this internal
    symbol. Tries, in order: the explicit index map, the symbol exactly as
    typed (covers US stocks like AAPL, crypto like BTC-USD), then the
    symbol with a '.NS' suffix (covers NSE equities like RELIANCE, TCS).
    The winning ticker is cached so we only probe once per symbol.
    Returns the resolved ticker string, or None if nothing worked.
    """
    if not symbol:
        return None
    key = symbol.strip().upper()

    if key in YAHOO_SYMBOL_MAP:
        return YAHOO_SYMBOL_MAP[key]

    if key in _SYMBOL_RESOLUTION_CACHE:
        return _SYMBOL_RESOLUTION_CACHE[key]

    # Already fully-qualified — caret (index), dot (exchange suffix), or
    # dash (crypto pairs like BTC-USD) — don't guess further.
    if "." in symbol or "^" in symbol or "-" in symbol:
        candidates = [symbol]
    else:
        candidates = [symbol, f"{key}.NS"]

    for candidate in candidates:
        try:
            hist = yf.Ticker(candidate).history(period="5d", interval="1d")
            if hist is not None and not hist.empty:
                _SYMBOL_RESOLUTION_CACHE[key] = candidate
                return candidate
        except Exception:
            continue

    return None


def fetch_yahoo_quote(symbol: str) -> dict:
    """
    Fetch a near-live quote for `symbol` (internal name, e.g. 'RELIANCE',
    'NIFTY 50', or a raw ticker like 'AAPL' / 'BTC-USD').

    Returns a dict with (at minimum):
        regularMarketPrice, close, previousClose, open,
        dayHigh, dayLow, volume, change_percent, yahoo_symbol, fetched_at
    On failure returns: {"error": "<message>"}
    """
    yahoo_sym = _resolve_yahoo_symbol(symbol)
    if not yahoo_sym:
        return {"error": f"Could not resolve a valid Yahoo ticker for '{symbol}' "
                          f"(tried as typed, and with a '.NS' suffix)"}

    now = time.time()
    cached = _QUOTE_CACHE.get(yahoo_sym)
    if cached and (now - cached["_ts"]) < _CACHE_TTL_SECONDS:
        return cached["data"]

    try:
        ticker = yf.Ticker(yahoo_sym)

        price = prev_close = day_open = day_high = day_low = volume = None

        # Fast path: fast_info (cheap, no full history download)
        try:
            fi = ticker.fast_info
            price = fi.get("lastPrice") or fi.get("last_price")
            prev_close = fi.get("previousClose") or fi.get("previous_close")
            day_open = fi.get("open")
            day_high = fi.get("dayHigh") or fi.get("day_high")
            day_low = fi.get("dayLow") or fi.get("day_low")
            volume = fi.get("lastVolume") or fi.get("last_volume")
        except Exception:
            pass

        # Fallback: pull last daily candles if fast_info gave nothing usable
        if not price or price <= 0:
            hist = ticker.history(period="5d", interval="1d")
            if hist is None or hist.empty:
                return {"error": f"yfinance returned no data for '{yahoo_sym}' "
                                  f"(internal name was '{symbol}')"}
            last_row = hist.iloc[-1]
            price = float(last_row["Close"])
            prev_close = float(hist.iloc[-2]["Close"]) if len(hist) > 1 else price
            day_open = float(last_row["Open"])
            day_high = float(last_row["High"])
            day_low = float(last_row["Low"])
            volume = float(last_row["Volume"])

        if not price or price <= 0:
            return {"error": f"yfinance returned an invalid price for '{yahoo_sym}'"}

        prev_close = prev_close or price
        change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0.0

        data = {
            "symbol": symbol,
            "yahoo_symbol": yahoo_sym,
            "regularMarketPrice": round(float(price), 2),
            "close": round(float(price), 2),
            "previousClose": round(float(prev_close), 2),
            "open": round(float(day_open), 2) if day_open else round(float(price), 2),
            "dayHigh": round(float(day_high), 2) if day_high else round(float(price), 2),
            "dayLow": round(float(day_low), 2) if day_low else round(float(price), 2),
            "volume": int(volume) if volume else 0,
            "change_percent": round(change_pct, 2),
            "fetched_at": datetime.now().strftime("%H:%M:%S"),
        }
        _QUOTE_CACHE[yahoo_sym] = {"_ts": now, "data": data}
        return data

    except Exception as e:
        return {"error": f"yfinance error for '{yahoo_sym}': {e}"}


def fetch_yahoo_history(symbol: str, period: str = "1mo", interval: str = "1d"):
    """
    Fetch historical OHLCV for `symbol`.

    Returns a pandas DataFrame with columns Open/High/Low/Close/Volume on
    success, or {"error": "..."} dict on failure (never raises).
    """
    yahoo_sym = _resolve_yahoo_symbol(symbol)
    if not yahoo_sym:
        return {"error": f"Could not resolve a valid Yahoo ticker for '{symbol}'"}
    try:
        ticker = yf.Ticker(yahoo_sym)
        df = ticker.history(period=period, interval=interval)
        if df is None or df.empty:
            return {"error": f"yfinance returned no historical data for '{yahoo_sym}'"}
        return df[["Open", "High", "Low", "Close", "Volume"]].copy()
    except Exception as e:
        return {"error": f"yfinance error for '{yahoo_sym}': {e}"}
