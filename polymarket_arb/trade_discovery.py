import re
from typing import Dict, List, Tuple

from .market_cache import load_market_lookup


CandidateEntry = Dict[str, str]


def _looks_mutually_exclusive(description: str, rules: str) -> bool:
    text = f"{description} {rules}".lower()
    keywords = [
        "mutually exclusive",
        "only one",
        "exactly one",
        "single outcome",
        "one of",
    ]
    return any(k in text for k in keywords)


def discover_all_no_trades(market_lookup: Dict[str, Dict]) -> List[Dict]:
    """
    Build all_no trades for markets with 3+ outcomes that appear mutually exclusive.
    """
    strategies: List[Dict] = []
    for info in market_lookup.values():
        tokens = info.get("tokens") or []
        if len(tokens) < 3:
            continue

        description = info.get("description", "")
        rules = info.get("rules", "")
        if not _looks_mutually_exclusive(description, rules):
            continue

        slug = info.get("market_slug") or info.get("slug")
        if not slug:
            continue

        positions: List[Tuple[str, str]] = []
        for token in tokens:
            outcome = token.get("outcome")
            if outcome:
                positions.append((slug, outcome))

        if not positions:
            continue

        strategies.append({
            "trade_name": f"all_no_{slug}",
            "method": "all_no",
            "positions": positions,
            "description": description,
        })
    return strategies


_CANDIDATE_KEYWORDS = {
    "trump": ["trump"],
    "harris": ["harris"],
    "biden": ["biden"],
    "democratic": ["democrat", "democratic", "dems"],
    "republican": ["republican", "gop"],
}

_PREFERRED_PAIRS = {
    ("democratic", "republican"),
    ("republican", "democratic"),
    ("trump", "harris"),
    ("harris", "trump"),
    ("trump", "biden"),
    ("biden", "trump"),
}


def _detect_candidate(text: str) -> str:
    lowered = text.lower()
    for candidate, keywords in _CANDIDATE_KEYWORDS.items():
        if any(k in lowered for k in keywords):
            return candidate
    return ""


def _detect_category(slug: str, description: str) -> str:
    text = f"{slug} {description}".lower()
    if "popular vote" in text or "popular-vote" in text:
        return "popular_vote"
    if "electoral" in text:
        return "electoral_college"
    if "balance of power" in text:
        return "balance_of_power"
    if "president" in text or "presidency" in text:
        return "presidency"
    if re.search(r"wins?[- ]by", text):
        return "margin_bins"
    return ""


def _infer_outcome(tokens: List[Dict], candidate: str) -> str:
    outcomes = [t.get("outcome") for t in tokens if isinstance(t, dict) and t.get("outcome")]
    if not outcomes:
        return ""

    if "Yes" in outcomes:
        return "Yes"

    cand_lower = candidate.lower()
    for outcome in outcomes:
        if cand_lower and cand_lower in str(outcome).lower():
            return outcome

    return str(outcomes[0])


def _collect_candidate_entries(market_lookup: Dict[str, Dict]) -> List[CandidateEntry]:
    entries: List[CandidateEntry] = []
    for info in market_lookup.values():
        slug = info.get("market_slug") or info.get("slug")
        description = info.get("description", "")
        tokens = info.get("tokens") or []
        if not slug:
            continue

        candidate = _detect_candidate(f"{slug} {description}")
        category = _detect_category(slug, description)
        if not candidate or not category:
            continue

        outcome = _infer_outcome(tokens, candidate)
        if not outcome:
            continue

        entries.append({
            "slug": slug,
            "outcome": outcome,
            "candidate": candidate,
            "category": category,
            "description": description,
        })
    return entries


def discover_simple_balanced_trades(market_lookup: Dict[str, Dict]) -> List[Dict]:
    """
    Build balanced trades by pairing obvious complements (e.g., DEM vs GOP popular vote buckets).
    """
    entries = _collect_candidate_entries(market_lookup)
    by_category: Dict[str, Dict[str, List[CandidateEntry]]] = {}
    for entry in entries:
        by_category.setdefault(entry["category"], {}).setdefault(entry["candidate"], []).append(entry)

    strategies: List[Dict] = []
    for category, candidates in by_category.items():
        for side_a, side_b in _PREFERRED_PAIRS:
            if side_a not in candidates or side_b not in candidates:
                continue

            side_a_trades = [(e["slug"], e["outcome"]) for e in candidates[side_a]]
            side_b_trades = [(e["slug"], e["outcome"]) for e in candidates[side_b]]
            if not side_a_trades or not side_b_trades:
                continue

            trade_name = f"{category}_{side_a}_vs_{side_b}"
            strategies.append({
                "trade_name": trade_name,
                "method": "balanced",
                "side_a_trades": side_a_trades,
                "side_b_trades": side_b_trades,
                "description": f"{category} pairing {side_a} vs {side_b}",
            })

    return strategies


def discover_trades() -> List[Dict]:
    """
    Load market_lookup and return discovered strategies.
    """
    market_lookup, _ = load_market_lookup()
    if not market_lookup:
        return []

    strategies = []
    strategies.extend(discover_all_no_trades(market_lookup))
    strategies.extend(discover_simple_balanced_trades(market_lookup))
    return strategies
