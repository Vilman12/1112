from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class StrategyConfig:
    ema_fast: int = 50
    ema_slow: int = 200
    stoch_oversold: float = 30
    stoch_overbought: float = 70
    support_buffer_pct: float = 0.002


@dataclass
class Settings:
    symbol: str
    timeframe: str
    candle_limit: int
    leverage: int
    risk_per_trade: float
    max_balance_pct: float
    min_trade_btc: float
    stop_loss_pct: float
    take_profit_pct: float
    max_open_positions: int
    cooldown_minutes: int
    strategy: StrategyConfig
    loop_seconds: int
    api_key: str
    api_secret: str
    paper_trading: bool


def load_settings(config_path: Path | None = None) -> Settings:
    load_dotenv(ROOT / ".env")
    path = config_path or ROOT / "config.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    strat = raw.get("strategy") or {}
    return Settings(
        symbol=raw["symbol"],
        timeframe=raw["timeframe"],
        candle_limit=int(raw.get("candle_limit", 250)),
        leverage=int(raw["leverage"]),
        risk_per_trade=float(raw["risk_per_trade"]),
        max_balance_pct=float(raw.get("max_balance_pct", 0.25)),
        min_trade_btc=float(raw["min_trade_btc"]),
        stop_loss_pct=float(raw["stop_loss_pct"]),
        take_profit_pct=float(raw["take_profit_pct"]),
        max_open_positions=int(raw["max_open_positions"]),
        cooldown_minutes=int(raw["cooldown_minutes"]),
        strategy=StrategyConfig(
            ema_fast=int(strat.get("ema_fast", 50)),
            ema_slow=int(strat.get("ema_slow", 200)),
            stoch_oversold=float(strat.get("stoch_oversold", 30)),
            stoch_overbought=float(strat.get("stoch_overbought", 70)),
            support_buffer_pct=float(strat.get("support_buffer_pct", 0.002)),
        ),
        loop_seconds=int(raw.get("loop_seconds", 60)),
        api_key=os.getenv("BINANCE_API_KEY", "").strip(),
        api_secret=os.getenv("BINANCE_API_SECRET", "").strip(),
        paper_trading=os.getenv("PAPER_TRADING", "true").lower() in ("1", "true", "yes"),
    )
