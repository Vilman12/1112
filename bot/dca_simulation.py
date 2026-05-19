"""
Симуляция: старт $1000 + пополнение $200/мес + торговля v3 по месяцам.
"""
from __future__ import annotations

import argparse
from copy import deepcopy

import pandas as pd

from bot.backtest import run_backtest
from bot.config import ROOT, load_settings
from bot.data_loader import fetch_ohlcv_history
from bot.fees import TAKER_FEE
from bot.pipeline import prepare_df


def simulate(
    df: pd.DataFrame,
    enriched: pd.DataFrame,
    settings,
    initial: float,
    monthly_deposit: float,
) -> pd.DataFrame:
    df = df.copy()
    df["month"] = df["timestamp"].dt.to_period("M")
    months = sorted(df["month"].unique())

    balance = initial
    total_deposited = initial
    rows = []

    for m in months:
        mask = df["month"] == m
        if mask.sum() < 100:
            continue

        balance += monthly_deposit
        total_deposited += monthly_deposit
        start_bal = balance

        month_df = df.loc[mask].reset_index(drop=True)
        month_en = enriched.loc[mask].reset_index(drop=True)

        s = deepcopy(settings)
        r = run_backtest(s, month_df, start_bal, TAKER_FEE, df_enriched=month_en)
        balance = r.final_balance
        trading_pnl = balance - start_bal

        rows.append(
            {
                "month": str(m),
                "deposit": monthly_deposit,
                "start_balance": round(start_bal, 2),
                "trading_pnl": round(trading_pnl, 2),
                "end_balance": round(balance, 2),
                "trades": len(r.trades),
            }
        )

    return pd.DataFrame(rows)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--initial", type=float, default=1_000.0)
    p.add_argument("--monthly", type=float, default=200.0)
    args = p.parse_args()

    settings = load_settings()
    cache = ROOT / "data" / f"ohlcv_BTC-USDT_15m_{args.days}d.csv"
    df = fetch_ohlcv_history(settings, days=args.days, cache_path=cache)
    enriched = prepare_df(df, settings)

    table = simulate(df, enriched, settings, args.initial, args.monthly)
    out = ROOT / "logs" / "dca_simulation.csv"
    table.to_csv(out, index=False)

    total_in = args.initial + args.monthly * len(table)
    final = table["end_balance"].iloc[-1] if len(table) else args.initial
    trading_total = table["trading_pnl"].sum() if len(table) else 0
    pure_dca = total_in

    print(f"\n=== DCA + bot v3 ({args.days}d backtest) ===")
    print(f"Start:              ${args.initial:,.0f}")
    print(f"Monthly deposit:    ${args.monthly:,.0f}/mo x {len(table)} months")
    print(f"Total deposited:    ${total_in:,.2f}")
    print(f"Final balance:      ${final:,.2f}")
    print(f"Trading PnL sum:    ${trading_total:,.2f}")
    net = final - total_in
    print(f"Net vs deposits:    ${net:,.2f} ({(final/total_in-1)*100:+.1f}% on contributed)")
    print(f"DCA only (no trade): ${pure_dca:,.2f} | bot edge: ${final - pure_dca:+,.2f}")
    print(f"\n{table.to_string(index=False)}")
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
