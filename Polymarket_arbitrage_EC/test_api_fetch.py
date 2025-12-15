import argparse
import json
from typing import Optional, Dict, Any

from create_markets_data_csv import fetch_markets_data


def fetch_sample_object(
    host: str = "https://clob.polymarket.com",
    chain_id: int = 137,
    status_filter: str = "open",
    index: int = 0,
    include_fake: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Fetch markets from the Polymarket CLOB API and print a single sample object.
    Returns the selected market dictionary or None if nothing was returned.
    """
    markets = fetch_markets_data(
        host=host,
        chain_id=chain_id,
        status_filter=status_filter,
        include_fake=include_fake,
    )
    if not markets:
        print("No markets returned from the API.")
        return None

    safe_index = min(max(index, 0), len(markets) - 1)
    sample = markets[safe_index]
    print(f"Fetched {len(markets)} markets; showing item {safe_index}:")
    print(json.dumps(sample, indent=2, sort_keys=True))
    return sample


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch and print a sample market object from the Polymarket CLOB API."
    )
    parser.add_argument(
        "--host",
        default="https://clob.polymarket.com",
        help="CLOB host to query.",
    )
    parser.add_argument(
        "--chain-id",
        type=int,
        default=137,
        help="Chain ID to use for the client (137 = Polygon mainnet).",
    )
    parser.add_argument(
        "--status",
        default="open",
        choices=["open", "closed", "all"],
        help="Filter markets by status before sampling.",
    )
    parser.add_argument(
        "--index",
        type=int,
        default=0,
        help="Zero-based index of the market to show from the returned list.",
    )
    parser.add_argument(
        "--include-fake",
        action="store_true",
        help="Also inject the local fake test market into the results.",
    )
    args = parser.parse_args()

    fetch_sample_object(
        host=args.host,
        chain_id=args.chain_id,
        status_filter=args.status,
        index=args.index,
        include_fake=args.include_fake,
    )


if __name__ == "__main__":
    main()
