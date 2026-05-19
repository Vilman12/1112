"""Walk-forward: train window → test window, сдвиг по времени."""
from __future__ import annotations

import argparse
from copy import deepcopy

import pandas as pd

from bot.backtest import print_report, run_backtest
from bot.config import ROOT, load_settings
from bot.data_loader import fetch_ohlcv_history
from bot.fees import TAKER_FEE
from bot.pipeline import prepare_df


def walk_forward(
    df: pd.DataFrame,
    enriched_full: pd.DataFrame,
    settings,
    train_days: int,
    test_days: int,
    balance: float,
) -> pd.DataFrame:
    tf_min = 15
    bars_per_day = 24 * 60 // tf_min
    train_bars = train_days * bars_per_day
    test_bars = test_days * bars_per_day
    rows = []

    start = train_bars + 210
    while start + test_bars < len(df):
        test_start = start
        test_end = start + test_bars
        test_df = df.iloc[test_start:test_end].copy().reset_index(drop=True)
        test_en = enriched_full.iloc[test_start:test_end].copy().reset_index(drop=True)

        s = deepcopy(settings)
        r = run_backtest(s, test_df, balance, TAKER_FEE, df_enriched=test_en)
        t0 = df.iloc[test_start]["timestamp"]
        t1 = df.iloc[test_end - 1]["timestamp"]
        rows.append(
            {
                "test_from": str(t0)[:10],
                "test_to": str(t1)[:10],
                "return_pct": round(r.total_return_pct, 2),
                "trades": len(r.trades),
                "win_rate": round(r.win_rate, 1),
                "max_dd": round(r.max_drawdown_pct, 2),
            }
        )
        start += test_bars

    return pd.DataFrame(rows)


def main() -> None:
    p = argparse.ArgumentParser(description="Walk-forward validation")
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--train-days", type=int, default=120)
    p.add_argument("--test-days", type=int, default=60)
    p.add_argument("--balance", type=float, default=1_000.0)
    args = p.parse_args()

    settings = load_settings()
    cache = ROOT / "data" / f"ohlcv_BTC-USDT_15m_{args.days}d.csv"
    df = fetch_ohlcv_history(settings, days=args.days, cache_path=cache)
    enriched = prepare_df(df, settings)

    print(
        f"Walk-forward | train={args.train_days}d test={args.test_days}d | "
        f"regime={settings.regime.enabled} atr_stops={settings.risk_stops.use_atr_stops}"
    )

    wf = walk_forward(df, enriched, settings, args.train_days, args.test_days, args.balance)
    out = ROOT / "logs" / "walk_forward.csv"
    wf.to_csv(out, index=False)

    if wf.empty:
        print("Недостаточно данных для окон.")
        return

    pos = (wf["return_pct"] > 0).sum()
    print(f"\nOOS windows: {len(wf)} | profitable: {pos} ({pos/len(wf)*100:.0f}%)")
    print(f"Avg return/window: {wf['return_pct'].mean():.2f}%")
    print(f"Sum return (non-compound): {wf['return_pct'].sum():.2f}%")
    print(wf.to_string(index=False))
    print(f"\nSaved: {out}")

    r = run_backtest(settings, df, args.balance, TAKER_FEE, df_enriched=enriched)
    print("\n--- Full period backtest ---")
    print_report(r, args.days, len(df), TAKER_FEE)


if __name__ == "__main__":
    main()
