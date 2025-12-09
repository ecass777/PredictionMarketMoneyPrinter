import os
import sys

# Add project root so polymarket_arb package can be imported when running the script directly
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

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
