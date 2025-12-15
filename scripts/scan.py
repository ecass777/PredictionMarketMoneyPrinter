import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, Generator, List, Optional, Tuple

import requests

# Add project root so polymarket_arb package can be imported when running the script directly
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from polymarket_arb.client import PolymarketClient
from polymarket_arb.config import MIN_EDGE
from polymarket_arb.scanner import compute_simple_sum_arb, save_opportunities

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency
    load_dotenv = None

try:
    from py_clob_client.client import ClobClient
except Exception as exc:  # pragma: no cover - surface the import error at runtime
    ClobClient = None  # type: ignore


CSV_HEADERS = [
    "timestamp",
    "slug",
    "market_id",
    "question",
    "net_edge",
    "gross_edge",
    "total_ask",
    "total_liquidity",
    "decision_ms",
]

DEFAULT_HOST = "https://clob.polymarket.com"
DEFAULT_GAMMA_HOST = "https://gamma-api.polymarket.com"
DEFAULT_CHAIN_ID = 137
DEFAULT_PAGE_LIMIT = 100
DECISION_BUDGET_MS = 1000


def market_looks_open(market: Dict[str, object]) -> bool:
    if bool(market.get("closed")):
        return False
    if market.get("accepting_orders") is False or market.get("acceptingOrders") is False:
        return False
    if market.get("active") is False:
        return False
    status = str(market.get("status", "")).lower()
    if status in {"closed", "resolved", "ended", "paused"}:
        return False
    if status in {"open", "active", "trading", "live"}:
        return True
    return True


def normalize_market(raw_market: Dict[str, object]) -> Dict[str, object]:
    market = dict(raw_market)
    # Promote event-level fields when present
    if not market.get("question") and market.get("title"):
        market["question"] = market.get("title")
    if not market.get("group") and market.get("event_id"):
        market["group"] = market.get("event_id")
    if not market.get("group_key") and market.get("group"):
        market["group_key"] = market.get("group")

    if not market.get("id") and market.get("condition_id"):
        market["id"] = market.get("condition_id")
    if not market.get("market_slug") and market.get("slug"):
        market["market_slug"] = market.get("slug")
    if not market.get("slug") and market.get("market_slug"):
        market["slug"] = market.get("market_slug")

    def _coerce_list(value):
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                return []
        return []

    outcomes_value = market.get("outcomes")
    outcome_prices = _coerce_list(market.get("outcomePrices") or market.get("outcome_prices"))
    clob_token_ids = _coerce_list(market.get("clobTokenIds") or market.get("token_ids"))
    liquidity_val = market.get("liquidityNum") or market.get("liquidity") or 0

    if not outcomes_value:
        outcomes = []
        tokens = market.get("tokens") or []
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
        market["outcomes"] = outcomes
    else:
        # Normalize string/list outcomes into outcome dicts if they are not already dicts
        if isinstance(outcomes_value, list) and all(isinstance(o, dict) for o in outcomes_value):
            pass  # already in desired form
        else:
            outcomes_list = _coerce_list(outcomes_value)
            normalized_outcomes = []
            for idx, name in enumerate(outcomes_list):
                price_val = None
                if idx < len(outcome_prices):
                    try:
                        price_val = float(outcome_prices[idx])
                    except (TypeError, ValueError):
                        price_val = None
                try:
                    liquidity_float = float(liquidity_val) if liquidity_val is not None else 0.0
                except (TypeError, ValueError):
                    liquidity_float = 0.0
                normalized_outcomes.append(
                    {
                        "id": clob_token_ids[idx] if idx < len(clob_token_ids) else None,
                        "name": name,
                        "best_bid": price_val,
                        "best_ask": price_val,
                        "liquidity": liquidity_float,
                    }
                )
            market["outcomes"] = normalized_outcomes

    return market


