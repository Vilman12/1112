from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from bot.config import ROOT, Settings, load_settings
from bot.data_loader import fetch_ohlcv_history
from bot.indicators import enrich
from bot.risk import size_position
from bot.strategy import Side, evaluate_at


@dataclass
class Trade:
    side: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry: float
    exit: float
    qty: float
    pnl: float
    reason: str


@dataclass
class BacktestResult:
    initial_balance: float
    final_balance: float
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)

    @property
    def total_return_pct(self) -> float:
        if self.initial_balance <= 0:
            return 0.0
        return (self.final_balance / self.initial_balance - 1) * 100

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        return sum(1 for t in self.trades if t.pnl > 0) / len(self.trades) * 100

    @property
    def max_drawdown_pct(self) -> float:
        if not self.equity_curve:
            return 0.0
        peak = self.equity_curve[0]
        max_dd = 0.0
        for v in self.equity_curve:
            peak = max(peak, v)
            if peak > 0:
                max_dd = max(max_dd, (peak - v) / peak)
        return max_dd * 100


def _cooldown_bars(settings: Settings) -> int:
    if settings.timeframe.endswith("m"):
        return max(1, settings.cooldown_minutes // int(settings.timeframe[:-1]))
    return 1


def _bar_exit(side: Side, row: pd.Series, sl: float, tp: float) -> tuple[float, str] | None:
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


def _close_trade(
    balance: float,
    side: Side,
    entry: float,
    exit_px: float,
    qty: float,
    fee_rate: float,
) -> float:
    gross = (exit_px - entry) * qty if side == Side.LONG else (entry - exit_px) * qty
    fees = fee_rate * (entry + exit_px) * qty
    return balance + gross - fees


def run_backtest(
    settings: Settings,
    df: pd.DataFrame,
    initial_balance: float = 10_000.0,
    fee_rate: float = 0.0004,
) -> BacktestResult:
    df = enrich(df, settings.strategy)
    warmup = max(settings.strategy.ema_slow + 5, 210)
    cooldown_bars = _cooldown_bars(settings)

    balance = initial_balance
    equity: list[float] = [balance]
    trades: list[Trade] = []
    position: dict | None = None
    cooldown_until = 0

    i = warmup
    while i < len(df):
        row = df.iloc[i]

        if position:
            hit = _bar_exit(position["side"], row, position["sl"], position["tp"])
            if hit:
                exit_px, reason = hit
                balance = _close_trade(
                    balance,
                    position["side"],
                    position["entry"],
                    exit_px,
                    position["qty"],
                    fee_rate,
                )
                trades.append(
                    Trade(
                        side=position["side"].value,
                        entry_time=position["entry_time"],
                        exit_time=row["timestamp"],
                        entry=position["entry"],
                        exit=exit_px,
                        qty=position["qty"],
                        pnl=trades[-1].pnl if False else balance - equity[-1],
                        reason=reason,
                    )
                )
                trades[-1] = Trade(
                    side=position["side"].value,
                    entry_time=position["entry_time"],
                    exit_time=row["timestamp"],
                    entry=position["entry"],
                    exit=exit_px,
                    qty=position["qty"],
                    pnl=balance - equity[-1],
                    reason=reason,
                )
                position = None
                cooldown_until = i + cooldown_bars
                equity.append(balance)
                i += 1
                continue

        if position is None and i >= cooldown_until and i < len(df) - 1:
            signal = evaluate_at(df, i, settings.strategy)
            if signal.side != Side.FLAT:
                entry_idx = i + 1
                entry = float(df.iloc[entry_idx]["open"])
                qty = size_position(settings, balance, entry, settings.stop_loss_pct)
                if signal.side == Side.LONG:
                    sl = entry * (1 - settings.stop_loss_pct)
                    tp = entry * (1 + settings.take_profit_pct)
                else:
                    sl = entry * (1 + settings.stop_loss_pct)
                    tp = entry * (1 - settings.take_profit_pct)
                position = {
                    "side": signal.side,
                    "entry": entry,
                    "entry_time": df.iloc[entry_idx]["timestamp"],
                    "entry_idx": entry_idx,
                    "qty": qty,
                    "sl": sl,
                    "tp": tp,
                }
                i = entry_idx
                continue

        equity.append(balance)
        i += 1

    if position:
        last = df.iloc[-1]
        exit_px = float(last["close"])
        prev_bal = balance
        balance = _close_trade(
            balance, position["side"], position["entry"], exit_px, position["qty"], fee_rate
        )
        trades.append(
            Trade(
                side=position["side"].value,
                entry_time=position["entry_time"],
                exit_time=last["timestamp"],
                entry=position["entry"],
                exit=exit_px,
                qty=position["qty"],
                pnl=balance - prev_bal,
                reason="eod",
            )
        )
        equity.append(balance)

    return BacktestResult(
        initial_balance=initial_balance,
        final_balance=balance,
        trades=trades,
        equity_curve=equity,
    )


def print_report(result: BacktestResult, days: int, candles: int) -> None:
    print("\n=== Backtest report ===")
    print(f"Period: ~{days} days | candles: {candles}")
    print(f"Trades: {len(result.trades)}")
    print(f"Win rate: {result.win_rate:.1f}%")
    print(f"Initial: ${result.initial_balance:,.2f}")
    print(f"Final:   ${result.final_balance:,.2f}")
    print(f"Return:  {result.total_return_pct:+.2f}%")
    print(f"Max DD:  {result.max_drawdown_pct:.2f}%")
    if result.trades:
        avg = sum(t.pnl for t in result.trades) / len(result.trades)
        print(f"Avg PnL/trade: ${avg:+.2f}")
        print("\nLast 5 trades:")
        for t in result.trades[-5:]:
            print(
                f"  {t.side} {t.entry_time} -> {t.exit_time} | "
                f"{t.entry:.0f}->{t.exit:.0f} | ${t.pnl:+.2f} ({t.reason})"
            )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="1112 strategy backtest")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--balance", type=float, default=10_000.0)
    parser.add_argument("--fee", type=float, default=0.0004)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    settings = load_settings()
    cache_path = (
        ROOT
        / "data"
        / f"ohlcv_{settings.symbol.replace('/', '-')}_{settings.timeframe}_{args.days}d.csv"
    )
    if args.refresh and cache_path.exists():
        cache_path.unlink()

    print(f"Loading {settings.symbol} {settings.timeframe} ({args.days}d)...")
    df = fetch_ohlcv_history(settings, days=args.days, cache_path=cache_path)
    print(f"Candles: {len(df)} | {df['timestamp'].iloc[0]} .. {df['timestamp'].iloc[-1]}")

    result = run_backtest(settings, df, initial_balance=args.balance, fee_rate=args.fee)
    print_report(result, args.days, len(df))

    out = ROOT / "logs" / "backtest_trades.csv"
    out.parent.mkdir(exist_ok=True)
    if result.trades:
        pd.DataFrame([t.__dict__ for t in result.trades]).to_csv(out, index=False)
        print(f"\nTrades saved: {out}")


if __name__ == "__main__":
    main()
