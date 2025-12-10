
# Polymarket Arbitrage

This is a project I worked on in 2024 to find arbitrage in Polymarket.com specifically as it pertained to the Presidential elections. My original writeup on this can be found here: [Arbitrage in Polymarket.com](https://jeremywhittaker.com/index.php/2024/09/24/arbitrage-in-polymarket-com/).

The repository includes Python scripts and utilities to interact with the Polymarket Central Limit Order Book (CLOB) API on Polygon Mainnet (chain ID 137). These scripts enable:

- Generating/fetching API keys
- Fetching real-time or historical market data (prices, volumes, order books)
- Searching and analyzing markets
- Calculating arbitrage opportunities
- Scraping leaderboards
- Managing user trades (fetching, storing, analyzing)
- Automated or semi-automated trading logic

**Important**: All sensitive data (private key, secrets, passphrases) must be stored in environment variables (`keys.env` or `.env`). **Never** commit private keys to source control.

---

## Table of Contents
1. [Installation and Dependencies](#installation-and-dependencies)
2. [Environment Setup](#environment-setup)
3. [Project Structure](#project-structure)
4. [Script Descriptions](#script-descriptions)
5. [Usage Examples](#usage-examples)
6. [Outdated / Duplicate Scripts](#outdated--duplicate-scripts)
7. [Recommendations and Best Practices](#recommendations-and-best-practices)
8. [Disclaimer](#disclaimer)
9. [License](#license)

---

## Installation and Dependencies

### Python Version
Python 3.9+ recommended.

### Create and Activate a Virtual Environment
```bash
python -m venv venv
source venv/bin/activate   # Linux/Mac
# or
venv\Scripts\activate      # Windows
```

### Install Dependencies
```bash
pip install -r requirements.txt
```

### ChromeDriver (For scripts using Selenium)
You may need to download a matching [ChromeDriver](https://sites.google.com/chromium.org/driver/) for your Chrome version.

---

## Environment Setup

### `keys.env` / `.env`
Store your sensitive data:
```bash
PK=<YOUR_PRIVATE_KEY>
API_KEY=<YOUR_API_KEY>
SECRET=<YOUR_API_SECRET>
PASSPHRASE=<YOUR_API_PASSPHRASE>
POLYGONSCAN_API_KEY=<YOUR_POLYGONSCAN_KEY>
```
Always add `.env` and `keys.env` to your `.gitignore`.

### Run
```bash
source keys.env  # Or use dotenv
```

---

## Project Structure
```bash
.
├── data/
│   ├── markets_data.csv
│   ├── market_lookup.json
│   ├── user_trades/
│   ├── historical/
│   ├── book_data/
│   ├── polymarket_trades/
│   ├── ...
├── old/
│   └── condition_id_question_mapping.json
├── plots/
│   └── # HTML/visual outputs from Plotly
├── strategies/
│   └── # Arbitrage strategies or multi-trade definitions
├── create_markets_data_csv.py
├── derive_api_key.py
├── generate_api_key.py
├── generate_market_lookup_json.py
├── generate_markets_data_csv.py
├── get_all_historical_data.py
├── get_api_key.py
├── get_leaderboard_wallet_ids.py
├── get_live_price.py
├── get_market_book_and_live_arb.py
├── get_order_book.py
├── get_polygon_data.py
├── get_polygon_latest_trade_price.py
├── get_presidential_state_odds.py
├── get_trade_slugs_to_parquet.py
├── get_user_profile.py
├── get_user_trade_prices.py
├── goldsky.py
├── live_trade.py
├── plot_arb.py
├── rcp_poller.py
├── strategies.py
├── keys.env
├── .env
└── README.md
```

---


# Script Descriptions

Below is a brief overview of each script:

### `create_markets_data_csv.py`
- **Purpose**: Fetch all Polymarket CLOB markets and store as CSV (`./data/markets_data.csv`).
- **Notes**: A simpler or older approach. Potentially replaced by `generate_markets_data_csv.py`.

### `derive_api_key.py`
- **Purpose**: Demonstrates deriving an API key from your private key (`PK`).
- **Notes**: Example usage of `client.derive_api_key()` from `py_clob_client`.

### `generate_api_key.py`
- **Purpose**: Similar to `derive_api_key.py`, but uses `client.create_or_derive_api_creds()`.
- **Notes**: Outputs `API_KEY`, `SECRET`, and `PASSPHRASE` which you must store securely.

### `generate_market_lookup_json.py`
- **Purpose**: Reads `markets_data.csv` and generates `market_lookup.json`, mapping `condition_id` → details (`description`, `market_slug`, `tokens`).
- **Notes**: Helps with quick lookups of `slug`, `outcome`, and `token_id`.

### `generate_markets_data_csv.py`
- **Purpose**: A more robust or updated market-fetching script, includes additional logic (pagination, keyword search).
- **Notes**: Potentially supersedes `create_markets_data_csv.py`.

### `get_all_historical_data.py`
- **Purpose**: Uses `markets_data.csv` to pull minute-level historical prices for each market token. Saves to Parquet/CSV in `./data/historical`.
- **Notes**: Useful for time-series analysis or backtesting.

### `get_api_key.py`
- **Purpose**: Fetches existing API keys linked to your Polymarket account using `client.get_api_keys()`.
- **Notes**: Must have set creds from `.env` or `keys.env`.

### `get_leaderboard_wallet_ids.py`
- **Purpose**: Scrapes Polymarket’s leaderboard page (volume/profit) for top addresses using Selenium + BeautifulSoup.
- **Notes**: Uses ChromeDriver in headless mode. Outputs JSON to stdout by default.

### `get_live_price.py`
- **Purpose**: Fetch last-trade price of a token ID from Polymarket CLOB. Implements caching to minimize repeated calls.
- **Notes**: Called by scripts that need up-to-date prices.

### `get_market_book_and_live_arb.py`
- **Purpose**: Integrates user trade data, real-time order books, and `live_price` to calculate arbitrage. Renders HTML summary with `jinja2`.
- **Notes**: Runs continuously if desired, updating every X minutes. Great for live monitoring.

### `get_order_book.py`
- **Purpose**: Fetch order books for relevant trades (from `strategies.py`), store as CSV in `./data/book_data`.
- **Notes**: Typically invoked before `get_market_book_and_live_arb.py` or other arbitrage scripts.

### `get_polygon_data.py`
- **Purpose**: Comprehensive script to fetch user trade data (ERC-20 and ERC-1155 from Polygonscan), enrich with market info, merge, calculate P/L, produce plots, etc.
- **Notes**: Calls sub-processes like `get_live_price.py`.
- **Output**: Writes enriched transaction data to CSV and/or Parquet in `./data/user_trades/`.

### `get_polygon_latest_trade_price.py`
- **Purpose**: Similar to `get_polygon_data.py` but focuses on retrieving the latest transaction prices for specific markets/trades.
- **Notes**: Good for “just-in-time” price checks, merges data with user profiles, updates `latest_blockchain_prices.json`.

### `get_presidential_state_odds.py`
- **Purpose**: Specialized for fetching presidential election data by U.S. states (e.g., “Will Republicans or Democrats win?”).
- **Notes**: Builds `state_condition_map` from search results and writes odds to `state_odds.csv`.

### `get_trade_slugs_to_parquet.py`
- **Purpose**: Given a token ID, market slug, and outcome, fetch minute-level timeseries from Polymarket `/prices-history`.
- **Notes**: Saves to both Parquet and optional CSV for easy repeated analysis (`./data/historical`).

### `get_user_profile.py`
- **Purpose**: Uses Selenium to scrape Polymarket user profile pages for user details (username, P/L, volume, etc.).
- **Notes**: Invoked by other scripts to attach user metadata to addresses.

### `get_user_trade_prices.py`
- **Purpose**: Orchestrates user trades and merges them with strategies.
- **Notes**: Calls `get_polygon_data.py` as a subprocess, loads strategies from `strategies.py`, and generates HTML summary.

### `goldsky.py`
- **Purpose**: Demonstrates how to download a Parquet from S3 (GoldSky data) and load it into a DataFrame.
- **Notes**: Contains AWS credentials for example (should store them securely!).

### `live_trade.py`
- **Purpose**: Example of how to place live trades (limit or market) via `py_clob_client`.
- **Notes**: Includes logic for checking balances/allowances, adjusting limit price, etc. **Use caution in production.**

### `plot_arb.py`
- **Purpose**: Aggregates, merges, and plots various trades from `strategies.py`.
- **Notes**: Uses `get_trade_slugs_to_parquet.py` behind the scenes to fetch data, then produces Plotly HTML. Helps visualize multi-leg positions & arbitrage %.

### `rcp_poller.py`
- **Purpose**: Example script polling a RealClearPolitics page for poll data. Sends Twilio WhatsApp alerts if changes occur.
- **Notes**: Demonstrates web scraping + push notifications. Not strictly a Polymarket script but relevant for external signals.

### `strategies.py`
- **Purpose**: Defines a Python list of trades describing multi-leg trades or “basket trades.” Each dictionary includes:
  - `trade_name`, `subtitle`,
  - `side_a_trades` and `side_b_trades` (for “balanced” method)
  - or `positions` for “all_no.”
- **Notes**: Scripts like `get_market_book_and_live_arb.py` and `plot_arb.py` reference these entries to systematically fetch and analyze data.

---

## Usage Examples

### Generate or Derive API Key
```bash
python generate_api_key.py
# or
python derive_api_key.py
```
Place outputs in `keys.env`.

### Fetch All Markets → CSV
```bash
python generate_markets_data_csv.py
# or the older version
python create_markets_data_csv.py
```

### Create Market Lookup JSON
```bash
python generate_market_lookup_json.py
```

### Pull Historical Data
```bash
python get_all_historical_data.py
```

### Retrieve User Data from Polygonscan (ERC-20 / ERC-1155 trades)
```bash
python get_polygon_data.py --wallets 0xYourAddressHere
```
This produces an enriched CSV/Parquet in `./data/user_trades/`.

### Fetch Live Order Book
```bash
python get_order_book.py
```

### Monitor and Calculate Arbitrage
```bash
python get_market_book_and_live_arb.py
```

### Plot Trade Slugs (historical price)
```bash
python get_trade_slugs_to_parquet.py <token_id> <market_slug> <outcome>
# Then
python plot_arb.py
```
