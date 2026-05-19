"""Сравнение режимов / таймфреймов / комиссий на $1000."""
from __future__ import annotations

from copy import deepcopy

from bot.backtest import run_backtest
from bot.config import ROOT, load_settings
from bot.data_loader import fetch_ohlcv_history
from bot.fees import MAKER_FEE, TAKER_FEE
from bot.indicators import enrich


def _run(s, df, enriched, balance, exit_fee, entry_fee=None):
    r = run_backtest(
        s, df, balance, exit_fee, entry_fee_rate=entry_fee, df_enriched=enriched
    )
    n = len(r.trades)
    if n < 5:
        return None
    return {
        "ret": round(r.total_return_pct, 2),
        "wr": round(r.win_rate, 1),
        "n": n,
        "pf": round(r.profit_factor, 2),
        "dd": round(r.max_drawdown_pct, 2),
    }


def main() -> None:
    balance = 1_000.0
    days = 180
    base = load_settings()

    configs = []
    for tf in ("15m", "1h"):
        for mode in ("pullback", "breakout", "classic"):
            for long_only in (False, True):
                if mode == "classic" and long_only:
                    continue
                for sl, tp in [(0.008, 0.014), (0.009, 0.015), (0.01, 0.018)]:
                    configs.append(
                        {
                            "tf": tf,
                            "mode": mode,
                            "long_only": long_only,
                            "sl": sl,
                            "tp": tp,
                            "adx": 22,
                            "cd": 90,
                        }
                    )

    rows = []
    for c in configs:
        s = deepcopy(base)
        s.timeframe = c["tf"]
        s.strategy.mode = c["mode"]
        s.strategy.long_only = c["long_only"]
        s.strategy.adx_min = float(c["adx"])
        s.stop_loss_pct = c["sl"]
        s.take_profit_pct = c["tp"]
        s.cooldown_minutes = c["cd"]
        cache = (
            ROOT
            / "data"
            / f"ohlcv_{s.symbol.replace('/', '-')}_{c['tf']}_{days}d.csv"
        )
        df = fetch_ohlcv_history(s, days=days, cache_path=cache)
        enriched = enrich(df, s.strategy)

        for label, ef, ent in [
            ("taker", TAKER_FEE, None),
            ("maker_entry", TAKER_FEE, MAKER_FEE),
        ]:
            row = _run(s, df, enriched, balance, ef, ent)
            if row:
                rows.append({**c, "fees": label, **row})

    rows.sort(key=lambda x: x["ret"], reverse=True)
    print(f"Runs: {len(rows)}\n=== TOP 20 ===")
    for r in rows[:20]:
        print(r)
    pos = [r for r in rows if r["ret"] > 0]
    print(f"\nProfitable: {len(pos)} / {len(rows)}")


if __name__ == "__main__":
    main()
