# 1112 v3 — архитектура

## Слои

```
OHLCV → pipeline (indicators + regime) → dispatcher → signal
                                              ↓
                                    risk (ATR stops) → exchange
```

## Режимы (`bot/regime.py`)

| Режим | Действие |
|-------|----------|
| **trend** | classic (EMA + MACD + stoch у S/R) |
| **range** | mean reversion (RSI у support/resistance) |
| **chaos** | не торгуем (высокая/низкая волатильность, нет тренда) |

## Риск

- `risk_stops.use_atr_stops: true` — SL = 1.5×ATR, TP = 2.5×ATR (с clamp)
- Размер позиции от % риска и текущего баланса (compound)

## Kill-switch

- Недельный убыток ≥ 5% → пауза до следующей недели
- Просадка от пика ≥ 15% → стоп до конца сессии

## Funding (paper)

`funding.enabled: true` — логирует возможности при |rate| ≥ 0.03%

## Команды

```powershell
python main.py
python backtest.py --days 365 --balance 1000
python walk_forward.py --days 365 --train-days 120 --test-days 60
python strategy_suite.py --days 180
```

## Файлы

- `bot/dispatcher.py` — маршрутизация по режиму
- `bot/range_strategy.py` — range
- `bot/stops.py` — ATR SL/TP
- `bot/funding/harvester.py` — funding paper
- `bot/walk_forward.py` — OOS окна
