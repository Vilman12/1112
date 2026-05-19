"""Подготовка OHLCV: индикаторы + режим."""
from __future__ import annotations

import pandas as pd

from bot.config import Settings
from bot.indicators import enrich
from bot.regime import attach_regime


def prepare_df(df: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    df = enrich(df, settings.strategy)
    df = attach_regime(df, settings.regime)
    return df
