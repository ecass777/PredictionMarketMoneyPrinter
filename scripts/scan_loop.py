import argparse
import csv
import os
import sys
import time
from datetime import datetime
from typing import List, Dict, Any

# Add project root so polymarket_arb package can be imported when running the script directly
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from polymarket_arb.client import PolymarketClient
from polymarket_arb.config import MIN_EDGE
from polymarket_arb.scanner import scan_markets, scan_strategy_baskets
from Polymarket_arbitrage_EC.create_markets_data_csv import fetch_markets_data


LOG_PATH = os.path.join("data", "opportunities_log.csv")


def ensure_log_header(path: str) -> None:
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "timestamp",
                    "type",
                    "strategy",
                    "method",
                    "price_source",
                    "slug",
                    "question",
                    "net_edge",
                    "gross_edge",
                    "total_ask",
                    "total_liquidity",
                ],
            )
            writer.writeheader()


def append_opportunities(path: str, opportunities: List[Dict[str, Any]], price_source: str) -> None:
    if not opportunities:
        return
    ensure_log_header(path)
    now = datetime.utcnow().isoformat() + "Z"
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "timestamp",
                "type",
                "strategy",
                "method",
                "price_source",
                "slug",
                "question",
                "net_edge",
                "gross_edge",
                "total_ask",
                "total_liquidity",
            ],
        )
        for opp in opportunities:
            writer.writerow(
                {
                    "timestamp": now,
                    "type": opp.get("type"),
                    "strategy": opp.get("strategy"),
                    "method": opp.get("method"),
                    "price_source": opp.get("price_source", price_source),
                    "slug": opp.get("slug"),
                    "question": opp.get("question"),
                    "net_edge": opp.get("net_edge"),
                    "gross_edge": opp.get("gross_edge"),
                    "total_ask": opp.get("total_ask"),
                    "total_liquidity": opp.get("total_liquidity"),
                }
            )


def scan_once(client: PolymarketClient, args) -> List[Dict[str, Any]]:
    try:
        raw_markets = fetch_markets_data(status_filter="open", include_fake=False)
        markets = client.parse_markets(raw_markets)
    except Exception as exc:
        print(f"ERROR: failed to fetch/parse markets: {exc}")
        return []

    all_opps: List[Dict[str, Any]] = []

    simple_opps = scan_markets(client=client, markets=markets, min_edge=args.min_edge)
    if simple_opps:
        print(f"[{datetime.utcnow().isoformat()}Z] Simple opportunities: {len(simple_opps)}")
        for o in simple_opps:
            slug = o.get("slug") or ""
            print(
                f"  [sum_arb] slug={slug} net_edge={o['net_edge']:.4f} "
                f"gross_edge={o['gross_edge']:.4f} total_ask={o['total_ask']:.4f} "
                f"liquidity={o.get('total_liquidity')}"
            )
    all_opps.extend(simple_opps)

    if args.include_strategies:
        try:
            from Polymarket_arbitrage_EC.strategies import trades as strategies  # type: ignore
        except Exception as exc:
            print(f"WARNING: unable to import strategies: {exc}")
        else:
            strat_opps = scan_strategy_baskets(
                markets,
                strategies,
                min_edge=args.min_edge,
                price_source=args.price_source,
                user_id=args.user_id,
            )
            if strat_opps:
                print(f"[{datetime.utcnow().isoformat()}Z] Strategy opportunities: {len(strat_opps)}")
                for o in strat_opps:
                    print(
                        f"  [strategy] {o['strategy']} method={o['method']} "
                        f"net_edge={o['net_edge']:.4f} price_source={o.get('price_source')}"
                    )
            all_opps.extend(strat_opps)

    return all_opps


def main() -> None:
    parser = argparse.ArgumentParser(description="Continuously scan markets for arbitrage and log to CSV.")
    parser.add_argument("--min-edge", type=float, default=MIN_EDGE, help="Minimum net edge to report.")
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Seconds between scans.",
    )
    parser.add_argument(
        "--include-strategies",
        action="store_true",
        help="Evaluate multi-leg strategies defined in Polymarket_arbitrage_EC/strategies.py",
    )
    parser.add_argument(
        "--price-source",
        choices=["ask", "mid", "bid", "live", "actual"],
        default="ask",
        help="Price source to use when evaluating multi-leg strategies.",
    )
    parser.add_argument(
        "--user-id",
        default=None,
        help="User ID for 'actual' pricing (expects enriched trades parquet).",
    )
    parser.add_argument(
        "--log-path",
        default=LOG_PATH,
        help="Path to append opportunities CSV.",
    )
    args = parser.parse_args()

    client = PolymarketClient()
    print(
        f"Starting continuous scan: min_edge={args.min_edge} interval={args.interval}s "
        f"include_strategies={args.include_strategies} price_source={args.price_source}"
    )
    ensure_log_header(args.log_path)

    try:
        while True:
            opportunities = scan_once(client, args)
            append_opportunities(args.log_path, opportunities, args.price_source)
            time.sleep(max(1, args.interval))
    except KeyboardInterrupt:
        print("Stopping continuous scan.")


if __name__ == "__main__":
    main()
