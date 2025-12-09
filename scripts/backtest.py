from polymarket_arb.backtest import run_backtest


def main():
    df = run_backtest()
    if df.empty:
        print("No historical snapshots found in data/historical")
        return
    print(df)
    print()
    print("Summary:")
    print(df.describe())


if __name__ == "__main__":
    main()
