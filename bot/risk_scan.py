from copy import deepcopy

from bot.backtest import run_backtest
from bot.config import ROOT, load_settings
from bot.data_loader import fetch_ohlcv_history
from bot.fees import TAKER_FEE
from bot.indicators import enrich


def main() -> None:
    base = load_settings()
    base.strategy.mode = "classic"
    df = fetch_ohlcv_history(base, 180, ROOT / "data" / "ohlcv_BTC-USDT_15m_180d.csv")
    en = enrich(df, base.strategy)

    print("180d classic | $1000 | taker 0.05%/side\n")
    print(" risk  max_m  lev |  return%    $   DD%  trades")
    for risk in [0.01, 0.015, 0.02, 0.025, 0.03]:
        for max_m, lev in [(0.25, 5), (0.30, 5), (0.40, 5), (0.30, 10)]:
            s = deepcopy(base)
            s.risk_per_trade = risk
            s.max_balance_pct = max_m
            s.leverage = lev
            r = run_backtest(s, df, 1000, TAKER_FEE, df_enriched=en)
            if len(r.trades) < 8:
                continue
            usd = r.final_balance - 1000
            print(
                f" {risk:.2f}  {max_m:.2f}   {lev} | {r.total_return_pct:+7.2f}%  ${usd:+6.0f}  "
                f"{r.max_drawdown_pct:4.1f}%  {len(r.trades)}"
            )


if __name__ == "__main__":
    main()
