import os

POLYMARKET_API_BASE = os.getenv("POLYMARKET_API_BASE", "https://example-polymarket-api")
POLYMARKET_API_KEY = os.getenv("POLYMARKET_API_KEY", "")

FEE_RATE = float(os.getenv("POLYMARKET_FEE_RATE", "0.02"))
MAX_SLIPPAGE = float(os.getenv("POLYMARKET_MAX_SLIPPAGE", "0.01"))
MIN_EDGE = float(os.getenv("POLYMARKET_MIN_EDGE", "0.01"))
MIN_LIQUIDITY = float(os.getenv("POLYMARKET_MIN_LIQUIDITY", "500"))
