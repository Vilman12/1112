from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd

from bot.config import StrategyConfig


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


@dataclass
class Signal:
    side: Side
    reason: str
    price: float


def evaluate(df: pd.DataFrame, cfg: StrategyConfig) -> Signal:
    """Сигнал по закрытой свече (-2), не по текущей формирующейся."""
    if len(df) < 3:
        return Signal(Side.FLAT, "not_enough_data", 0.0)

    prev = df.iloc[-3]
    last = df.iloc[-2]
    price = float(last["close"])

    bull_trend = last["ema_fast"] > last["ema_slow"]
    bear_trend = last["ema_fast"] < last["ema_slow"]
    macd_bull = last["macd"] > last["macd_signal"]
    macd_bear = last["macd"] < last["macd_signal"]
    stoch_cross_up = prev["stoch_k"] <= prev["stoch_d"] and last["stoch_k"] > last["stoch_d"]
    stoch_cross_down = prev["stoch_k"] >= prev["stoch_d"] and last["stoch_k"] < last["stoch_d"]
    near_support = price <= float(last["support"]) * (1 + cfg.support_buffer_pct)
    near_resistance = price >= float(last["resistance"]) * (1 - cfg.support_buffer_pct)

    if (
        bull_trend
        and macd_bull
        and stoch_cross_up
        and last["stoch_k"] < cfg.stoch_overbought
        and near_support
    ):
        return Signal(Side.LONG, "trend+macd+stoch_up+support", price)

    if (
        bear_trend
        and macd_bear
        and stoch_cross_down
        and last["stoch_k"] > cfg.stoch_oversold
        and near_resistance
    ):
        return Signal(Side.SHORT, "trend+macd+stoch_down+resistance", price)

    return Signal(Side.FLAT, "no_setup", price)
