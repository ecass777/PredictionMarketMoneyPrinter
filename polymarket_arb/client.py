import logging
import time
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin

import requests

from .config import POLYMARKET_API_BASE, POLYMARKET_API_KEY
from .models import Market, Outcome


logger = logging.getLogger(__name__)


class PolymarketAPIError(Exception):
    """Base exception for Polymarket client errors."""


class MarketFetchError(PolymarketAPIError):
    """Raised when fetching markets fails after retries."""


class OrderPlacementError(PolymarketAPIError):
    """Raised when placing an order fails after retries."""


class PolymarketClient:
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None, max_retries: int = 3,
                 backoff_seconds: float = 0.5):
        self.base_url = base_url or POLYMARKET_API_BASE
        self.api_key = api_key or POLYMARKET_API_KEY
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _request_with_retry(self, method, url: str, *, operation: str, **kwargs) -> requests.Response:
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug("%s request to %s (attempt %s/%s)", operation, url, attempt, self.max_retries)
                response = method(url, **kwargs)
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                logger.warning("%s failed on attempt %s/%s: %s", operation, attempt, self.max_retries, exc)
                if attempt == self.max_retries:
                    raise
                time.sleep(self.backoff_seconds * (2 ** (attempt - 1)))

        raise PolymarketAPIError(f"{operation} failed after {self.max_retries} attempts")

    def _markets_endpoint(self) -> str:
        return urljoin(self.base_url.rstrip('/') + '/', "markets")

    def _orders_endpoint(self) -> str:
        return urljoin(self.base_url.rstrip('/') + '/', "orders")

    def fetch_raw_markets(self, *, limit: int = 100, max_pages: int = 5,
                          filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"limit": limit}
        if filters:
            params.update(filters)

        url = self._markets_endpoint()
        markets: List[Dict[str, Any]] = []
        cursor: Optional[str] = None

        for page in range(max_pages):
            if cursor:
                params["cursor"] = cursor
            try:
                response = self._request_with_retry(
                    requests.get,
                    url,
                    operation="Fetch markets",
                    headers=self._headers(),
                    params=params,
                    timeout=10,
                )
            except requests.RequestException as exc:
                raise MarketFetchError(f"Unable to fetch markets: {exc}") from exc

            payload = response.json()
            page_markets = self._extract_markets(payload)
            markets.extend(page_markets)

            cursor = self._extract_next_cursor(payload)
            logger.info("Fetched %s markets (page %s)", len(page_markets), page + 1)

            if not cursor or len(page_markets) < limit:
                break

        return markets

    @staticmethod
    def _extract_markets(payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            if "markets" in payload and isinstance(payload["markets"], Iterable):
                return list(payload["markets"])
            if "data" in payload and isinstance(payload["data"], Iterable):
                return list(payload["data"])
        raise MarketFetchError("Unexpected markets payload format")

    @staticmethod
    def _extract_next_cursor(payload: Any) -> Optional[str]:
        if not isinstance(payload, dict):
            return None
        next_cursor = payload.get("next_cursor") or payload.get("nextCursor")
        if next_cursor:
            return str(next_cursor)
        pagination = payload.get("pagination")
        if isinstance(pagination, dict):
            cursor_value = pagination.get("next") or pagination.get("cursor")
            if cursor_value:
                return str(cursor_value)
        return None

    def parse_markets(self, raw: Iterable[Dict[str, Any]]) -> List[Market]:
        markets: List[Market] = []
        for m in raw:
            market_id = m.get("id")
            question = m.get("question")
            group_key = m.get("group", m.get("event_id"))
            rules = m.get("rules", "")
            volume = float(m.get("volume", 0) or 0)
            end_time = m.get("end_time")
            outcomes: List[Outcome] = []
            for o in m.get("outcomes", []):
                oid = o.get("id")
                name = o.get("name")
                best_bid = o.get("best_bid")
                best_ask = o.get("best_ask")
                liquidity = float(o.get("liquidity", 0) or 0)
                if best_bid is not None:
                    best_bid = float(best_bid)
                if best_ask is not None:
                    best_ask = float(best_ask)
                outcome = Outcome(oid, name, best_bid, best_ask, liquidity)
                outcomes.append(outcome)
            market = Market(market_id, question, group_key, outcomes, rules, volume, end_time)
            markets.append(market)
        return markets

    def get_markets(self, *, limit: int = 100, max_pages: int = 5, filters: Optional[Dict[str, Any]] = None) -> List[Market]:
        raw = self.fetch_raw_markets(limit=limit, max_pages=max_pages, filters=filters)
        return self.parse_markets(raw)

    def place_order(self, market_id: str, outcome_id: str, side: str, price: float, size: float) -> Dict[str, Any]:
        url = self._orders_endpoint()
        payload: Dict[str, Any] = {
            "market_id": market_id,
            "outcome_id": outcome_id,
            "side": side,
            "price": price,
            "size": size,
        }
        try:
            response = self._request_with_retry(
                requests.post,
                url,
                operation="Place order",
                json=payload,
                headers=self._headers(),
                timeout=10,
            )
        except requests.RequestException as exc:
            raise OrderPlacementError(f"Unable to place order: {exc}") from exc

        logger.info("Order placed for market %s outcome %s", market_id, outcome_id)
        return response.json()
