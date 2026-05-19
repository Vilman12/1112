from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class StrategyConfig:
    mode: str = "pullback"
    ema_fast: int = 50
    ema_slow: int = 200
    ema_sep_pct: float = 0.0012
    pullback_pct: float = 0.004
    adx_min: float = 22.0
    min_atr_pct: float = 0.0025
    max_atr_pct: float = 0.02
    rsi_period: int = 14
    rsi_long_min: float = 38.0
    rsi_long_max: float = 52.0
    rsi_short_min: float = 48.0
    rsi_short_max: float = 62.0
    volume_factor: float = 0.85
    require_bullish_candle: bool = True
    stoch_oversold: float = 30
    stoch_overbought: float = 70
    support_buffer_pct: float = 0.002
    use_htf_filter: bool = True
    macd_rising_bars: int = 2
    long_only: bool = False
    breakout_lookback: int = 20
    combo: str = ""


@dataclass
class RegimeConfig:
    enabled: bool = True
    trend_adx_min: float = 22.0
    range_adx_max: float = 18.0
    trend_ema_sep_pct: float = 0.001
    chaos_atr_pct_min: float = 0.0015
    chaos_atr_pct_max: float = 0.035
    min_daily_trend_slope: float = 0.001


@dataclass
class RiskStopsConfig:
    use_atr_stops: bool = True
    sl_atr_mult: float = 1.5
    tp_atr_mult: float = 2.5
    min_sl_pct: float = 0.006
    max_sl_pct: float = 0.022
    min_tp_pct: float = 0.008
    max_tp_pct: float = 0.04


@dataclass
class KillSwitchConfig:
    enabled: bool = True
    max_weekly_loss_pct: float = 5.0
    max_drawdown_pct: float = 15.0


@dataclass
class FundingConfig:
    enabled: bool = False
    min_rate_pct: float = 0.03
    allocation_pct: float = 0.4


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
    exit_rules: dict
    regime: RegimeConfig
    risk_stops: RiskStopsConfig
    killswitch: KillSwitchConfig
    funding: FundingConfig


def _strategy_from_yaml(strat: dict) -> StrategyConfig:
    return StrategyConfig(
        mode=str(strat.get("mode", "pullback")),
        ema_fast=int(strat.get("ema_fast", 50)),
        ema_slow=int(strat.get("ema_slow", 200)),
        ema_sep_pct=float(strat.get("ema_sep_pct", 0.0012)),
        pullback_pct=float(strat.get("pullback_pct", 0.004)),
        adx_min=float(strat.get("adx_min", 22)),
        min_atr_pct=float(strat.get("min_atr_pct", 0.0025)),
        max_atr_pct=float(strat.get("max_atr_pct", 0.02)),
        rsi_period=int(strat.get("rsi_period", 14)),
        rsi_long_min=float(strat.get("rsi_long_min", 38)),
        rsi_long_max=float(strat.get("rsi_long_max", 52)),
        rsi_short_min=float(strat.get("rsi_short_min", 48)),
        rsi_short_max=float(strat.get("rsi_short_max", 62)),
        volume_factor=float(strat.get("volume_factor", 0.85)),
        require_bullish_candle=bool(strat.get("require_bullish_candle", True)),
        stoch_oversold=float(strat.get("stoch_oversold", 30)),
        stoch_overbought=float(strat.get("stoch_overbought", 70)),
        support_buffer_pct=float(strat.get("support_buffer_pct", 0.002)),
        use_htf_filter=bool(strat.get("use_htf_filter", True)),
        macd_rising_bars=int(strat.get("macd_rising_bars", 2)),
        long_only=bool(strat.get("long_only", False)),
        breakout_lookback=int(strat.get("breakout_lookback", 20)),
        combo=str(strat.get("combo", "") or ""),
    )


def _regime_from_yaml(d: dict) -> RegimeConfig:
    return RegimeConfig(
        enabled=bool(d.get("enabled", True)),
        trend_adx_min=float(d.get("trend_adx_min", 22)),
        range_adx_max=float(d.get("range_adx_max", 18)),
        trend_ema_sep_pct=float(d.get("trend_ema_sep_pct", 0.001)),
        chaos_atr_pct_min=float(d.get("chaos_atr_pct_min", 0.0015)),
        chaos_atr_pct_max=float(d.get("chaos_atr_pct_max", 0.035)),
        min_daily_trend_slope=float(d.get("min_daily_trend_slope", 0.001)),
    )


def _risk_stops_from_yaml(d: dict) -> RiskStopsConfig:
    return RiskStopsConfig(
        use_atr_stops=bool(d.get("use_atr_stops", True)),
        sl_atr_mult=float(d.get("sl_atr_mult", 1.5)),
        tp_atr_mult=float(d.get("tp_atr_mult", 2.5)),
        min_sl_pct=float(d.get("min_sl_pct", 0.006)),
        max_sl_pct=float(d.get("max_sl_pct", 0.022)),
        min_tp_pct=float(d.get("min_tp_pct", 0.008)),
        max_tp_pct=float(d.get("max_tp_pct", 0.04)),
    )


def _killswitch_from_yaml(d: dict) -> KillSwitchConfig:
    return KillSwitchConfig(
        enabled=bool(d.get("enabled", True)),
        max_weekly_loss_pct=float(d.get("max_weekly_loss_pct", 5)),
        max_drawdown_pct=float(d.get("max_drawdown_pct", 15)),
    )


def _funding_from_yaml(d: dict) -> FundingConfig:
    return FundingConfig(
        enabled=bool(d.get("enabled", False)),
        min_rate_pct=float(d.get("min_rate_pct", 0.03)),
        allocation_pct=float(d.get("allocation_pct", 0.4)),
    )


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
        strategy=_strategy_from_yaml(strat),
        loop_seconds=int(raw.get("loop_seconds", 60)),
        api_key=os.getenv("BINANCE_API_KEY", "").strip(),
        api_secret=os.getenv("BINANCE_API_SECRET", "").strip(),
        paper_trading=os.getenv("PAPER_TRADING", "true").lower() in ("1", "true", "yes"),
        exit_rules=dict(raw.get("exit") or {}),
        regime=_regime_from_yaml(raw.get("regime") or {}),
        risk_stops=_risk_stops_from_yaml(raw.get("risk_stops") or {}),
        killswitch=_killswitch_from_yaml(raw.get("killswitch") or {}),
        funding=_funding_from_yaml(raw.get("funding") or {}),
    )
