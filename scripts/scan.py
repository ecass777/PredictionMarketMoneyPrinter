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
