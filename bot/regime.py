"""Определение режима рынка: trend | range | chaos."""
from __future__ import annotations

from enum import Enum

import pandas as pd

from bot.config import RegimeConfig


class MarketRegime(str, Enum):
    TREND = "trend"
    RANGE = "range"
    CHAOS = "chaos"


def detect_regime(row: pd.Series, cfg: RegimeConfig) -> str:
    atr_pct = float(row["atr_pct"])
    adx = float(row["adx"])

    if atr_pct < cfg.chaos_atr_pct_min or atr_pct > cfg.chaos_atr_pct_max:
        return MarketRegime.CHAOS.value

    close = float(row["close"])
    ema_f = float(row["ema_fast"])
    ema_s = float(row["ema_slow"])
    ema_sep = abs(ema_f - ema_s) / close if close else 0.0

    slope = float(row.get("ema_slope_1d", 0) or 0)
    if abs(slope) < cfg.min_daily_trend_slope:
        # слабый макро-тренд → чаще range или chaos
        if adx <= cfg.range_adx_max:
            return MarketRegime.RANGE.value
        return MarketRegime.CHAOS.value

    if adx >= cfg.trend_adx_min and ema_sep >= cfg.trend_ema_sep_pct:
        return MarketRegime.TREND.value

    if adx <= cfg.range_adx_max:
        return MarketRegime.RANGE.value

    return MarketRegime.CHAOS.value


def attach_daily_trend(df: pd.DataFrame, ema_span: int = 200) -> pd.DataFrame:
    out = df.copy()
    daily = (
        out.set_index("timestamp")[["close"]]
        .resample("1D")
        .last()
        .dropna()
    )
    daily["ema_slow_1d"] = daily["close"].ewm(span=ema_span, adjust=False).mean()
    daily["ema_slope_1d"] = daily["ema_slow_1d"].pct_change(5)
    out = out.merge(
        daily[["ema_slope_1d"]],
        left_on="timestamp",
        right_index=True,
        how="left",
    )
    out["ema_slope_1d"] = out["ema_slope_1d"].ffill().fillna(0)
    return out


def attach_regime(df: pd.DataFrame, cfg: RegimeConfig) -> pd.DataFrame:
    out = attach_daily_trend(df)
    if not cfg.enabled:
        out["regime"] = MarketRegime.TREND.value
        return out
    regimes = [detect_regime(out.iloc[i], cfg) for i in range(len(out))]
    out["regime"] = regimes
    return out
