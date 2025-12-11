import csv
import json
import os
from typing import List, Tuple

from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OpenOrderParams


def _is_market_open(market: dict) -> bool:
    """Best-effort check for an open/active market based on common fields."""
    # Explicit closed flag wins
    if "closed" in market:
        if bool(market.get("closed")):
            return False

    # If accepting orders is explicitly false, consider it closed unless overridden by another signal
    if "accepting_orders" in market:
        if bool(market.get("accepting_orders")):
            return True
        if bool(market.get("closed")):
            return False

    # Active with not closed is generally open
    if market.get("active") is False:
        return False

    status = str(market.get("status", "")).lower()
    if status:
        if status in {"closed", "resolved", "ended", "paused"}:
            return False
        if status in {"open", "active", "trading", "live"}:
            return True

    # Fallback: if we don't know, default to open so data isn't silently dropped
    return True  # default to open if we cannot tell


def fetch_markets_with_pagination(client: ClobClient, status_filter: str = "all") -> List[dict]:
    """Fetch all markets using pagination and return the full list."""
    markets_list: List[dict] = []
    next_cursor = None

    while True:
        try:
            if next_cursor is None:
                response = client.get_markets()
            else:
                response = client.get_markets(next_cursor=next_cursor)
        except Exception as e:
            print(f"Exception occurred: {e}")
            print(f"Exception details: {e.__class__.__name__}")
            print(f"Error message: {e.args}")
            break

        if "data" not in response:
            print("No data found in response.")
            break

        markets_list.extend(response["data"])
        next_cursor = response.get("next_cursor")

        if not next_cursor:
            break

    status_filter = (status_filter or "all").lower()
    if status_filter == "all":
        return markets_list
    filtered: List[dict] = []
    for m in markets_list:
        is_open = _is_market_open(m)
        if status_filter == "open" and is_open:
            filtered.append(m)
        elif status_filter == "closed" and not is_open:
            filtered.append(m)
    return filtered


def _ensure_outcomes(markets: List[dict]) -> List[dict]:
    """Ensure each market has an 'outcomes' array built from tokens when missing."""
    normalized = []
    for m in markets:
        if m.get("outcomes"):
            normalized.append(m)
            continue
        tokens = m.get("tokens", [])
        outcomes = []
        for token in tokens if isinstance(tokens, list) else []:
            best_bid = token.get("best_bid")
            best_ask = token.get("best_ask")
            price = token.get("price")
            if best_bid is None and best_ask is None and price is not None:
                best_bid = best_ask = price
            outcomes.append(
                {
                    "id": token.get("token_id"),
                    "name": token.get("outcome"),
                    "best_bid": best_bid,
                    "best_ask": best_ask,
                    "liquidity": token.get("liquidity", 0),
                }
            )
        m = dict(m)
        m["outcomes"] = outcomes
        normalized.append(m)
    return normalized


def fetch_markets_data(
    host: str = "https://clob.polymarket.com",
    chain_id: int = 137,
    status_filter: str = "open",
    include_fake: bool = True,
) -> List[dict]:
    """Fetch markets (optionally filtered) and optionally inject the fake test market."""
    load_dotenv("keys.env")
    client = ClobClient(host, chain_id=chain_id)
    markets_list = fetch_markets_with_pagination(client, status_filter=status_filter)

    if include_fake:
        fake_market = {
            "enable_order_book": True,
            "active": True,
            "closed": False,
            "archived": False,
            "accepting_orders": True,
            "accepting_order_timestamp": None,
            "minimum_order_size": 1,
            "minimum_tick_size": 0.001,
            "condition_id": "fake-condition-id",
            "question_id": "fake-question-id",
            "question": "FAKE TEST MARKET - should be arb positive 2nd TEST",
            "description": "Synthetic market injected for testing arbitrage detection",
            "market_slug": "fake-arb-market",
            "end_date_iso": None,
            "game_start_time": None,
            "seconds_delay": 0,
            "fpmm": "",
            "maker_base_fee": 0,
            "taker_base_fee": 0,
            "notifications_enabled": False,
            "neg_risk": False,
            "neg_risk_market_id": "",
            "neg_risk_request_id": "",
            "icon": "",
            "image": "",
            "rewards": {"rates": None, "min_size": 0, "max_spread": 0},
            "is_50_50_outcome": False,
            "tokens": [
                {
                    "token_id": "fake-token-yes",
                    "outcome": "Yes",
                    "price": 0.30,
                    "winner": False,
                    "best_bid": 0.28,
                    "best_ask": 0.30,
                    "liquidity": 1000,
                },
                {
                    "token_id": "fake-token-no",
                    "outcome": "No",
                    "price": 0.40,
                    "winner": False,
                    "best_bid": 0.28,
                    "best_ask": 0.30,
                    "liquidity": 1000,
                },
            ],
            "tags": ["Testing"],
            "status": "open",
            "volume": 10000,
            "rules": "Test market for arb detection",
        }
        markets_list.append(fake_market)

    return _ensure_outcomes(markets_list)


