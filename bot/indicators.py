from __future__ import annotations

import numpy as np
import pandas as pd

from bot.config import StrategyConfig


def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


def _adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    up = high.diff()
    down = -low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    atr = _atr(df, period)
    plus_di = 100 * pd.Series(plus_dm, index=df.index).rolling(period).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=df.index).rolling(period).mean() / atr
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
    return dx.rolling(period).mean()


def enrich(df: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    out = df.copy()
    out["ema_fast"] = out["close"].ewm(span=cfg.ema_fast, adjust=False).mean()
    out["ema_slow"] = out["close"].ewm(span=cfg.ema_slow, adjust=False).mean()
    out["macd"] = out["close"].ewm(span=12, adjust=False).mean() - out["close"].ewm(
        span=26, adjust=False
    ).mean()
    out["macd_signal"] = out["macd"].ewm(span=9, adjust=False).mean()
    out["macd_hist"] = out["macd"] - out["macd_signal"]
    low14 = out["low"].rolling(14).min()
    high14 = out["high"].rolling(14).max()
    out["stoch_k"] = ((out["close"] - low14) / (high14 - low14).replace(0, np.nan)) * 100
    out["stoch_d"] = out["stoch_k"].rolling(3).mean()
    out["support"] = out["low"].rolling(20).min()
    out["resistance"] = out["high"].rolling(20).max()
    out["rsi"] = _rsi(out["close"], cfg.rsi_period)
    out["atr"] = _atr(out)
    out["atr_pct"] = out["atr"] / out["close"]
    out["adx"] = _adx(out)
    out["vol_sma"] = out["volume"].rolling(20).mean()
    return out.dropna()
