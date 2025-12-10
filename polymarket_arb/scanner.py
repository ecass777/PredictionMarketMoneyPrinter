import json
import os
from datetime import datetime
from .config import FEE_RATE, MAX_SLIPPAGE, MIN_EDGE, MIN_LIQUIDITY
from .client import PolymarketClient


def group_markets_by_key(markets):
    groups = {}
    for m in markets:
        key = m.group_key or m.market_id
        if key not in groups:
            groups[key] = []
        groups[key].append(m)
    return groups


def compute_simple_sum_arb(market, min_edge=MIN_EDGE):
    total_ask = market.implied_prob_sum(use_ask=True)
    if total_ask == 0:
        return None
    gross_edge = 1.0 - total_ask
    net_edge = gross_edge - FEE_RATE - MAX_SLIPPAGE
    if net_edge <= min_edge:
        return None
    if market.total_liquidity() < MIN_LIQUIDITY:
        return None
    return {
        "type": "sum_arb",
        "market_ids": [market.market_id],
        "group_key": market.group_key,
        "question": market.question,
        "gross_edge": gross_edge,
        "net_edge": net_edge,
        "total_ask": total_ask,
    }


def scan_markets(client=None, markets=None, min_edge=MIN_EDGE):
    if client is None:
        client = PolymarketClient()
    if markets is None:
        markets = client.get_markets()
    opportunities = []
    for m in markets:
        opp = compute_simple_sum_arb(m, min_edge=min_edge)
        if opp:
            opportunities.append(opp)
    return opportunities


def _build_slug_index(markets):
    return {m.slug: m for m in markets if getattr(m, "slug", None)}


def _price_for_outcome(market, outcome_name, use_ask=True):
    outcome_name_lower = str(outcome_name).lower()
    for outcome in market.outcomes:
        if str(outcome.name).lower() != outcome_name_lower:
            continue
        if use_ask and outcome.best_ask is not None:
            return outcome.best_ask
        if not use_ask and outcome.best_bid is not None:
            return outcome.best_bid
        return outcome.mid_price
    return None


def scan_strategy_baskets(markets, strategies, *, min_edge=MIN_EDGE, use_ask=True):
    slug_index = _build_slug_index(markets)
    opportunities = []

    for strategy in strategies:
        method = strategy.get("method")
        trade_name = strategy.get("trade_name", "").strip() or "unnamed_strategy"

        if method not in {"all_no", "balanced"}:
            continue

        pairs = []
        if method == "all_no":
            pairs = strategy.get("positions", [])
        elif method == "balanced":
            pairs = strategy.get("side_a_trades", []) + strategy.get("side_b_trades", [])

        legs = []
        prices = []
        missing = []

        for slug, outcome in pairs:
            market = slug_index.get(slug)
            if not market:
                missing.append({"slug": slug, "outcome": outcome, "reason": "market_not_found"})
                continue

            price = _price_for_outcome(market, outcome, use_ask=use_ask)
            if price is None:
                missing.append({"slug": slug, "outcome": outcome, "reason": "price_unavailable"})
                continue

            price = float(price)
            prices.append(price)
            legs.append({
                "slug": slug,
                "outcome": outcome,
                "price": price,
                "question": market.question,
            })

        if not prices:
            continue

        if method == "balanced":
            gross_edge = 1.0 - sum(prices)
        else:
            max_price = max(prices)
            total_winnings = sum(1 - p for p in prices) - (1 - max_price)
            gross_edge = total_winnings - max_price

        net_edge = gross_edge - FEE_RATE - MAX_SLIPPAGE

        if net_edge < min_edge:
            continue

        opportunities.append({
            "type": "strategy",
            "strategy": trade_name,
            "method": method,
            "gross_edge": gross_edge,
            "net_edge": net_edge,
            "legs": legs,
            "missing": missing,
        })

    return opportunities


def save_opportunities(opportunities, path="data/opportunities.json"):
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "opportunities": opportunities,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