def write_markets_csv(markets_list: List[dict], csv_file: str = "./data/markets_data.csv") -> Tuple[int, str]:
    """Write markets to CSV and return (row_count, path)."""
    csv_columns = set()
    for market in markets_list:
        csv_columns.update(market.keys())
        if "tokens" in market:
            csv_columns.update({f"token_{key}" for token in market["tokens"] for key in token.keys()})

    csv_columns = sorted(csv_columns)

    try:
        os.makedirs(os.path.dirname(csv_file), exist_ok=True)
        with open(csv_file, "w", newline="", encoding="utf-8", errors="replace") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=csv_columns)
            writer.writeheader()
            for market in markets_list:
                row = {}
                for key in csv_columns:
                    if key.startswith("token_"):
                        token_key = key[len("token_") :]
                        row[key] = ", ".join([str(token.get(token_key, "N/A")) for token in market.get("tokens", [])])
                    else:
                        row[key] = market.get(key, "N/A")
                writer.writerow(row)
        print(f"Data has been written to {csv_file} successfully.")
        return len(markets_list), csv_file
    except IOError as e:
        print(f"Error writing to CSV: {e}")
        return 0, csv_file


def generate_markets_csv(
    csv_file: str = "./data/markets_data.csv",
    host: str = "https://clob.polymarket.com",
    chain_id: int = 137,
    status_filter: str = "open",
) -> Tuple[int, str]:
    """
    Fetch all markets from the Polymarket CLOB API and write them to CSV.
    Returns (row_count, path).
    Defaults to only open markets.
    """
    markets_list = fetch_markets_data(host=host, chain_id=chain_id, status_filter=status_filter, include_fake=True)
    if not markets_list:
        print("No markets fetched; skipping CSV write.")
        return 0, csv_file
    # print(markets_list[:10])
    # fake_market = {
    #     "enable_order_book": True,
    #     "active": True,
    #     "closed": False,
    #     "archived": False,
    #     "accepting_orders": True,
    #     "accepting_order_timestamp": None,
    #     "minimum_order_size": 1,
    #     "minimum_tick_size": 0.001,
    #     "condition_id": "fake-condition-id",
    #     "question_id": "fake-question-id",
    #     "question": "FAKE TEST MARKET - should be arb positive 2nd TEST",
    #     "description": "Synthetic market injected for testing arbitrage detection",
    #     "market_slug": "fake-arb-market",
    #     "end_date_iso": None,
    #     "game_start_time": None,
    #     "seconds_delay": 0,
    #     "fpmm": "",
    #     "maker_base_fee": 0,
    #     "taker_base_fee": 0,
    #     "notifications_enabled": False,
    #     "neg_risk": False,
    #     "neg_risk_market_id": "",
    #     "neg_risk_request_id": "",
    #     "icon": "",
    #     "image": "",
    #     "rewards": {"rates": None, "min_size": 0, "max_spread": 0},
    #     "is_50_50_outcome": False,
    #     "tokens": [
    #         {
    #             "token_id": "fake-token-yes",
    #             "outcome": "Yes",
    #             "price": 0.30,
    #             "winner": False,
    #             "best_bid": 0.28,
    #             "best_ask": 0.30,
    #             "liquidity": 1000,
    #         },
    #         {
    #             "token_id": "fake-token-no",
    #             "outcome": "No",
    #             "price": 0.40,
    #             "winner": False,
    #             "best_bid": 0.28,
    #             "best_ask": 0.30,
    #             "liquidity": 1000,
    #         },
    #     ],
    #     "tags": ["Testing"],
    #     "status": "open",
    #     "volume": 10000,
    #     "rules": "Test market for arb detection",
    # }
    # markets_list.append(fake_market)
    # print("DEBUG: injected fake market 'fake-arb-market' into CSV payload for testing")

    return write_markets_csv(markets_list, csv_file)


if __name__ == "__main__":
    generate_markets_csv()
