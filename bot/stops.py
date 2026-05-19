"""SL/TP: фиксированные % или кратные ATR."""
from __future__ import annotations

from bot.config import RiskStopsConfig, Settings
from bot.strategy import Side


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def stop_tp_pcts(
    entry: float,
    atr: float,
    settings: Settings,
) -> tuple[float, float]:
    """Доли от цены (0.009 = 0.9%) для SL и TP."""
    rs = settings.risk_stops
    if rs.use_atr_stops and atr > 0 and entry > 0:
        sl = _clamp((atr * rs.sl_atr_mult) / entry, rs.min_sl_pct, rs.max_sl_pct)
        tp = _clamp((atr * rs.tp_atr_mult) / entry, rs.min_tp_pct, rs.max_tp_pct)
        return sl, tp
    return settings.stop_loss_pct, settings.take_profit_pct


def levels(
    side: Side,
    entry: float,
    atr: float,
    settings: Settings,
) -> tuple[float, float, float, float]:
    """entry, sl_price, tp_price, sl_pct."""
    sl_pct, tp_pct = stop_tp_pcts(entry, atr, settings)
    if side == Side.LONG:
        return entry, entry * (1 - sl_pct), entry * (1 + tp_pct), sl_pct
    return entry, entry * (1 + sl_pct), entry * (1 - tp_pct), sl_pct
