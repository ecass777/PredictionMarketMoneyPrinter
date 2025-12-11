import logging
import os
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

from .market_cache import load_market_lookup

logger = logging.getLogger(__name__)

try:
    from py_clob_client.client import ClobClient
except Exception:  # pragma: no cover - optional dependency
    ClobClient = None


DEFAULT_HOST = "https://clob.polymarket.com"
DEFAULT_CHAIN_ID = 137
_live_price_cache: Dict[str, Tuple[float, float]] = {}
_live_cache_ttl = 60  # seconds
_clob_client: Optional["ClobClient"] = None


def _get_clob_client() -> "ClobClient":
    if ClobClient is None:
        raise ImportError("py_clob_client is required for live pricing")
    global _clob_client
    if _clob_client is None:
        api_key = os.getenv("API_KEY") or os.getenv("POLYMARKET_API_KEY")
        _clob_client = ClobClient(DEFAULT_HOST, key=api_key, chain_id=DEFAULT_CHAIN_ID) if api_key else ClobClient(
            DEFAULT_HOST, chain_id=DEFAULT_CHAIN_ID
        )
    return _clob_client


def get_token_id_for_slug_outcome(slug: str, outcome: str) -> Optional[str]:
    _, slug_to_token_map = load_market_lookup()
    if not slug_to_token_map:
        return None

    token_map = slug_to_token_map.get(str(slug))
    if not token_map:
        return None

    if outcome in token_map:
        return token_map[outcome]

    outcome_lower = str(outcome).lower()
    for label, token_id in token_map.items():
        if str(label).lower() == outcome_lower:
            return token_id
    return None


def get_live_price(token_id: str) -> Optional[float]:
    """
    Fetch the last trade price for a token, cached for a short TTL.
    """
    if not token_id:
        return None

    now = time.time()
    cached = _live_price_cache.get(token_id)
    if cached and now - cached[1] < _live_cache_ttl:
        return cached[0]

    try:
        client = _get_clob_client()
        response = client.get_last_trade_price(token_id=token_id)
        price = response.get("price") if isinstance(response, dict) else None
        if price is not None:
            _live_price_cache[token_id] = (float(price), now)
            return float(price)
    except Exception as exc:
        logger.warning("Failed to fetch live price for %s: %s", token_id, exc)
    return None


def get_order_book_prices_from_csv(slug: str, outcome: str, price_type: str = "mid") -> Tuple[Optional[float], Optional[float]]:
    """
    Read ./data/book_data/{slug}_{outcome}.csv and return (price, size) for ask/bid/mid.
    """
    price_type = (price_type or "mid").lower()
    path = Path("data") / "book_data" / f"{slug}_{outcome}.csv"
    if not path.exists():
        logger.debug("Order book CSV not found: %s", path)
        return None, None

    try:
        df = pd.read_csv(path)
    except Exception as exc:
        logger.warning("Unable to read %s: %s", path, exc)
        return None, None

    if "side" not in df.columns or "price" not in df.columns:
        return None, None

    def _pick(row_side: str, chooser):
        relevant = df[df["side"].str.lower() == row_side]
        if relevant.empty:
            return None, None
        chosen = chooser(relevant["price"])
        row = relevant.loc[relevant["price"] == chosen].iloc[0]
        return float(row["price"]), float(row["size"]) if "size" in row else None

    if price_type == "ask":
        return _pick("ask", min)
    if price_type == "bid":
        return _pick("bid", max)
    if price_type == "mid":
        ask_df = df[df["side"].str.lower() == "ask"]
        bid_df = df[df["side"].str.lower() == "bid"]
        if ask_df.empty or bid_df.empty:
            return None, None
        min_ask = ask_df["price"].min()
        max_bid = bid_df["price"].max()
        return float((min_ask + max_bid) / 2.0), None
    return None, None


def get_actual_user_price(slug: str, outcome: str, user_id: Optional[str]) -> Tuple[Optional[float], Optional[float]]:
    """
    Return the latest price paid and size for the given slug/outcome from a user's enriched trades parquet.
    """
    if not user_id:
        return None, None

    path = Path("data") / "user_trades" / f"{user_id}_enriched_transactions.parquet"
    if not path.exists():
        logger.debug("User trades parquet not found: %s", path)
        return None, None

    try:
        df = pd.read_parquet(path)
    except Exception as exc:
        logger.warning("Unable to read user trades parquet %s: %s", path, exc)
        return None, None

    if "timeStamp_erc1155" not in df.columns:
        logger.debug("Missing timeStamp_erc1155 column in %s", path)
        return None, None

    df["timeStamp_erc1155"] = pd.to_datetime(df["timeStamp_erc1155"], errors="coerce")
    filtered = df[(df["market_slug"] == slug) & (df["outcome"] == outcome) & df["timeStamp_erc1155"].notna()]
    if filtered.empty:
        return None, None

    latest = filtered.sort_values("timeStamp_erc1155").iloc[-1]
    price = latest.get("price_paid_per_token")
    shares = latest.get("shares")
    if price is None:
        return None, None
    try:
        return float(price), float(shares) if shares is not None else None
    except (TypeError, ValueError):
        return None, None
