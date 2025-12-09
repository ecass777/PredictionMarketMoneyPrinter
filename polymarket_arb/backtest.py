import json
import os
import pandas as pd
from .client import PolymarketClient
from .scanner import compute_simple_sum_arb


def load_snapshot(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def compute_snapshot_pnl(markets_raw):
    client = PolymarketClient()
    markets = client.parse_markets(markets_raw)
    opportunities = []
    for market in markets:
        opp = compute_simple_sum_arb(market)
        if opp:
            opportunities.append(opp)
    total_edge = sum(opp["net_edge"] for opp in opportunities)
    total_count = len(opportunities)
    return total_edge, total_count


def run_backtest(data_dir="data/historical"):
    rows = []
    if not os.path.exists(data_dir):
        return pd.DataFrame(rows)
    for name in sorted(os.listdir(data_dir)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(data_dir, name)
        raw = load_snapshot(path)
        total_edge, count = compute_snapshot_pnl(raw)
        rows.append(
            {
                "snapshot": name,
                "total_net_edge": total_edge,
                "opportunity_count": count,
            }
        )
    if not rows:
        return pd.DataFrame([])
    df = pd.DataFrame(rows)
    return df
