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

    macd_up = all(
        float(df.iloc[idx - k]["macd_hist"]) > float(df.iloc[idx - k - 1]["macd_hist"])
        for k in range(cfg.macd_rising_bars)
        if idx - k - 1 >= 0
    )
    macd_down = all(
        float(df.iloc[idx - k]["macd_hist"]) < float(df.iloc[idx - k - 1]["macd_hist"])
        for k in range(cfg.macd_rising_bars)
        if idx - k - 1 >= 0
    )

    htf_ok_long = not cfg.use_htf_filter or int(last.get("htf_bull", 0)) == 1
    htf_ok_short = not cfg.use_htf_filter or int(last.get("htf_bull", 0)) == 0

    if (
        bull
        and htf_ok_long
        and price > ema_s
        and touched_fast
        and price >= ema_f
        and cfg.rsi_long_min <= rsi <= cfg.rsi_long_max
        and hist > 0
        and macd_up
        and long_candle_ok
    ):
        return Signal(Side.LONG, "pullback_long", price)

    if not cfg.long_only and (
        bear
        and htf_ok_short
        and price < ema_s
        and touched_fast_short
        and price <= ema_f
        and cfg.rsi_short_min <= rsi <= cfg.rsi_short_max
        and hist < 0
        and macd_down
        and short_candle_ok
    ):
        return Signal(Side.SHORT, "pullback_short", price)

    return Signal(Side.FLAT, "no_setup", price)


def _evaluate_breakout(df: pd.DataFrame, idx: int, cfg: StrategyConfig) -> Signal:
    """Пробой диапазона в сторону тренда (1h + ADX)."""
    lb = cfg.breakout_lookback
    if idx < lb + 2:
        return Signal(Side.FLAT, "not_enough_data", float(df.iloc[idx]["close"]))

    prev = df.iloc[idx - 1]
    last = df.iloc[idx]
    price = float(last["close"])
    prev_close = float(prev["close"])

    if not _market_ok(last, cfg):
        return Signal(Side.FLAT, "filter_market", price)

    window = df.iloc[idx - lb : idx]
    range_high = float(window["high"].max())
    range_low = float(window["low"].min())
    ema_f = float(last["ema_fast"])
    ema_s = float(last["ema_slow"])
    bull = ema_f > ema_s * (1 + cfg.ema_sep_pct)
    bear = ema_f < ema_s * (1 - cfg.ema_sep_pct)
    htf_ok_long = not cfg.use_htf_filter or int(last.get("htf_bull", 0)) == 1
    htf_ok_short = not cfg.use_htf_filter or int(last.get("htf_bull", 0)) == 0

    long_break = prev_close <= range_high and price > range_high * 1.0002
    short_break = prev_close >= range_low and price < range_low * 0.9998

    if bull and htf_ok_long and long_break:
        return Signal(Side.LONG, "breakout_long", price)

    if not cfg.long_only and bear and htf_ok_short and short_break:
        return Signal(Side.SHORT, "breakout_short", price)

    return Signal(Side.FLAT, "no_setup", price)


def _signals_bundle(df: pd.DataFrame, idx: int, cfg: StrategyConfig) -> dict[str, Signal]:
    pb_cfg = StrategyConfig(**{**cfg.__dict__, "use_htf_filter": False})
    htf_cfg = StrategyConfig(**{**cfg.__dict__, "use_htf_filter": True})
    return {
        "classic": _evaluate_classic(df, idx, cfg),
        "pullback": _evaluate_pullback(df, idx, pb_cfg),
        "pullback_htf": _evaluate_pullback(df, idx, htf_cfg),
        "breakout": _evaluate_breakout(df, idx, htf_cfg),
    }


def _pick_or(signals: dict[str, Signal], order: list[str], price: float) -> Signal:
    """Приоритет: первый сработавший сигнал в списке."""
    for key in order:
        s = signals[key]
        if s.side != Side.FLAT:
            return Signal(s.side, f"combo_or_{key}_{s.reason}", price)
    return Signal(Side.FLAT, "combo_or_none", price)


