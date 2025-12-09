from polymarket_arb.execution import ExecutionBot


def main():
    bot = ExecutionBot()
    executed = bot.run()
    if not executed:
        print("No trades executed")
    else:
        for e in executed:
            print(f"Executed arb in market {e['market_id']}")


if __name__ == "__main__":
    main()
