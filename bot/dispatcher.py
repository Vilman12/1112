"""Маршрутизация сигнала по режиму рынка."""
from __future__ import annotations

import pandas as pd

from bot.config import Settings
from bot.range_strategy import evaluate_range_at
from bot.regime import MarketRegime
from bot.strategy import Side, Signal, StrategyConfig, evaluate_at


def evaluate_dispatch(df: pd.DataFrame, idx: int, settings: Settings) -> Signal:
    price = float(df.iloc[idx]["close"])

    if not settings.regime.enabled:
        return evaluate_at(df, idx, settings.strategy)

    regime = str(df.iloc[idx].get("regime", MarketRegime.CHAOS.value))

    if regime == MarketRegime.CHAOS.value:
        return Signal(Side.FLAT, "regime_chaos", price)

    if regime == MarketRegime.TREND.value:
        trend_cfg = StrategyConfig(
            **{**settings.strategy.__dict__, "mode": "classic", "combo": ""}
        )
        sig = evaluate_at(df, idx, trend_cfg)
        if sig.side != Side.FLAT:
            return Signal(sig.side, f"trend_{sig.reason}", sig.price)
        return sig

    if regime == MarketRegime.RANGE.value:
        sig = evaluate_range_at(df, idx, settings.strategy)
        if sig.side != Side.FLAT:
            return Signal(sig.side, f"range_{sig.reason}", sig.price)
        return sig

    return Signal(Side.FLAT, "regime_unknown", price)