def _extract_markets_from_event(event: Dict[str, object], verbose: bool = False) -> List[Dict[str, object]]:
    markets = event.get("markets") or []
    if not isinstance(markets, list):
        if verbose:
            print(f"DEBUG: event {event.get('id')} has no markets list")
        return []

    enriched: List[Dict[str, object]] = []
    for m in markets:
        if not isinstance(m, dict):
            continue
        m = dict(m)
        # Bring event context into the market
        m.setdefault("event_id", event.get("id"))
        m.setdefault("question", event.get("question") or event.get("title"))
        m.setdefault("group", event.get("group") or event.get("id"))
        m.setdefault("group_key", event.get("group") or event.get("id"))
        enriched.append(m)
    return enriched


def _stream_markets_via_events(
    gamma_host: str,
    status_filter: str,
    page_limit: int,
    verbose: bool = False,
) -> Generator[Dict[str, object], None, None]:
    offset = 0
    page = 0
    while True:
        page += 1
        params = {
            "order": "id",
            "ascending": "false",
            "closed": "false",
            "limit": page_limit,
            "offset": offset,
        }
        url = f"{gamma_host.rstrip('/')}/events"
        try:
            if verbose:
                print(f"DEBUG: GET {url} page={page} offset={offset} limit={page_limit}")
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            print(f"ERROR: failed to fetch events from {url}: {exc}")
            return

        if isinstance(payload, list):
            events = payload
        elif isinstance(payload, dict):
            events = payload.get("data") or payload.get("events") or []
        else:
            events = []
            if verbose:
                print(f"DEBUG: unexpected payload type from {url}: {type(payload)}")

        if verbose:
            print(f"DEBUG: received {len(events)} events on page {page}")
        if not events:
            break

        for e_idx, event in enumerate(events, start=1):
            for m_idx, market in enumerate(_extract_markets_from_event(event, verbose=verbose), start=1):
                normalized = normalize_market(market)
                if status_filter != "all":
                    is_open = market_looks_open(normalized)
                    if status_filter == "open" and not is_open:
                        if verbose:
                            print(
                                f"DEBUG: skip market {normalized.get('slug')} not open "
                                f"(event_page={page} event_item={e_idx} market_item={m_idx})"
                            )
                        continue
                    if status_filter == "closed" and is_open:
                        if verbose:
                            print(
                                f"DEBUG: skip market {normalized.get('slug')} open while filtering closed "
                                f"(event_page={page} event_item={e_idx} market_item={m_idx})"
                            )
                        continue
                if verbose:
                    print(
                        f"DEBUG: yield market {normalized.get('slug')} id={normalized.get('id')} "
                        f"event_id={normalized.get('event_id')} event_page={page} event_item={e_idx} market_item={m_idx}"
                    )
                yield normalized

        if len(events) < page_limit:
            break
        offset += page_limit


