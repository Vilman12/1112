from __future__ import annotations

from dataclasses import dataclass

from bot.config import Settings
from bot.strategy import Side


@dataclass
class TradePlan:
    side: str
    quantity: float
    stop_loss: float
    take_profit: float
    position_side: str


def build_plan(settings: Settings, signal_side: Side, price: float) -> TradePlan | None:
    if signal_side == Side.FLAT:
        return None

    stop_pct = settings.stop_loss_pct
    tp_pct = settings.take_profit_pct

    if signal_side == Side.LONG:
        stop = price * (1 - stop_pct)
        tp = price * (1 + tp_pct)
        order_side = "buy"
        position_side = "LONG"
    else:
        stop = price * (1 + stop_pct)
        tp = price * (1 - tp_pct)
        order_side = "sell"
        position_side = "SHORT"

    return TradePlan(
        side=order_side,
        quantity=0.0,
        stop_loss=stop,
        take_profit=tp,
        position_side=position_side,
    )


def size_position(
    settings: Settings,
    balance_usdt: float,
    price: float,
    stop_pct: float,
) -> float:
    """Размер позиции из риска на сделку и дистанции до SL."""
    if balance_usdt <= 0 or price <= 0 or stop_pct <= 0:
        return settings.min_trade_btc

    risk_usdt = balance_usdt * settings.risk_per_trade
    qty_by_risk = risk_usdt / (price * stop_pct)
    # Потолок: доля депозита в марже × плечо = max notional (Futures)
    max_notional = balance_usdt * settings.max_balance_pct * settings.leverage
    cap_qty = max_notional / price
    qty = min(qty_by_risk, cap_qty)
    return max(qty, settings.min_trade_btc)
