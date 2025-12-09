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


def compute_simple_sum_arb(market):
    total_ask = market.implied_prob_sum(use_ask=True)
    if total_ask == 0:
        return None
    gross_edge = 1.0 - total_ask
    net_edge = gross_edge - FEE_RATE - MAX_SLIPPAGE
    if net_edge <= MIN_EDGE:
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


def scan_markets(client=None):
    if client is None:
        client = PolymarketClient()
    markets = client.get_markets()
    opportunities = []
    for m in markets:
        opp = compute_simple_sum_arb(m)
        if opp:
            opportunities.append(opp)
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
