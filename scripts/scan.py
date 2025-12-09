import os
import sys

# Add project root so polymarket_arb package can be imported when running the script directly
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from polymarket_arb.scanner import scan_markets, save_opportunities
from polymarket_arb.client import PolymarketClient


def main():
    client = PolymarketClient()
    opps = scan_markets(client)
    if not opps:
        print("No opportunities found")
    else:
        for o in opps:
            print(f"[{o['type']}] {o['question']} | net_edge={o['net_edge']:.4f}")
    save_opportunities(opps)


if __name__ == "__main__":
    main()
