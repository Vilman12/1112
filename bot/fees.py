"""Комиссии Binance USDT-M Futures (market = taker)."""

# Стандартный taker без VIP / BNB — консервативно для бэктеста
TAKER_FEE = 0.0005  # 0.05% за сторону (market)
MAKER_FEE = 0.0002  # 0.02% — limit на откате (оптимистичный вход)
ROUND_TRIP_FEE = TAKER_FEE * 2  # вход + выход, оба taker


def trade_fees(
    entry: float,
    exit_px: float,
    qty: float,
    fee_rate: float = TAKER_FEE,
    entry_fee_rate: float | None = None,
) -> float:
    entry_fee = entry_fee_rate if entry_fee_rate is not None else fee_rate
    notional_entry = entry * qty
    notional_exit = exit_px * qty
    return entry_fee * notional_entry + fee_rate * notional_exit
