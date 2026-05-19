# 1112 - Binance Futures Bot

Bot for Binance USDT-M Futures (BTC/USDT, 15m).

## Quick start

```powershell
pip install -r requirements.txt
copy .env.example .env
python main.py
```

PAPER_TRADING=true for paper mode.

## Backtest ($1000, taker 0.05% per side)

| Period | Trades | WR | PnL |
|--------|--------|-----|-----|
| 90d | 8 | 50% | +$5 |
| 180d | 16 | 50% | +$10 |
| 365d | 39 | 33% | -$16 |

```powershell
python backtest.py --days 180 --balance 1000
```

Strategy: classic. See docs/PROFIT_PLAN.ru.md
