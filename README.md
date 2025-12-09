# Polymarket Arbitrage Bot

This repo contains four main pieces:

1. Arbitrage scanner  
2. Dash dashboard for visualizing opportunities  
3. Execution bot for placing trades  
4. Backtesting engine for evaluating strategies on historical market snapshots  

The code is structured so you can start with scanning and backtesting using saved data, then wire up the live Polymarket API and execution once you are ready.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Configuration

Set environment variables as needed:

* `POLYMARKET_API_BASE` – base URL for Polymarket markets endpoint
* `POLYMARKET_API_KEY` – if you need authenticated access (optional)
* `POLYMARKET_MAX_SLIPPAGE` – max slippage in probability points (e.g. 0.01)
* `POLYMARKET_FEE_RATE` – platform fee rate as decimal (e.g. 0.02)

You can also edit `polymarket_arb/config.py` directly.

## Usage

### 1) Scan for arbitrage

```bash
python scripts/scan.py
```

This will print a table of opportunities to stdout and save JSON to `data/opportunities.json` if the `data/` directory exists.

### 2) Run dashboard

```bash
python scripts/dashboard.py
```

Then open the Dash URL in your browser. The dashboard reads the latest `data/opportunities.json`.

### 3) Execute arbitrage trades

```bash
python scripts/execute.py
```

This uses the same scanner to identify opportunities and then calls the execution layer. You must implement the real order placement in `polymarket_arb/client.py`.

### 4) Backtesting

Place historical snapshots (CSV or JSON) in `data/historical/` and run:

```bash
python scripts/backtest.py
```

The backtester will apply the scanner logic to each snapshot and aggregate performance statistics.

## Notes

* By default, HTTP client methods in `polymarket_arb/client.py` are minimal placeholders; you should wire them to the actual Polymarket API.
* All risk is on you. Read market rules carefully and validate that the arbitrage is real after fees, slippage, and tail scenarios.

