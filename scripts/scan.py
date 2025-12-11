import argparse
import ast
import os
import sys
from typing import List

# Add project root so polymarket_arb package can be imported when running the script directly
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from polymarket_arb.config import MIN_EDGE
from polymarket_arb.scanner import (
    compute_simple_sum_arb,
    save_opportunities,
    scan_markets,
    scan_strategy_baskets,
)
from polymarket_arb.client import PolymarketClient
from polymarket_arb.models import Market, Outcome
from Polymarket_arbitrage_EC.create_markets_data_csv import fetch_markets_data, generate_markets_csv


def _load_markets_from_csv(csv_path: str = "data/markets_data.csv") -> List[Market]:
    """Load markets from the generated CSV (used to bring in the injected fake market)."""
    try:
        import pandas as pd
    except ImportError:
        print("DEBUG: pandas not available; cannot load markets from CSV")
        return []

    if not os.path.exists(csv_path):
        print(f"DEBUG: CSV {csv_path} not found; skipping CSV market load")
        return []

    df = pd.read_csv(csv_path, low_memory=False)
    required_cols = {"condition_id", "question", "market_slug", "tokens"}
    if not required_cols.issubset(set(df.columns)):
        print(f"DEBUG: CSV missing required columns {required_cols}; found {df.columns}")
        return []

    markets: List[Market] = []
    for _, row in df.iterrows():
        try:
            tokens = ast.literal_eval(row["tokens"])
        except Exception:
            tokens = []

        outcomes: List[Outcome] = []
        for token in tokens if isinstance(tokens, list) else []:
            outcome_name = token.get("outcome")
            if not outcome_name:
                continue
            best_bid = token.get("best_bid")
            best_ask = token.get("best_ask")
            price = token.get("price")
            try:
                best_bid = float(best_bid) if best_bid is not None else None
            except (TypeError, ValueError):
                best_bid = None
            try:
                best_ask = float(best_ask) if best_ask is not None else None
            except (TypeError, ValueError):
                best_ask = None
            try:
                price = float(price) if price is not None else None
            except (TypeError, ValueError):
                price = None
            # Fallback: if no bid/ask, use price as mid
            if best_bid is None and best_ask is None and price is not None:
                best_bid = best_ask = price
            liquidity = token.get("liquidity", 0)
            try:
                liquidity = float(liquidity) if liquidity is not None else 0.0
            except (TypeError, ValueError):
                liquidity = 0.0
            outcomes.append(Outcome(token.get("token_id"), outcome_name, best_bid, best_ask, liquidity))

        market = Market(
            market_id=row.get("condition_id") or row.get("market_id") or row.get("question_id"),
            question=row.get("question", ""),
            group_key=row.get("group") or row.get("event_id") or row.get("condition_id"),
            outcomes=outcomes,
            rules=row.get("rules", ""),
            volume=float(row.get("volume", 0) or 0),
            end_time=row.get("end_date_iso"),
            slug=row.get("market_slug") or row.get("slug"),
        )
        markets.append(market)

    print(f"DEBUG: loaded {len(markets)} markets from CSV ({csv_path})")
    return markets


def main():
    parser = argparse.ArgumentParser(description="Scan Polymarket markets for arbitrage.")
    parser.add_argument("--min-edge", type=float, default=MIN_EDGE, help="Minimum net edge to report.")
    parser.add_argument(
        "--include-strategies",
        action="store_true",
        help="Evaluate multi-leg strategies defined in Polymarket_arbitrage_EC/strategies.py",
    )
    parser.add_argument(
        "--auto-discover",
        action="store_true",
        help="Automatically discover strategies from markets_data and market_lookup.",
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
        "--skip-refresh",
        action="store_true",
        help="Skip regenerating markets CSV (use existing data/markets_data.csv).",
    )
    args = parser.parse_args()

    client = PolymarketClient()

    raw_markets = fetch_markets_data(status_filter="open", include_fake=True)
    markets = client.parse_markets(raw_markets)
    print(f"DEBUG: fetched {len(markets)} markets from API helper (open filter + fake included)")

    if not args.skip_refresh:
        generate_markets_csv()  # still available for lookup generation if needed

    strategies = []
    if args.auto_discover:
        from polymarket_arb.market_cache import build_market_lookup_from_csv, load_market_lookup
        from polymarket_arb.trade_discovery import discover_trades

        # Build lookup based on freshly generated CSV
        build_market_lookup_from_csv()
        load_market_lookup()
        strategies = discover_trades()

    print(
        f"DEBUG: running scan with min_edge={args.min_edge}, "
        f"include_strategies={args.include_strategies}, "
        f"auto_discover={args.auto_discover}, "
        f"price_source={args.price_source}, "
        f"user_id={args.user_id}"
    )
    print(f"DEBUG: total markets to scan after merge: {len(markets)}")

    simple_opps = scan_markets(client=client, markets=markets, min_edge=args.min_edge)
    all_opps = list(simple_opps)
    print(f"DEBUG: found {len(simple_opps)} single-market opportunities")

    if simple_opps:
        print("Single-market sum arbitrage:")
        for o in simple_opps:
            slug = o.get("slug") or ""
            market_id = o.get("market_ids", [None])[0]
            print(
                f"[{o['type']}] slug={slug} id={market_id} question={o['question']} "
                f"| net_edge={o['net_edge']:.4f} gross_edge={o['gross_edge']:.4f} "
                f"total_ask={o['total_ask']:.4f} liquidity={o.get('total_liquidity', 'n/a')}"
            )
    else:
        print("No single-market opportunities found")

    if args.include_strategies:
        try:
            from Polymarket_arbitrage_EC.strategies import trades as strategies  # type: ignore
        except Exception as exc:
            print(f"Skipping strategy scan (unable to import strategies: {exc})")
            strategy_opps = []
        else:
            strategy_opps = scan_strategy_baskets(
                markets,
                strategies,
                min_edge=args.min_edge,
                price_source=args.price_source,
                user_id=args.user_id,
            )
            if strategy_opps:
                print("\nStrategy basket opportunities:")
                for o in strategy_opps:
                    print(f"[{o['strategy']}] method={o['method']} | net_edge={o['net_edge']:.4f}")
            else:
                print("\nNo strategy basket opportunities found")
            print(f"DEBUG: found {len(strategy_opps)} strategy opportunities (include_strategies)")
        all_opps.extend(strategy_opps)
    elif args.auto_discover:
        if strategies:
            strategy_opps = scan_strategy_baskets(
                markets,
                strategies,
                min_edge=args.min_edge,
                price_source=args.price_source,
                user_id=args.user_id,
            )
            if strategy_opps:
                print("\nStrategy basket opportunities (auto-discovered):")
                for o in strategy_opps:
                    print(f"[{o['strategy']}] method={o['method']} | net_edge={o['net_edge']:.4f}")
            else:
                print("\nNo auto-discovered strategy opportunities found")
            print(f"DEBUG: found {len(strategy_opps)} strategy opportunities (auto-discover)")
            all_opps.extend(strategy_opps)
        else:
            print("\nNo strategies discovered; skipping strategy scan")

    if not all_opps:
        print("No opportunities found")

    save_opportunities(all_opps)


if __name__ == "__main__":
    main()
