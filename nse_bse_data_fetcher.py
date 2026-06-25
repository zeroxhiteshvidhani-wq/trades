"""
A script to fetch live and historical data for stocks and indices from NSE and BSE.

This script uses the functions from yahoo.py to fetch data from Yahoo Finance.
"""

from yahoo import fetch_yahoo_quote, fetch_yahoo_history
import pandas as pd

# A list of symbols to fetch data for.
# The script will automatically resolve these to the correct Yahoo Finance ticker.
# For example, 'RELIANCE' becomes 'RELIANCE.NS' for NSE.
# 'SENSEX' becomes '^BSESN' for BSE.
SYMBOLS_TO_FETCH = [
    "RELIANCE",  # NSE stock
    "TCS",       # NSE stock
    "INFY",      # NSE stock
    "SENSEX",    # BSE index
    "NIFTY 50",  # NSE index
]


def get_quotes():
    """Fetches and prints the latest quotes for the symbols."""
    print("--- Fetching Live Quotes ---")
    for symbol in SYMBOLS_TO_FETCH:
        print(f"Fetching quote for: {symbol}")
        quote = fetch_yahoo_quote(symbol)
        if "error" in quote:
            print(f"  Error: {quote['error']}")
        else:
            # Using pandas to print a nice table-like output for the quote
            quote_df = pd.DataFrame([quote])
            print(quote_df.to_string())
        print("-" * 30)


def get_history():
    """Fetches and prints historical data for a single symbol."""
    print("\n--- Fetching Historical Data ---")
    symbol = "RELIANCE"
    print(f"Fetching 1 month of historical data for: {symbol}")
    history = fetch_yahoo_history(symbol, period="1mo", interval="1d")
    if isinstance(history, dict) and "error" in history:
        print(f"  Error: {history['error']}")
    else:
        print(history)


if __name__ == "__main__":
    get_quotes()
    get_history()
    print("
Script finished.")
    print("You can run this script using: python nse_bse_data_fetcher.py")
