# Стратегии и комбинации

## Запуск теста

```powershell
python strategy_suite.py --days 180
```

Результаты: `logs/strategy_suite_180d.csv`  
Депозит $1000, риск 2%, taker 0.05%/сторона.

## Режимы в config.yaml

```yaml
strategy:
  mode: classic          # одиночная
  combo: ""              # или combo: and_cp

# либо через mode:
  mode: combo:classic_htf_trend
```

## Сводка (180 дней)

| Стратегия | Смысл | Лучший результат |
|-----------|--------|------------------|
| **classic** | EMA + MACD + stoch у S/R | **+5.9% (~$59)** |
| **classic_htf** | classic + тренд 1h | +4.4% (~$44), меньше сделок |
| or_cph | classic или pullback+1h | +1% (слабее classic) |
| and_cp / and_cph / and_all | все сигналы совпали | **0 сделок** |
| pullback / vote2 | откат / голосование | минус |
| breakout / or_pb | пробой | **−40…48%** (слив) |

## Вывод

- **Комбинации AND** (classic + pullback) на BTC 15m **никогда не совпадают** — бесполезны.
- **OR с breakout/pullback** увеличивает сделки, но **убивает** депозит.
- Оставляем **classic**; опционально **classic_htf** — чуть меньше прибыль, чуть меньше шума.

## Combo-ключи

| combo | Описание |
|-------|----------|
| `classic_htf_trend` | classic только по тренду 1h |
| `and_cp` | classic И pullback |
| `and_cph` | classic И pullback+1h |
| `and_all` | все три |
| `or_cp` | приоритет: classic → pullback |
| `or_cph` | classic → pullback+1h |
| `or_pb` | pullback+1h → breakout |
| `vote2` | 2 из 3 в одну сторону |