def _pick_and(signals: list[Signal], price: float, tag: str) -> Signal:
    if not signals or any(s.side == Side.FLAT for s in signals):
        return Signal(Side.FLAT, f"combo_and_{tag}", price)
    side = signals[0].side
    if any(s.side != side for s in signals):
        return Signal(Side.FLAT, f"combo_and_{tag}_conflict", price)
    return Signal(side, f"combo_{tag}", price)


def _pick_vote(signals: dict[str, Signal], price: float, min_votes: int = 2) -> Signal:
    longs = sum(1 for s in signals.values() if s.side == Side.LONG)
    shorts = sum(1 for s in signals.values() if s.side == Side.SHORT)
    if longs >= min_votes and longs > shorts:
        return Signal(Side.LONG, f"combo_vote{min_votes}_long", price)
    if shorts >= min_votes and shorts > longs:
        return Signal(Side.SHORT, f"combo_vote{min_votes}_short", price)
    return Signal(Side.FLAT, "combo_vote_none", price)


def evaluate_combo_at(df: pd.DataFrame, idx: int, cfg: StrategyConfig, combo: str) -> Signal:
    """Комбинации: and_cp, or_cp, and_all, vote2, classic+htf, ..."""
    if idx < 2 or idx >= len(df):
        return Signal(Side.FLAT, "not_enough_data", 0.0)

    price = float(df.iloc[idx]["close"])
    sig = _signals_bundle(df, idx, cfg)
    c, p, ph, b = sig["classic"], sig["pullback"], sig["pullback_htf"], sig["breakout"]

    if combo in ("classic",):
        return c
    if combo in ("pullback",):
        return p
    if combo in ("pullback_htf",):
        return ph
    if combo in ("breakout",):
        return b

    if combo == "and_cp":
        return _pick_and([c, p], price, "cp")
    if combo == "and_cph":
        return _pick_and([c, ph], price, "cph")
    if combo == "and_pb":
        return _pick_and([ph, b], price, "pb")
    if combo == "and_all":
        return _pick_and([c, ph, b], price, "all")
    if combo == "or_cp":
        return _pick_or(sig, ["classic", "pullback"], price)
    if combo == "or_cph":
        return _pick_or(sig, ["classic", "pullback_htf"], price)
    if combo == "or_pb":
        return _pick_or(sig, ["pullback_htf", "breakout"], price)
    if combo == "vote2":
        return _pick_vote(sig, price, 2)
    if combo == "vote2_no_classic":
        return _pick_vote({"pullback_htf": ph, "breakout": b}, price, 2)
    if combo == "classic_htf_trend":
        if c.side == Side.FLAT:
            return c
        htf_bull = int(df.iloc[idx].get("htf_bull", 0))
        if c.side == Side.LONG and htf_bull != 1:
            return Signal(Side.FLAT, "htf_block_long", price)
        if c.side == Side.SHORT and htf_bull != 0:
            return Signal(Side.FLAT, "htf_block_short", price)
        return c

    return Signal(Side.FLAT, f"unknown_combo_{combo}", price)


def evaluate_at(df: pd.DataFrame, idx: int, cfg: StrategyConfig) -> Signal:
    if idx < 2 or idx >= len(df):
        return Signal(Side.FLAT, "not_enough_data", 0.0)

    if cfg.combo:
        return evaluate_combo_at(df, idx, cfg, cfg.combo)

    if cfg.mode == "classic":
        return _evaluate_classic(df, idx, cfg)
    if cfg.mode == "breakout":
        return _evaluate_breakout(df, idx, cfg)
    if cfg.mode == "pullback":
        return _evaluate_pullback(df, idx, cfg)
    if cfg.mode.startswith("combo:"):
        return evaluate_combo_at(df, idx, cfg, cfg.mode.split(":", 1)[1])
    return _evaluate_pullback(df, idx, cfg)


def evaluate(df: pd.DataFrame, cfg: StrategyConfig) -> Signal:
    if len(df) < 3:
        return Signal(Side.FLAT, "not_enough_data", 0.0)
    return evaluate_at(df, len(df) - 2, cfg)
