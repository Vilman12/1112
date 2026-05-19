"""Подбор classic под цель $200-300 за 90-120 дней. Сравнение compound vs fixed."""
from __future__ import annotations

from copy import deepcopy
from itertools import product

from bot.backtest import run_backtest
from bot.config import ROOT, load_settings
from bot.data_loader import fetch_ohlcv_history
from bot.fees import TAKER_FEE
from bot.indicators import enrich


def main() -> None:
    balance = 1_000.0
    target_lo, target_hi = 200, 300
    base = load_settings()
    base.strategy.mode = "classic"
    base.strategy.combo = ""

    for days in (90, 120):
        cache = ROOT / "data" / f"ohlcv_BTC-USDT_15m_{days}d.csv"
        df = fetch_ohlcv_history(base, days=days, cache_path=cache)
        en = enrich(df, base.strategy)
        print(f"\n{'='*60}\n{days}d | goal ${target_lo}-${target_hi} | classic\n")

        # compound vs fixed baseline
        s = deepcopy(base)
        r_c = run_backtest(s, df, balance, TAKER_FEE, df_enriched=en, compound=True)
        r_f = run_backtest(s, df, balance, TAKER_FEE, df_enriched=en, compound=False)
        print(
            f"Baseline risk={s.risk_per_trade:.0%} max_m={s.max_balance_pct} lev={s.leverage}"
        )
        print(
            f"  COMPOUND:  ${r_c.final_balance - balance:+.0f} ({r_c.total_return_pct:+.1f}%) "
            f"n={len(r_c.trades)} dd={r_c.max_drawdown_pct:.1f}%"
        )
        print(
            f"  FIXED $1k: ${r_f.final_balance - balance:+.0f} ({r_f.total_return_pct:+.1f}%) "
            f"n={len(r_f.trades)}"
        )

        hits = []
        for risk, max_m, lev, cd in product(
            [0.02, 0.03, 0.04, 0.05, 0.06],
            [0.30, 0.40, 0.50],
            [5, 10],
            [45, 60, 90],
        ):
            s = deepcopy(base)
            s.risk_per_trade = risk
            s.max_balance_pct = max_m
            s.leverage = lev
            s.cooldown_minutes = cd
            r = run_backtest(s, df, balance, TAKER_FEE, df_enriched=en, compound=True)
            usd = r.final_balance - balance
            if len(r.trades) < 4:
                continue
            if target_lo <= usd <= target_hi * 1.15:
                hits.append(
                    {
                        "usd": round(usd, 0),
                        "ret": round(r.total_return_pct, 1),
                        "dd": round(r.max_drawdown_pct, 1),
                        "n": len(r.trades),
                        "risk": risk,
                        "max_m": max_m,
                        "lev": lev,
                        "cd": cd,
                    }
                )

        hits.sort(key=lambda x: x["dd"])
        print(f"\nConfigs in ${target_lo}-${target_hi} band: {len(hits)}")
        for h in hits[:8]:
            print(
                f"  ${h['usd']:+.0f} ({h['ret']:+.0f}%) dd={h['dd']}% "
                f"n={h['n']} risk={h['risk']:.0%} margin={h['max_m']:.0%} "
                f"lev={h['lev']} cd={h['cd']}m"
            )

        # best return with dd < 25%
        best = None
        for risk, max_m, lev, cd in product(
            [0.02, 0.03, 0.04, 0.05, 0.06, 0.07],
            [0.30, 0.40, 0.50, 0.60],
            [5, 10, 15],
            [45, 60],
        ):
            s = deepcopy(base)
            s.risk_per_trade, s.max_balance_pct, s.leverage = risk, max_m, lev
            s.cooldown_minutes = cd
            r = run_backtest(s, df, balance, TAKER_FEE, df_enriched=en, compound=True)
            if len(r.trades) < 4 or r.max_drawdown_pct > 25:
                continue
            usd = r.final_balance - balance
            if best is None or usd > best["usd"]:
                best = {
                    "usd": usd,
                    "ret": r.total_return_pct,
                    "dd": r.max_drawdown_pct,
                    "n": len(r.trades),
                    "risk": risk,
                    "max_m": max_m,
                    "lev": lev,
                    "cd": cd,
                }
        if best:
            print(
                f"\nMax profit (DD<25%): ${best['usd']:+.0f} ({best['ret']:+.1f}%) "
                f"dd={best['dd']}% risk={best['risk']:.0%} margin={best['max_m']:.0%} "
                f"lev={best['lev']} cd={best['cd']}m n={best['n']}"
            )


if __name__ == "__main__":
    main()
