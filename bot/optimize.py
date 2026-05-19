from __future__ import annotations

import itertools
from copy import deepcopy

import pandas as pd

from bot.backtest import run_backtest
from bot.config import ROOT, Settings, load_settings
from bot.data_loader import fetch_ohlcv_history
from bot.fees import TAKER_FEE
from bot.indicators import enrich


def _score(result, min_trades: int = 8) -> float:
    n = len(result.trades)
    if n < min_trades:
        return -999.0
    if result.total_return_pct <= 0:
        return result.total_return_pct - result.max_drawdown_pct * 0.5
    return (
        result.total_return_pct
        + 0.25 * result.profit_factor
        - 0.35 * result.max_drawdown_pct
        + min(n, 25) * 0.05
    )


def optimize(
    df: pd.DataFrame,
    enriched: pd.DataFrame,
    base: Settings,
    balance: float = 1_000.0,
    fee: float = TAKER_FEE,
) -> tuple[dict, pd.DataFrame]:
    rows = []
    best_score = -9999.0
    best_params: dict = {}

    grid = {
        "sl": [0.008, 0.009],
        "tp": [0.009, 0.010, 0.011],
        "adx": [18, 20],
        "pullback": [0.004, 0.005],
        "risk": [0.01, 0.012],
        "be": [0, 0.004],
        "trail": [(0, 0), (0.0055, 0.0025)],
    }
    keys = list(grid.keys())
    combos = list(itertools.product(*grid.values()))
    total = len(combos)
    print(f"Combinations: {total}")

    for n, vals in enumerate(combos, 1):
        params = dict(zip(keys, vals))
        sl, tp = params["sl"], params["tp"]
        if tp < sl * 0.85:
            continue

        s = deepcopy(base)
        s.stop_loss_pct = sl
        s.take_profit_pct = tp
        s.risk_per_trade = params["risk"]
        s.strategy.adx_min = float(params["adx"])
        s.strategy.pullback_pct = params["pullback"]
        tt, to = params["trail"]
        s.exit_rules = {
            "breakeven_trigger_pct": params["be"],
            "breakeven_lock_pct": 0.001,
            "trail_trigger_pct": tt,
            "trail_offset_pct": to,
        }

        r = run_backtest(s, df, balance, fee, df_enriched=enriched)
        sc = _score(r)
        row = {
            "score": round(sc, 3),
            "return_pct": round(r.total_return_pct, 2),
            "win_rate": round(r.win_rate, 1),
            "trades": len(r.trades),
            "max_dd": round(r.max_drawdown_pct, 2),
            "pf": round(r.profit_factor, 2),
            **params,
            "trail_t": tt,
            "trail_o": to,
        }
        rows.append(row)
        if sc > best_score:
            best_score = sc
            best_params = row
            print(f"  [{n}/{total}] new best: +{row['return_pct']}% WR {row['win_rate']}% trades {row['trades']}")

        if n % 20 == 0:
            print(f"  [{n}/{total}] ...")

    return best_params, pd.DataFrame(rows).sort_values("score", ascending=False)


def main() -> None:
    days = 180
    balance = 1_000.0
    settings = load_settings()
    cache = (
        ROOT
        / "data"
        / f"ohlcv_{settings.symbol.replace('/', '-')}_{settings.timeframe}_{days}d.csv"
    )
    print(f"Loading {days}d...")
    df = fetch_ohlcv_history(settings, days=days, cache_path=cache)
    enriched = enrich(df, settings.strategy)
    print(f"Candles: {len(df)} | fee {TAKER_FEE*100:.3f}%/side | deposit ${balance}")

    best, table = optimize(df, enriched, settings, balance=balance, fee=TAKER_FEE)
    out = ROOT / "logs" / "optimize_results.csv"
    table.to_csv(out, index=False)

    print("\n=== TOP 8 ===")
    print(table.head(8).to_string(index=False))
    print("\n=== BEST (apply to config.yaml) ===")
    for k, v in best.items():
        print(f"  {k}: {v}")
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