def stream_live_markets(
    host: str,
    chain_id: int,
    status_filter: str = "open",
    source: str = "gamma",
    gamma_host: str = DEFAULT_GAMMA_HOST,
    page_limit: int = DEFAULT_PAGE_LIMIT,
    verbose: bool = False,
) -> Generator[Dict[str, object], None, None]:
    if source == "gamma":
        yield from _stream_markets_via_events(
            gamma_host=gamma_host,
            status_filter=status_filter,
            page_limit=page_limit,
            verbose=verbose,
        )
        return

    if ClobClient is None:
        raise ImportError("py_clob_client is required for live scanning but is not installed")

    if load_dotenv:
        load_dotenv("keys.env")
        if verbose:
            print("DEBUG: loaded keys.env (if present)")

    api_key = os.getenv("API_KEY") or os.getenv("POLYMARKET_API_KEY")
    if verbose:
        print(f"DEBUG: using API key set? {'yes' if api_key else 'no'}")
    client = ClobClient(host, key=api_key, chain_id=chain_id) if api_key else ClobClient(host, chain_id=chain_id)

    cursor: Optional[str] = None
    page = 0
    while True:
        page += 1
        try:
            if verbose:
                print(f"DEBUG: fetching markets page={page} cursor={cursor}")
            response = client.get_markets() if cursor is None else client.get_markets(next_cursor=cursor)
        except Exception as exc:
            print(f"ERROR: unable to fetch markets: {exc}")
            return

        if not isinstance(response, dict):
            print(f"ERROR: unexpected response type {type(response)}")
            return

        payload = response.get("data") or response.get("markets") or []
        if not payload:
            if verbose:
                print(f"DEBUG: empty payload on page {page}")
            break

        if verbose:
            print(f"DEBUG: received {len(payload)} markets on page {page}")

        for idx, raw_market in enumerate(payload, start=1):
            normalized = normalize_market(raw_market)
            if status_filter != "all":
                is_open = market_looks_open(normalized)
                if status_filter == "open" and not is_open:
                    if verbose:
                        print(f"DEBUG: skip market {normalized.get('slug')} not open (page {page} item {idx})")
                    continue
                if status_filter == "closed" and is_open:
                    if verbose:
                        print(f"DEBUG: skip market {normalized.get('slug')} open while filtering closed (page {page} item {idx})")
                    continue
            if verbose:
                print(
                    f"DEBUG: yield market {normalized.get('slug')} id={normalized.get('id')} "
                    f"q={normalized.get('question')!r} page={page} item={idx}"
                )
            yield normalized

        cursor = response.get("next_cursor") or response.get("nextCursor")
        if verbose:
            print(f"DEBUG: next cursor={cursor}")
        if not cursor:
            break


def ensure_csv(path: str, verbose: bool = False) -> None:
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
        if verbose:
            print(f"DEBUG: created directory {directory} for CSV")
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()
        if verbose:
            print(f"DEBUG: wrote CSV header to {path}")


def append_opportunity_csv(path: str, opportunity: Dict[str, object], decision_ms: float, verbose: bool = False) -> None:
    ensure_csv(path, verbose=verbose)
    row = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "slug": opportunity.get("slug"),
        "market_id": (opportunity.get("market_ids") or [None])[0],
        "question": opportunity.get("question"),
        "net_edge": opportunity.get("net_edge"),
        "gross_edge": opportunity.get("gross_edge"),
        "total_ask": opportunity.get("total_ask"),
        "total_liquidity": opportunity.get("total_liquidity"),
        "decision_ms": round(decision_ms, 3),
    }
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writerow(row)
    if verbose:
        print(f"DEBUG: appended CSV row for slug={opportunity.get('slug')} decision_ms={decision_ms:.3f}")


def evaluate_market(
    client: PolymarketClient,
    raw_market: Dict[str, object],
    min_edge: float,
    verbose: bool = False,
) -> Tuple[Optional[Dict[str, object]], float]:
    start = time.perf_counter()
    try:
        parsed = client.parse_markets([raw_market])
    except Exception as exc:
        outcomes_val = raw_market.get("outcomes")
        print(
            f"DEBUG: failed to parse market {raw_market.get('slug') or raw_market.get('market_slug')}: {exc} "
            f"(outcomes type={type(outcomes_val)})"
        )
        return None, (time.perf_counter() - start) * 1000

    market = parsed[0] if parsed else None
    if market is None:
        return None, (time.perf_counter() - start) * 1000

    opportunity = compute_simple_sum_arb(market, min_edge=min_edge)
    decision_ms = (time.perf_counter() - start) * 1000
    if verbose:
        ask_sum = f"{opportunity['total_ask']:.4f}" if opportunity and "total_ask" in opportunity else "n/a"
        liquidity = opportunity.get("total_liquidity") if opportunity else "n/a"
        edge_msg = (
            f"net_edge={opportunity['net_edge']:.4f} gross_edge={opportunity['gross_edge']:.4f}"
            if opportunity
            else "no opportunity"
        )
        print(
            f"DEBUG: evaluated slug={getattr(market, 'slug', None)} "
            f"ask_sum={ask_sum} "
            f"liquidity={liquidity} "
            f"{edge_msg} decision_ms={decision_ms:.2f}"
        )
    return opportunity, decision_ms


