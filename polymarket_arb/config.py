import os
from typing import Iterable, Tuple


def _load_env_file(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return

    def parse(line: str) -> Tuple[str, str]:
        key, value = line.split("=", 1)
        return key.strip(), value.strip().strip('"').strip("'")

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = parse(line)
        # Don't override already-set environment variables
        os.environ.setdefault(key, value)


_load_env_file()

POLYMARKET_API_BASE = os.getenv("POLYMARKET_API_BASE", "https://example-polymarket-api")
POLYMARKET_API_KEY = os.getenv("POLYMARKET_API_KEY", "")

FEE_RATE = float(os.getenv("POLYMARKET_FEE_RATE", "0.00"))
MAX_SLIPPAGE = float(os.getenv("POLYMARKET_MAX_SLIPPAGE", "0.01"))
MIN_EDGE = float(os.getenv("POLYMARKET_MIN_EDGE", "0.01"))
MIN_LIQUIDITY = float(os.getenv("POLYMARKET_MIN_LIQUIDITY", "500"))
