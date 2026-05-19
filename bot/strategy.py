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


def _market_ok(last: pd.Series, cfg: StrategyConfig) -> bool:
    atr_pct = float(last["atr_pct"])
    adx = float(last["adx"])
    if atr_pct < cfg.min_atr_pct or atr_pct > cfg.max_atr_pct:
        return False
    if adx < cfg.adx_min:
        return False
    vol_ok = float(last["volume"]) >= float(last["vol_sma"]) * cfg.volume_factor
    return vol_ok


def _evaluate_classic(df: pd.DataFrame, idx: int, cfg: StrategyConfig) -> Signal:
    prev = df.iloc[idx - 1]
    last = df.iloc[idx]
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
        return Signal(Side.LONG, "classic_long", price)

    if (
        bear_trend
        and macd_bear
        and stoch_cross_down
        and last["stoch_k"] > cfg.stoch_oversold
        and near_resistance
    ):
        return Signal(Side.SHORT, "classic_short", price)

    return Signal(Side.FLAT, "no_setup", price)


def _evaluate_pullback(df: pd.DataFrame, idx: int, cfg: StrategyConfig) -> Signal:
    """v2: вход на откате к EMA в тренде — выше win rate, меньше «случайных» пробоев S/R."""
    prev = df.iloc[idx - 1]
    last = df.iloc[idx]
    price = float(last["close"])
    ema_f = float(last["ema_fast"])
    ema_s = float(last["ema_slow"])

    if not _market_ok(last, cfg):
        return Signal(Side.FLAT, "filter_market", price)

    bull = ema_f > ema_s * (1 + cfg.ema_sep_pct)
    bear = ema_f < ema_s * (1 - cfg.ema_sep_pct)
    hist = float(last["macd_hist"])
    hist_prev = float(prev["macd_hist"])
    rsi = float(last["rsi"])

    touched_fast = float(last["low"]) <= ema_f * (1 + cfg.pullback_pct)
    touched_fast_short = float(last["high"]) >= ema_f * (1 - cfg.pullback_pct)
    bull_candle = float(last["close"]) > float(last["open"])
    bear_candle = float(last["close"]) < float(last["open"])

    if cfg.require_bullish_candle:
        long_candle_ok = bull_candle
        short_candle_ok = bear_candle
    else:
        long_candle_ok = short_candle_ok = True

    if (
        bull
        and price > ema_s
        and touched_fast
        and price >= ema_f
        and cfg.rsi_long_min <= rsi <= cfg.rsi_long_max
        and hist > 0
        and hist > hist_prev
        and long_candle_ok
    ):
        return Signal(Side.LONG, "pullback_long", price)

    if (
        bear
        and price < ema_s
        and touched_fast_short
        and price <= ema_f
        and cfg.rsi_short_min <= rsi <= cfg.rsi_short_max
        and hist < 0
        and hist < hist_prev
        and short_candle_ok
    ):
        return Signal(Side.SHORT, "pullback_short", price)

    return Signal(Side.FLAT, "no_setup", price)


def evaluate_at(df: pd.DataFrame, idx: int, cfg: StrategyConfig) -> Signal:
    if idx < 2 or idx >= len(df):
        return Signal(Side.FLAT, "not_enough_data", 0.0)

    if cfg.mode == "classic":
        return _evaluate_classic(df, idx, cfg)
    return _evaluate_pullback(df, idx, cfg)


def evaluate(df: pd.DataFrame, cfg: StrategyConfig) -> Signal:
    if len(df) < 3:
        return Signal(Side.FLAT, "not_enough_data", 0.0)
    return evaluate_at(df, len(df) - 2, cfg)
