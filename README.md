# 1112 — Binance Futures Bot

Трендовый бот для Binance USDT-M Futures (BTC/USDT, 15m).

## Быстрый старт

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python main.py
```

PAPER_TRADING=true по умолчанию — без реальных ордеров.

## Файлы

- .env — ключи API
- config.yaml — плечо, риск, SL/TP, стратегия
- logs/bot.log — лог

## Live

PAPER_TRADING=false, Hedge Mode на Binance, малый risk в config.yaml.

## Backtest

Историю **скачивает с Binance Futures** (публично, ключи не нужны), кэш в `data/`.

```powershell
python -m pip install -r requirements.txt
python backtest.py --days 90
```

Опции:
- `--days 90` — глубина истории
- `--balance 10000` — стартовый депозит
- `--fee 0.0004` — комиссия за сторону
- `--refresh` — перекачать CSV

Результат: отчёт в консоли + `logs/backtest_trades.csv`

Свои свечи: положи CSV в `data/` с колонками timestamp,open,high,low,close,volume (см. кэш после первого запуска).
