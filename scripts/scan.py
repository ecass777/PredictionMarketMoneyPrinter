import argparse
import os
import sys

# Add project root so polymarket_arb package can be imported when running the script directly
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from polymarket_arb.config import MIN_EDGE
from polymarket_arb.scanner import save_opportunities, scan_markets, scan_strategy_baskets
from polymarket_arb.client import PolymarketClient


def main():
    parser = argparse.ArgumentParser(description="Scan Polymarket markets for arbitrage.")
    parser.add_argument("--min-edge", type=float, default=MIN_EDGE, help="Minimum net edge to report.")
    parser.add_argument(
        "--include-strategies",
        action="store_true",
        help="Evaluate multi-leg strategies defined in Polymarket_arbitrage_EC/strategies.py",
    )
    args = parser.parse_args()

    client = PolymarketClient()
    markets = client.get_markets()

    simple_opps = scan_markets(client=client, markets=markets, min_edge=args.min_edge)
    all_opps = list(simple_opps)

    if simple_opps:
        print("Single-market sum arbitrage:")
        for o in simple_opps:
            print(f"[{o['type']}] {o['question']} | net_edge={o['net_edge']:.4f}")
    else:
        print("No single-market opportunities found")

    if args.include_strategies:
        try:
            from Polymarket_arbitrage_EC.strategies import trades as strategies  # type: ignore
        except Exception as exc:
            print(f"Skipping strategy scan (unable to import strategies: {exc})")
            strategy_opps = []
        else:
            strategy_opps = scan_strategy_baskets(markets, strategies, min_edge=args.min_edge)
            if strategy_opps:
                print("\nStrategy basket opportunities:")
                for o in strategy_opps:
                    print(f"[{o['strategy']}] method={o['method']} | net_edge={o['net_edge']:.4f}")
            else:
                print("\nNo strategy basket opportunities found")
            all_opps.extend(strategy_opps)

    if not all_opps:
        print("No opportunities found")

    save_opportunities(all_opps)


if __name__ == "__main__":
    main()
