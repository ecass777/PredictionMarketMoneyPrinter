import logging
from typing import Any, Dict, List, Optional, Tuple

import requests

from .client import PolymarketClient
from .scanner import scan_markets
from .config import FEE_RATE, MAX_SLIPPAGE, MIN_EDGE, MIN_LIQUIDITY


class ExecutionBot:
    def __init__(self, client=None, capital_per_opportunity=1000.0):
        self.client = client or PolymarketClient()
        self.capital_per_opportunity = capital_per_opportunity

    def _place_order_with_retry(
        self, market_id: str, outcome_id: str, price: float, size: float
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        last_error = None
        for attempt in range(2):
            try:
                resp = self.client.place_order(
                    market_id=market_id,
                    outcome_id=outcome_id,
                    side="buy",
                    price=price,
                    size=size,
                )
                return True, resp, None
            except requests.HTTPError as http_err:
                last_error = f"HTTP error on attempt {attempt + 1}: {http_err}"
                logging.warning(last_error)
            except Exception as exc:  # noqa: BLE001 - broad to capture client errors
                last_error = f"Unexpected error on attempt {attempt + 1}: {exc}"
                logging.warning(last_error)
        return False, None, last_error

    def execute_sum_arb(self, market):
        results: List[Dict[str, Any]] = []
        valid_outcomes = []
        for o in market.outcomes:
            if o.best_ask is None or o.liquidity <= 0:
                results.append(
                    {
                        "outcome_id": getattr(o, "outcome_id", None),
                        "success": False,
                        "status": "skipped",
                        "reason": "missing ask or liquidity",
                    }
                )
                continue
            if o.best_ask <= 0 or o.best_ask >= 1:
                results.append(
                    {
                        "outcome_id": o.outcome_id,
                        "success": False,
                        "status": "skipped",
                        "reason": "stale quote outside bounds",
                    }
                )
                continue
            if o.best_bid is not None and o.best_bid > o.best_ask:
                results.append(
                    {
                        "outcome_id": o.outcome_id,
                        "success": False,
                        "status": "skipped",
                        "reason": "inverted market quotes",
                    }
                )
                continue
            if o.best_bid and o.best_bid > 0:
                spread = (o.best_ask - o.best_bid) / o.best_bid
                if spread > MAX_SLIPPAGE:
                    results.append(
                        {
                            "outcome_id": o.outcome_id,
                            "success": False,
                            "status": "skipped",
                            "reason": "slippage too high",
                        }
                    )
                    continue
            valid_outcomes.append(o)

        total_ask = sum(o.best_ask for o in valid_outcomes)
        if total_ask <= 0:
            return results

        adjusted_total_cost = sum(o.best_ask * (1 + FEE_RATE) for o in valid_outcomes)
        aggregate_edge = 1 - adjusted_total_cost
        if aggregate_edge < MIN_EDGE:
            results.append(
                {
                    "success": False,
                    "status": "skipped",
                    "reason": "aggregate edge below threshold",
                    "aggregate_edge": aggregate_edge,
                }
            )
            return results

        size_factor = self.capital_per_opportunity / total_ask
        for o in valid_outcomes:
            adjusted_price = o.best_ask * (1 + FEE_RATE)
            net_edge = 1 - adjusted_price
            if net_edge < MIN_EDGE:
                results.append(
                    {
                        "outcome_id": o.outcome_id,
                        "success": False,
                        "status": "skipped",
                        "reason": "per-outcome edge below threshold",
                        "net_edge": net_edge,
                    }
                )
                continue

            size = min(size_factor * o.best_ask, o.liquidity)
            if size <= 0:
                results.append(
                    {
                        "outcome_id": o.outcome_id,
                        "success": False,
                        "status": "skipped",
                        "reason": "non-positive size",
                    }
                )
                continue

            success, resp, err = self._place_order_with_retry(
                market_id=market.market_id,
                outcome_id=o.outcome_id,
                price=o.best_ask,
                size=size,
            )
            results.append(
                {
                    "outcome_id": o.outcome_id,
                    "price": o.best_ask,
                    "size": size,
                    "success": success,
                    "status": "filled" if success else "failed",
                    "response": resp,
                    "error": err,
                }
            )
        return results

    def run(self):
        raw_markets = self.client.get_markets()
        executed = []
        for m in raw_markets:
            if m.total_liquidity() < MIN_LIQUIDITY:
                continue
            total_ask = m.implied_prob_sum(use_ask=True)
            if total_ask >= 1.0:
                continue
            results = self.execute_sum_arb(m)
            if results:
                executed.append(
                    {
                        "market_id": m.market_id,
                        "question": m.question,
                        "orders": results,
                    }
                )
        return executed
