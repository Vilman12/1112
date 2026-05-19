from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field

import pandas as pd

from bot.config import ROOT, Settings, load_settings
from bot.data_loader import fetch_ohlcv_history
from bot.exit_rules import apply_breakeven_trail, check_exit
from bot.fees import TAKER_FEE, trade_fees
from bot.dispatcher import evaluate_dispatch
from bot.killswitch import KillSwitch
from bot.pipeline import prepare_df
from bot.risk import size_position
from bot.stops import levels
from bot.strategy import Side


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
    regime: str = ""


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

    @property
    def profit_factor(self) -> float:
        wins = sum(t.pnl for t in self.trades if t.pnl > 0)
        losses = abs(sum(t.pnl for t in self.trades if t.pnl < 0))
        if losses == 0:
            return wins if wins > 0 else 0.0
        return wins / losses


def _cooldown_bars(settings: Settings) -> int:
    if settings.timeframe.endswith("m"):
        return max(1, settings.cooldown_minutes // int(settings.timeframe[:-1]))
    return 1


def _exit_cfg(settings: Settings) -> dict:
    raw = getattr(settings, "exit_rules", None) or {}
    return raw if isinstance(raw, dict) else {}


def _close_trade(
    balance: float,
    side: Side,
    entry: float,
    exit_px: float,
    qty: float,
    fee_rate: float,
    entry_fee_rate: float | None = None,
) -> float:
    gross = (exit_px - entry) * qty if side == Side.LONG else (entry - exit_px) * qty
    fees = trade_fees(entry, exit_px, qty, fee_rate, entry_fee_rate=entry_fee_rate)
    return balance + gross - fees


def run_backtest(
    settings: Settings,
    df: pd.DataFrame,
    initial_balance: float = 1_000.0,
    fee_rate: float = TAKER_FEE,
    entry_fee_rate: float | None = None,
    df_enriched: pd.DataFrame | None = None,
    compound: bool = True,
) -> BacktestResult:
    df = df_enriched if df_enriched is not None else prepare_df(df, settings)
    warmup = max(settings.strategy.ema_slow + 5, 210)
    cooldown_bars = _cooldown_bars(settings)
    exit_cfg = _exit_cfg(settings)
    ks = KillSwitch(settings.killswitch, initial_balance)

    balance = initial_balance
    equity: list[float] = [balance]
    trades: list[Trade] = []
    position: dict | None = None
    cooldown_until = 0
    regime_bars: dict[str, int] = {}

    i = warmup
    while i < len(df):
        row = df.iloc[i]

        if position:
            apply_breakeven_trail(position, row, exit_cfg)
            hit = check_exit(position["side"], row, position["sl"], position["tp"])
            if hit:
                exit_px, reason = hit
                prev = balance
                balance = _close_trade(
                    balance,
                    position["side"],
                    position["entry"],
                    exit_px,
                    position["qty"],
                    fee_rate,
                    entry_fee_rate,
                )
                trades.append(
                    Trade(
                        side=position["side"].value,
                        entry_time=position["entry_time"],
                        exit_time=row["timestamp"],
                        entry=position["entry"],
                        exit=exit_px,
                        qty=position["qty"],
                        pnl=balance - prev,
                        reason=reason,
                        regime=position.get("regime", ""),
                    )
                )
                position = None
                cooldown_until = i + cooldown_bars
                equity.append(balance)
                i += 1
                continue

        reg = str(row.get("regime", "?"))
        regime_bars[reg] = regime_bars.get(reg, 0) + 1

        ts = row["timestamp"]
        if hasattr(ts, "to_pydatetime"):
            ts = ts.to_pydatetime()

        if position is None and i >= cooldown_until and i < len(df) - 1:
            if not ks.update(balance, ts):
                equity.append(balance)
                i += 1
                continue

            signal = evaluate_dispatch(df, i, settings)
            if signal.side != Side.FLAT:
                entry_idx = i + 1
                entry_row = df.iloc[entry_idx]
                entry = float(entry_row["open"])
                atr = float(df.iloc[i]["atr"])
                _, sl, tp, sl_pct = levels(signal.side, entry, atr, settings)
                sizing_balance = balance if compound else initial_balance
                qty = size_position(settings, sizing_balance, entry, sl_pct)
                position = {
                    "side": signal.side,
                    "entry": entry,
                    "entry_time": entry_row["timestamp"],
                    "entry_idx": entry_idx,
                    "qty": qty,
                    "sl": sl,
                    "tp": tp,
                    "regime": reg,
                    "reason": signal.reason,
                }
                i = entry_idx
                continue

        equity.append(balance)
        i += 1

    if position:
        last = df.iloc[-1]
        exit_px = float(last["close"])
        prev = balance
        balance = _close_trade(
            balance,
            position["side"],
            position["entry"],
            exit_px,
            position["qty"],
            fee_rate,
            entry_fee_rate,
        )
        trades.append(
            Trade(
                side=position["side"].value,
                entry_time=position["entry_time"],
                exit_time=last["timestamp"],
                entry=position["entry"],
                exit=exit_px,
                qty=position["qty"],
                pnl=balance - prev,
                reason="eod",
                regime=position.get("regime", ""),
            )
        )
        equity.append(balance)

    result = BacktestResult(
        initial_balance=initial_balance,
        final_balance=balance,
        trades=trades,
        equity_curve=equity,
    )
    result.regime_bars = regime_bars  # type: ignore[attr-defined]
    result.killswitch_halted = ks.halted  # type: ignore[attr-defined]
    result.killswitch_reason = ks.halt_reason  # type: ignore[attr-defined]
    return result


def print_report(
    result: BacktestResult,
    days: int,
    candles: int,
    fee_rate: float = TAKER_FEE,
) -> None:
    print("\n=== Backtest report ===")
    print(f"Period: ~{days} days | candles: {candles}")
    print(f"Fee (taker/side): {fee_rate * 100:.3f}%")
    print(f"Trades: {len(result.trades)}")
    print(f"Win rate: {result.win_rate:.1f}%")
    print(f"Profit factor: {result.profit_factor:.2f}")
    print(f"Initial: ${result.initial_balance:,.2f}")
    print(f"Final:   ${result.final_balance:,.2f}")
    print(f"Return:  {result.total_return_pct:+.2f}%")
    print(f"Max DD:  {result.max_drawdown_pct:.2f}%")
    print("Sizing:  compound on (each trade uses current balance)")
    rb = getattr(result, "regime_bars", None)
    if rb:
        total = sum(rb.values())
        print("Regime time:")
        for k, v in sorted(rb.items(), key=lambda x: -x[1]):
            print(f"  {k}: {v/total*100:.1f}%")
    if getattr(result, "killswitch_halted", False):
        print(f"Kill-switch: HALTED ({getattr(result, 'killswitch_reason', '')})")
    if result.trades:
        by_reg: dict[str, list[float]] = {}
        for t in result.trades:
            by_reg.setdefault(t.regime or "?", []).append(t.pnl)
        print("PnL by entry regime:")
        for k, pnls in sorted(by_reg.items()):
            print(f"  {k}: ${sum(pnls):+.2f} ({len(pnls)} trades)")
        avg = sum(t.pnl for t in result.trades) / len(result.trades)
        fees_sum = sum(
            trade_fees(t.entry, t.exit, t.qty, fee_rate) for t in result.trades
        )
        print(f"Avg PnL/trade: ${avg:+.2f}")
        print(f"Total fees: ${fees_sum:.2f}")
        print("\nLast 5 trades:")
        for t in result.trades[-5:]:
            print(
                f"  {t.side} {t.entry_time} -> {t.exit_time} | "
                f"{t.entry:.0f}->{t.exit:.0f} | ${t.pnl:+.2f} ({t.reason})"
            )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="1112 strategy backtest")
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--balance", type=float, default=1_000.0)
    parser.add_argument("--fee", type=float, default=TAKER_FEE)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--mode", choices=("pullback", "classic", "breakout"), default=None)
    parser.add_argument(
        "--entry-fee",
        type=float,
        default=None,
        help="Комиссия входа (напр. 0.0002 maker). По умолчанию = --fee",
    )
    args = parser.parse_args()

    settings = load_settings()
    if args.mode:
        settings.strategy.mode = args.mode

    cache_path = (
        ROOT
        / "data"
        / f"ohlcv_{settings.symbol.replace('/', '-')}_{settings.timeframe}_{args.days}d.csv"
    )
    if args.refresh and cache_path.exists():
        cache_path.unlink()

    print(
        f"Loading {settings.symbol} {settings.timeframe} ({args.days}d) | "
        f"regime={settings.regime.enabled} | v3 dispatcher"
    )
    df = fetch_ohlcv_history(settings, days=args.days, cache_path=cache_path)
    print(f"Candles: {len(df)} | {df['timestamp'].iloc[0]} .. {df['timestamp'].iloc[-1]}")
    enriched = prepare_df(df, settings)

    entry_fee = args.entry_fee if args.entry_fee is not None else args.fee
    result = run_backtest(
        settings,
        df,
        initial_balance=args.balance,
        fee_rate=args.fee,
        entry_fee_rate=entry_fee if entry_fee != args.fee else None,
        df_enriched=enriched,
    )
    print_report(result, args.days, len(df), args.fee)

    out = ROOT / "logs" / "backtest_trades.csv"
    out.parent.mkdir(exist_ok=True)
    if result.trades:
        pd.DataFrame([t.__dict__ for t in result.trades]).to_csv(out, index=False)
        print(f"\nTrades saved: {out}")


if __name__ == "__main__":
    main()
