from __future__ import annotations

import pandas as pd

from bot.strategy import Side


def apply_breakeven_trail(position: dict, row: pd.Series, cfg: dict) -> None:
    """Подтягивает SL: breakeven после X%, trail после Y%."""
    entry = position["entry"]
    high = float(row["high"])
    low = float(row["low"])
    be_trig = cfg.get("breakeven_trigger_pct", 0)
    be_lock = cfg.get("breakeven_lock_pct", 0.0008)
    trail_trig = cfg.get("trail_trigger_pct", 0)
    trail_off = cfg.get("trail_offset_pct", 0.003)

    if position["side"] == Side.LONG:
        if be_trig and high >= entry * (1 + be_trig):
            position["sl"] = max(position["sl"], entry * (1 + be_lock))
        if trail_trig and high >= entry * (1 + trail_trig):
            trail_sl = high * (1 - trail_off)
            position["sl"] = max(position["sl"], trail_sl)
    else:
        if be_trig and low <= entry * (1 - be_trig):
            position["sl"] = min(position["sl"], entry * (1 - be_lock))
        if trail_trig and low <= entry * (1 - trail_trig):
            trail_sl = low * (1 + trail_off)
            position["sl"] = min(position["sl"], trail_sl)


def check_exit(side: Side, row: pd.Series, sl: float, tp: float) -> tuple[float, str] | None:
    high = float(row["high"])
    low = float(row["low"])
    if side == Side.LONG:
        hit_sl = low <= sl
        hit_tp = high >= tp
        if hit_sl and hit_tp:
            return sl, "sl"
        if hit_sl:
            return sl, "sl"
        if hit_tp:
            return tp, "tp"
    else:
        hit_sl = high >= sl
        hit_tp = low <= tp
        if hit_sl and hit_tp:
            return sl, "sl"
        if hit_sl:
            return sl, "sl"
        if hit_tp:
            return tp, "tp"
    return None