def main():
    parser = argparse.ArgumentParser(description="Stream Polymarket markets and scan each one for arbitrage in real time.")
    parser.add_argument("--min-edge", type=float, default=MIN_EDGE, help="Minimum net edge to report.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="CLOB host to pull live markets from.")
    parser.add_argument("--gamma-host", default=DEFAULT_GAMMA_HOST, help="Gamma API host for events/markets.")
    parser.add_argument("--chain-id", type=int, default=DEFAULT_CHAIN_ID, help="Chain ID used by the CLOB host.")
    parser.add_argument(
        "--status-filter",
        choices=["open", "closed", "all"],
        default="open",
        help="Filter markets before scanning.",
    )
    parser.add_argument(
        "--source",
        choices=["gamma", "clob"],
        default="gamma",
        help="Data source for markets (gamma events API or CLOB).",
    )
    parser.add_argument(
        "--page-limit",
        type=int,
        default=DEFAULT_PAGE_LIMIT,
        help="Page size when pulling events from the gamma API.",
    )
    parser.add_argument(
        "--csv-path",
        default="data/arbitrage_hits.csv",
        help="Where to append arbitrage opportunities.",
    )
    parser.add_argument(
        "--json-path",
        default="data/opportunities.json",
        help="Optional JSON snapshot of found opportunities.",
    )
    parser.add_argument(
        "--decision-budget-ms",
        type=int,
        default=DECISION_BUDGET_MS,
        help="Warn if a per-market decision exceeds this many milliseconds.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed debug output for every step.",
    )
    args = parser.parse_args()

    client = PolymarketClient()
    opportunities: List[Dict[str, object]] = []
    scanned = 0

    print(
        f"Streaming markets source={args.source} "
        f"gamma_host={args.gamma_host if args.source == 'gamma' else 'n/a'} "
        f"clob_host={args.host if args.source == 'clob' else 'n/a'} "
        f"(chain_id={args.chain_id}) status={args.status_filter}; "
        f"min_edge={args.min_edge}, decision budget={args.decision_budget_ms}ms"
    )

    for raw_market in stream_live_markets(
        host=args.host,
        chain_id=args.chain_id,
        status_filter=args.status_filter,
        source=args.source,
        gamma_host=args.gamma_host,
        page_limit=args.page_limit,
        verbose=args.verbose,
    ):
        scanned += 1
        opportunity, decision_ms = evaluate_market(
            client,
            raw_market,
            min_edge=args.min_edge,
            verbose=args.verbose,
        )
        slug = raw_market.get("slug") or raw_market.get("market_slug") or raw_market.get("question", "")

        if opportunity:
            opportunities.append(opportunity)
            append_opportunity_csv(args.csv_path, opportunity, decision_ms, verbose=args.verbose)
            print(
                f"[HIT] slug={slug} net_edge={opportunity['net_edge']:.4f} "
                f"gross_edge={opportunity['gross_edge']:.4f} total_ask={opportunity['total_ask']:.4f} "
                f"liquidity={opportunity.get('total_liquidity')} decision_ms={decision_ms:.1f}"
            )
        elif decision_ms > args.decision_budget_ms:
            print(f"DEBUG: decision for slug={slug} took {decision_ms:.1f}ms (over budget)")

    if opportunities:
        save_opportunities(opportunities, path=args.json_path)
        print(f"Finished scanning {scanned} markets; found {len(opportunities)} opportunities. CSV: {args.csv_path}")
    else:
        print(f"Finished scanning {scanned} markets; no opportunities found.")


if __name__ == "__main__":
    main()
