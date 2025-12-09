import json
import os
import pandas as pd
from .client import PolymarketClient
from .scanner import scan_markets
from .config import FEE_RATE, MAX_SLIPPAGE


def load_snapshot(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def compute_snapshot_pnl(markets_raw):
    client = PolymarketClient()
    markets = client.parse_markets(markets_raw)
    total_edge = 0.0
    total_count = 0
    for m in markets:
        total_ask = m.implied_prob_sum(use_ask=True)
        if total_ask <= 0:
            continue
        gross_edge = 1.0 - total_ask
        net_edge = gross_edge - FEE_RATE - MAX_SLIPPAGE
        if net_edge > 0:
            total_edge += net_edge
            total_count += 1
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
