from __future__ import annotations

from copy import deepcopy
from itertools import product

from bot.backtest import run_backtest
from bot.config import ROOT, load_settings
from bot.data_loader import fetch_ohlcv_history
from bot.fees import TAKER_FEE
from bot.indicators import enrich


def scan(days: int, balance: float = 1_000.0) -> None:
    base = load_settings()
    base.strategy.mode = "classic"
    base.timeframe = "15m"
    cache = ROOT / "data" / f"ohlcv_BTC-USDT_15m_{days}d.csv"
    df = fetch_ohlcv_history(base, days=days, cache_path=cache)
    enriched = enrich(df, base.strategy)

    rows = []
    for sl, tp, cd, adx, risk in product(
        [0.008, 0.009, 0.01],
        [0.012, 0.014, 0.015, 0.016, 0.018],
        [60, 90, 120],
        [20, 22],
        [0.01, 0.012],
    ):
        if tp < sl * 1.2:
            continue
        s = deepcopy(base)
        s.stop_loss_pct = sl
        s.take_profit_pct = tp
        s.cooldown_minutes = cd
        s.risk_per_trade = risk
        s.strategy.adx_min = float(adx)
        r = run_backtest(s, df, balance, TAKER_FEE, df_enriched=enriched)
        n = len(r.trades)
        if n < 8:
            continue
        rows.append(
            {
                "ret": round(r.total_return_pct, 2),
                "wr": round(r.win_rate, 1),
                "n": n,
                "pf": round(r.profit_factor, 2),
                "dd": round(r.max_drawdown_pct, 2),
                "sl": sl,
                "tp": tp,
                "cd": cd,
                "adx": adx,
                "risk": risk,
            }
        )

    rows.sort(key=lambda x: x["ret"], reverse=True)
    print(f"\n=== {days}d | top 10 (taker fees) ===")
    for row in rows[:10]:
        print(row)
    pos = sum(1 for r in rows if r["ret"] > 0)
    print(f"Profitable: {pos}/{len(rows)}")


if __name__ == "__main__":
    for d in (90, 180, 365):
        scan(d)
