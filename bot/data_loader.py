from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import ccxt
import pandas as pd

from bot.config import ROOT, Settings


def _timeframe_ms(tf: str) -> int:
    unit = tf[-1]
    n = int(tf[:-1])
    if unit == "m":
        return n * 60_000
    if unit == "h":
        return n * 3_600_000
    if unit == "d":
        return n * 86_400_000
    raise ValueError(f"Unsupported timeframe: {tf}")


def fetch_ohlcv_history(
    settings: Settings,
    days: int = 90,
    cache_path: Path | None = None,
) -> pd.DataFrame:
    """История с Binance Futures (публично, без API-ключей). Кэш в CSV."""
    cache = cache_path or ROOT / "data" / f"ohlcv_{settings.symbol.replace('/', '-')}_{settings.timeframe}_{days}d.csv"
    cache.parent.mkdir(parents=True, exist_ok=True)

    if cache.exists():
        df = pd.read_csv(cache)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        return df

    exchange = ccxt.binance(
        {"enableRateLimit": True, "options": {"defaultType": "future"}}
    )
    tf_ms = _timeframe_ms(settings.timeframe)
    since = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
    all_bars: list = []

    while since < exchange.milliseconds():
        batch = exchange.fetch_ohlcv(
            settings.symbol, settings.timeframe, since=since, limit=1000
        )
        if not batch:
            break
        all_bars.extend(batch)
        since = batch[-1][0] + tf_ms
        time.sleep(exchange.rateLimit / 1000)

    df = pd.DataFrame(
        all_bars, columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
    df.to_csv(cache, index=False)
    return df
