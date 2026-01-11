import logging
from typing import Optional

import yfinance as yf
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


class StockResult(BaseModel):
    symbol: str
    price: float = Field(..., description="Latest trading price")
    currency: Optional[str] = None
    exchange: Optional[str] = None
    source: str = "yfinance"


_SYMBOL_NORMALIZATION = {
    "HCL": "HCLTECH",
    "HCLTECH": "HCLTECH",
    "INFY": "INFY",
    "TCS": "TCS",
    "RELIANCE": "RELIANCE",
}


def _resolve_symbol(user_symbol: str) -> str:
    sym = user_symbol.strip().upper()
    return _SYMBOL_NORMALIZATION.get(sym, sym)


def _latest_price(ticker: yf.Ticker) -> Optional[float]:
    info = ticker.fast_info
    price = info.get("last_price")
    if price is not None:
        return float(price)

    try:
        hist = ticker.history(period="1d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        logger.debug("History lookup failed for %s", ticker.ticker, exc_info=True)
    return None


def fetch_stock(symbol: str, exchange_suffix: str = ".NS") -> StockResult:
    """
    Fetch latest stock price for an Indian ticker using yfinance (e.g., HCLTECH -> HCLTECH.NS).
    Includes simple symbol normalization and price fallbacks.
    """
    if not symbol:
        raise ValueError("Symbol is required")

    resolved = _resolve_symbol(symbol)
    ticker = yf.Ticker(f"{resolved}{exchange_suffix}")
    price = _latest_price(ticker)
    if price is None:
        # attempt without suffix as fallback
        alt_ticker = yf.Ticker(resolved)
        price = _latest_price(alt_ticker)
        if price is None:
            raise ValueError(f"Price unavailable for symbol {resolved}{exchange_suffix}")

    try:
        info = ticker.fast_info if price is not None else alt_ticker.fast_info
        return StockResult(
            symbol=resolved,
            price=price,
            currency=info.get("currency"),
            exchange=info.get("exchange"),
        )
    except (TypeError, ValidationError) as exc:
        logger.exception("StockResult validation failed")
        raise ValueError(f"Malformed stock data: {exc}") from exc
