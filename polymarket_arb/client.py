import os
import requests
from .models import Market, Outcome
from .config import POLYMARKET_API_BASE, POLYMARKET_API_KEY


class PolymarketClient:
    def __init__(self, base_url=None, api_key=None):
        self.base_url = base_url or POLYMARKET_API_BASE
        self.api_key = api_key or POLYMARKET_API_KEY

    def _headers(self):
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def fetch_raw_markets(self):
        url = os.path.join(self.base_url, "markets")
        resp = requests.get(url, headers=self._headers(), timeout=10)
        resp.raise_for_status()
        return resp.json()

    def parse_markets(self, raw):
        markets = []
        for m in raw:
            market_id = m.get("id")
            question = m.get("question")
            group_key = m.get("group", m.get("event_id"))
            rules = m.get("rules", "")
            volume = float(m.get("volume", 0) or 0)
            end_time = m.get("end_time")
            outcomes = []
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

    def get_markets(self):
        raw = self.fetch_raw_markets()
        return self.parse_markets(raw)

    def place_order(self, market_id, outcome_id, side, price, size):
        url = os.path.join(self.base_url, "orders")
        payload = {
            "market_id": market_id,
            "outcome_id": outcome_id,
            "side": side,
            "price": price,
            "size": size,
        }
        resp = requests.post(url, json=payload, headers=self._headers(), timeout=10)
        resp.raise_for_status()
        return resp.json()
