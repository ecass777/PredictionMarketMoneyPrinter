from .client import PolymarketClient
from .scanner import scan_markets
from .config import MIN_LIQUIDITY


class ExecutionBot:
    def __init__(self, client=None, capital_per_opportunity=1000.0):
        self.client = client or PolymarketClient()
        self.capital_per_opportunity = capital_per_opportunity

    def execute_sum_arb(self, market):
        total_ask = market.implied_prob_sum(use_ask=True)
        if total_ask <= 0:
            return []
        size_factor = self.capital_per_opportunity / total_ask
        results = []
        for o in market.outcomes:
            if o.best_ask is None or o.liquidity <= 0:
                continue
            size = min(size_factor * o.best_ask, o.liquidity)
            if size <= 0:
                continue
            resp = self.client.place_order(
                market_id=market.market_id,
                outcome_id=o.outcome_id,
                side="buy",
                price=o.best_ask,
                size=size,
            )
            results.append(resp)
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
