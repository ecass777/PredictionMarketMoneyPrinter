class Outcome:
    def __init__(self, outcome_id, name, best_bid, best_ask, liquidity):
        self.outcome_id = outcome_id
        self.name = name
        self.best_bid = best_bid
        self.best_ask = best_ask
        self.liquidity = liquidity

    @property
    def mid_price(self):
        if self.best_bid is None and self.best_ask is None:
            return None
        if self.best_bid is None:
            return self.best_ask
        if self.best_ask is None:
            return self.best_bid
        return (self.best_bid + self.best_ask) / 2.0


class Market:
    def __init__(self, market_id, question, group_key, outcomes, rules, volume, end_time, slug=None):
        self.market_id = market_id
        self.question = question
        self.group_key = group_key
        self.outcomes = outcomes
        self.rules = rules
        self.volume = volume
        self.end_time = end_time
        self.slug = slug

    def total_liquidity(self):
        total = 0.0
        for outcome in self.outcomes:
            if outcome.liquidity:
                total += outcome.liquidity
        return total

    def implied_prob_sum(self, use_ask=True):
        total = 0.0
        for outcome in self.outcomes:
            if use_ask and outcome.best_ask is not None:
                total += outcome.best_ask
            elif not use_ask and outcome.best_bid is not None:
                total += outcome.best_bid
        return total
