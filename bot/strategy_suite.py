"""
Тест одиночных стратегий и комбинаций на истории.
Запуск: python -m bot.strategy_suite --days 180
"""
from __future__ import annotations

import argparse
from copy import deepcopy

import pandas as pd

from bot.backtest import run_backtest
from bot.config import ROOT, StrategyConfig, load_settings
from bot.data_loader import fetch_ohlcv_history
from bot.fees import TAKER_FEE
from bot.indicators import enrich

# Одиночные + комбинации
SUITE: list[tuple[str, str, str]] = [
    ("classic", "classic", "EMA+MACD+stoch у S/R"),
    ("pullback", "pullback", "Откат к EMA50"),
    ("pullback_htf", "combo:pullback_htf", "Откат + фильтр 1h"),
    ("breakout", "combo:breakout", "Пробой диапазона"),
    ("classic_htf", "combo:classic_htf_trend", "Classic + тренд 1h"),
    ("and_cp", "combo:and_cp", "Classic И pullback"),
    ("and_cph", "combo:and_cph", "Classic И pullback+1h"),
    ("and_pb", "combo:and_pb", "Pullback+1h И breakout"),
    ("and_all", "combo:and_all", "Все три согласны"),
    ("or_cp", "combo:or_cp", "Classic ИЛИ pullback (без конфликта)"),
    ("or_cph", "combo:or_cph", "Classic ИЛИ pullback+1h"),
    ("or_pb", "combo:or_pb", "Pullback+1h ИЛИ breakout"),
    ("vote2", "combo:vote2", "2 из 3 за одно направление"),
]

SL_TP_PRESETS = [
    (0.009, 0.016, "sl09_tp16"),
    (0.008, 0.014, "sl08_tp14"),
    (0.009, 0.018, "sl09_tp18"),
]


def _apply_strategy(s, name: str, mode_key: str) -> None:
    if mode_key.startswith("combo:"):
        s.strategy.combo = mode_key.split(":", 1)[1]
        s.strategy.mode = "pullback"
    else:
        s.strategy.combo = ""
        s.strategy.mode = mode_key


def run_suite(days: int = 180, balance: float = 1_000.0) -> pd.DataFrame:
    base = load_settings()
    base.strategy.use_htf_filter = True
    cache = ROOT / "data" / f"ohlcv_{base.symbol.replace('/', '-')}_15m_{days}d.csv"
    print(f"Loading {days}d...")
    df = fetch_ohlcv_history(base, days=days, cache_path=cache)
    enriched = enrich(df, base.strategy)

    rows: list[dict] = []
    total = len(SUITE) * len(SL_TP_PRESETS)
    n = 0
    for label, mode_key, desc in SUITE:
        for sl, tp, sltp_tag in SL_TP_PRESETS:
            n += 1
            s = deepcopy(base)
            _apply_strategy(s, label, mode_key)
            s.stop_loss_pct = sl
            s.take_profit_pct = tp
            r = run_backtest(s, df, balance, TAKER_FEE, df_enriched=enriched)
            cnt = len(r.trades)
            row = {
                "strategy": label,
                "desc": desc,
                "sl_tp": sltp_tag,
                "return_pct": round(r.total_return_pct, 2),
                "usd": round(r.final_balance - balance, 2),
                "trades": cnt,
                "win_rate": round(r.win_rate, 1) if cnt else 0,
                "pf": round(r.profit_factor, 2) if cnt else 0,
                "max_dd": round(r.max_drawdown_pct, 2),
            }
            rows.append(row)
            if n % 10 == 0 or row["return_pct"] > 3:
                print(
                    f"  [{n}/{total}] {label:14} {sltp_tag} "
                    f"ret={row['return_pct']:+.2f}% n={cnt}"
                )

    out = pd.DataFrame(rows).sort_values(["return_pct", "pf"], ascending=False)
    path = ROOT / "logs" / f"strategy_suite_{days}d.csv"
    path.parent.mkdir(exist_ok=True)
    out.to_csv(path, index=False)
    print(f"\nSaved: {path}")
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=180)
    p.add_argument("--balance", type=float, default=1_000.0)
    args = p.parse_args()

    table = run_suite(args.days, args.balance)
    pos = table[table["return_pct"] > 0]
    print(f"\n=== TOP 12 (profit only: {len(pos)}/{len(table)}) ===")
    print(
        table.head(12)[
            ["strategy", "sl_tp", "return_pct", "usd", "trades", "win_rate", "pf", "max_dd"]
        ].to_string(index=False)
    )
    print("\n=== WORST 5 ===")
    print(
        table.tail(5)[
            ["strategy", "sl_tp", "return_pct", "usd", "trades", "win_rate", "pf"]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
