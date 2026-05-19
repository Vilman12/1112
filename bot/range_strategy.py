"""Mean reversion в режиме range (RSI + границы диапазона)."""
from __future__ import annotations

import pandas as pd

from bot.config import StrategyConfig
from bot.strategy import Side, Signal


def evaluate_range_at(df: pd.DataFrame, idx: int, cfg: StrategyConfig) -> Signal:
    if idx < 22:
        return Signal(Side.FLAT, "not_enough_data", 0.0)

    last = df.iloc[idx]
    price = float(last["close"])
    rsi = float(last["rsi"])
    support = float(last["support"])
    resistance = float(last["resistance"])
    buf = cfg.support_buffer_pct

    near_support = price <= support * (1 + buf * 2)
    near_resistance = price >= resistance * (1 - buf * 2)

    if near_support and rsi <= cfg.stoch_oversold + 5:
        return Signal(Side.LONG, "range_long", price)

    if not cfg.long_only and near_resistance and rsi >= cfg.stoch_overbought - 5:
        return Signal(Side.SHORT, "range_short", price)

    return Signal(Side.FLAT, "range_no_setup", price)
