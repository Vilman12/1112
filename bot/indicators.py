from __future__ import annotations

import pandas as pd

from bot.config import StrategyConfig


def enrich(df: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    out = df.copy()
    out["ema_fast"] = out["close"].ewm(span=cfg.ema_fast, adjust=False).mean()
    out["ema_slow"] = out["close"].ewm(span=cfg.ema_slow, adjust=False).mean()
    out["macd"] = out["close"].ewm(span=12, adjust=False).mean() - out["close"].ewm(
        span=26, adjust=False
    ).mean()
    out["macd_signal"] = out["macd"].ewm(span=9, adjust=False).mean()
    low14 = out["low"].rolling(14).min()
    high14 = out["high"].rolling(14).max()
    out["stoch_k"] = ((out["close"] - low14) / (high14 - low14).replace(0, pd.NA)) * 100
    out["stoch_d"] = out["stoch_k"].rolling(3).mean()
    out["support"] = out["low"].rolling(20).min()
    out["resistance"] = out["high"].rolling(20).max()
    return out.dropna()
