import ast
import json
import logging
import os
from pathlib import Path
from typing import Dict, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

try:
    from py_clob_client.client import ClobClient
except Exception:  # pragma: no cover - dependency might be optional in some environments
    ClobClient = None


DEFAULT_HOST = "https://clob.polymarket.com"
DEFAULT_CHAIN_ID = 137


def _ensure_parent(path: Path) -> None:
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)


def refresh_markets_csv(
    csv_path: str = "data/markets_data.csv",
    *,
    host: str = DEFAULT_HOST,
    chain_id: int = DEFAULT_CHAIN_ID,
) -> int:
    """
    Fetch all markets from the Polymarket CLOB API and write them to a CSV file.

    Returns the number of markets written. Raises ImportError if py_clob_client
    is unavailable.
    """
    if ClobClient is None:
        raise ImportError("py_clob_client is required to refresh markets data")

    api_key = os.getenv("API_KEY") or os.getenv("POLYMARKET_API_KEY")
    client = ClobClient(host, key=api_key, chain_id=chain_id) if api_key else ClobClient(host, chain_id=chain_id)

    try:
        response = client.get_markets()
    except Exception as exc:
        logger.error("Failed to fetch markets: %s", exc)
        return 0

    markets = []
    if isinstance(response, dict):
        markets = response.get("data") or response.get("markets") or []
    elif isinstance(response, list):
        markets = response
    else:
        logger.warning("Unexpected response type when fetching markets: %s", type(response))
        return 0

    if not markets:
        logger.warning("No markets fetched; skipping CSV write to %s", csv_path)
        return 0

    output_path = Path(csv_path)
    _ensure_parent(output_path)

    df = pd.DataFrame(markets)
    df.to_csv(output_path, index=False)
    logger.info("Wrote %s markets to %s", len(df), output_path)
    print(f"Number of markets {len(df)}")
    return len(df)


def _parse_tokens(raw_tokens):
    if isinstance(raw_tokens, list):
        return raw_tokens
    if pd.isna(raw_tokens):
        return []
    if isinstance(raw_tokens, str):
        try:
            return ast.literal_eval(raw_tokens)
        except (ValueError, SyntaxError):
            logger.debug("Unable to parse tokens cell: %s", raw_tokens)
            return []
    return []


def build_market_lookup_from_csv(
    csv_path: str = "data/markets_data.csv",
    json_path: str = "data/market_lookup.json",
) -> Dict[str, Dict]:
    """
    Read markets_data.csv, parse tokens, and write a JSON lookup keyed by condition_id.
    """
    csv_file = Path(csv_path)
    if not csv_file.exists():
        logger.warning("CSV path %s does not exist; skipping lookup build", csv_file)
        return {}

    df = pd.read_csv(csv_file, low_memory=False)
    required_cols = ["condition_id", "description", "market_slug", "tokens"]
    for col in required_cols:
        if col not in df.columns:
            logger.warning("Missing column %s in %s; unable to build lookup", col, csv_file)
            return {}

    lookup_df = df[["condition_id", "description", "market_slug", "tokens", *([c for c in df.columns if c == "rules"])]]
    lookup_df = lookup_df.drop_duplicates(subset="condition_id")

    lookup: Dict[str, Dict] = {}
    for _, row in lookup_df.iterrows():
        tokens_raw = _parse_tokens(row["tokens"])
        parsed_tokens = []
        for token in tokens_raw:
            if not isinstance(token, dict):
                continue
            token_id = token.get("token_id") or token.get("id")
            outcome = token.get("outcome") or token.get("name")
            parsed_tokens.append({"token_id": token_id, "outcome": outcome})

        condition_id = str(row["condition_id"])
        lookup[condition_id] = {
            "description": row.get("description", ""),
            "market_slug": row.get("market_slug", ""),
            "tokens": parsed_tokens,
        }

        if "rules" in row:
            lookup[condition_id]["rules"] = row.get("rules", "")

    output_path = Path(json_path)
    _ensure_parent(output_path)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(lookup, f, indent=2)
    logger.info("Wrote market lookup JSON to %s (%s markets)", output_path, len(lookup))
    return lookup


def load_market_lookup(json_path: str = "data/market_lookup.json") -> Tuple[Dict[str, Dict], Dict[str, Dict[str, str]]]:
    """
    Load the market lookup JSON and return:
      - condition_lookup: dict[condition_id] -> {..., 'market_slug', 'tokens': [...]}
      - slug_to_token_map: dict[slug] -> dict[outcome_label] -> token_id
    """
    json_file = Path(json_path)
    if not json_file.exists():
        logger.warning("Lookup file %s not found", json_file)
        return {}, {}

    with open(json_file, "r", encoding="utf-8") as f:
        lookup: Dict[str, Dict] = json.load(f)

    slug_to_token_map: Dict[str, Dict[str, str]] = {}
    for entry in lookup.values():
        slug = entry.get("market_slug") or entry.get("slug")
        tokens = entry.get("tokens", [])
        if not slug or not isinstance(tokens, list):
            continue
        token_map: Dict[str, str] = {}
        for token in tokens:
            if not isinstance(token, dict):
                continue
            outcome = token.get("outcome")
            token_id = token.get("token_id")
            if outcome is None or token_id is None:
                continue
            token_map[str(outcome)] = str(token_id)
        if token_map:
            slug_to_token_map[str(slug)] = token_map

    return lookup, slug_to_token_map
