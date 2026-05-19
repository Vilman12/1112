"""Быстрый перебор пресетов без полной сетки optimize.py."""
from __future__ import annotations

from copy import deepcopy

from bot.backtest import run_backtest
from bot.config import ROOT, load_settings
from bot.data_loader import fetch_ohlcv_history
from bot.fees import TAKER_FEE
from bot.indicators import enrich


def main() -> None:
    days = 180
    balance = 1_000.0
    base = load_settings()
    cache = (
        ROOT
        / "data"
        / f"ohlcv_{base.symbol.replace('/', '-')}_{base.timeframe}_{days}d.csv"
    )
    df = fetch_ohlcv_history(base, days=days, cache_path=cache)
    enriched = enrich(df, base.strategy)

    presets = []
    for sl, tp in [(0.007, 0.012), (0.008, 0.012), (0.008, 0.014), (0.009, 0.012), (0.009, 0.016)]:
        for adx in [20, 22]:
            for cd in [60, 90]:
                for be, tt, to in [
                    (0, 0, 0),
                    (0.005, 0.007, 0.003),
                    (0.006, 0.009, 0.004),
                ]:
                    for htf in [True]:
                        presets.append(
                            {
                                "sl": sl,
                                "tp": tp,
                                "adx": adx,
                                "cd": cd,
                                "be": be,
                                "tt": tt,
                                "to": to,
                                "htf": htf,
                            }
                        )

    rows = []
    for p in presets:
        s = deepcopy(base)
        s.stop_loss_pct = p["sl"]
        s.take_profit_pct = p["tp"]
        s.cooldown_minutes = p["cd"]
        s.strategy.adx_min = float(p["adx"])
        s.strategy.use_htf_filter = p["htf"]
        s.exit_rules = {
            "breakeven_trigger_pct": p["be"],
            "breakeven_lock_pct": 0.001,
            "trail_trigger_pct": p["tt"],
            "trail_offset_pct": p["to"],
        }
        r = run_backtest(s, df, balance, TAKER_FEE, df_enriched=enriched)
        n = len(r.trades)
        if n < 6:
            continue
        rows.append(
            {
                "ret": round(r.total_return_pct, 2),
                "wr": round(r.win_rate, 1),
                "n": n,
                "pf": round(r.profit_factor, 2),
                "dd": round(r.max_drawdown_pct, 2),
                "fees": round(sum(t.qty * t.entry for t in r.trades) * TAKER_FEE * 2, 2),
                **p,
            }
        )

    rows.sort(key=lambda x: x["ret"], reverse=True)
    print(f"Tested {len(presets)} presets, {len(rows)} with >=6 trades\n")
    print("=== TOP 15 by return ===")
    for row in rows[:15]:
        print(row)
    pos = [r for r in rows if r["ret"] > 0]
    print(f"\nProfitable configs: {len(pos)} / {len(rows)}")


if __name__ == "__main__":
    main()
