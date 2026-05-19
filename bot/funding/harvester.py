"""Paper-модуль: сбор ставки финансирования (funding rate)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from bot.config import FundingConfig, Settings

log = logging.getLogger(__name__)


@dataclass
class FundingOpportunity:
    symbol: str
    rate_pct: float
    side: str
    ts: datetime


class FundingHarvester:
    def __init__(self, settings: Settings, exchange):
        self.settings = settings
        self.cfg: FundingConfig = settings.funding
        self.exchange = exchange
        self.paper_pnl = 0.0
        self.events: list[FundingOpportunity] = []

    def fetch_rate_pct(self) -> float | None:
        """Текущая ставка funding в % за период (8h на Binance)."""
        try:
            info = self.exchange.client.fetch_funding_rate(self.settings.symbol)
            rate = info.get("fundingRate") or info.get("funding_rate")
            if rate is None:
                return None
            return float(rate) * 100
        except Exception as e:
            log.warning("funding rate: %s", e)
            return None

    def tick(self) -> None:
        if not self.cfg.enabled:
            return

        rate = self.fetch_rate_pct()
        if rate is None:
            return

        sym = self.settings.symbol
        now = datetime.now(timezone.utc)

        if rate >= self.cfg.min_rate_pct:
            opp = FundingOpportunity(sym, rate, "short_perp_hedge", now)
            self.events.append(opp)
            est = self.cfg.allocation_pct * 1000 * (rate / 100)
            self.paper_pnl += est
            log.info(
                "[FUNDING PAPER] %s rate=%.4f%% → шорт perp + хедж | est +$%.2f",
                sym,
                rate,
                est,
            )
        elif rate <= -self.cfg.min_rate_pct:
            opp = FundingOpportunity(sym, rate, "long_perp_hedge", now)
            self.events.append(opp)
            est = self.cfg.allocation_pct * 1000 * (abs(rate) / 100)
            self.paper_pnl += est
            log.info(
                "[FUNDING PAPER] %s rate=%.4f%% → лонг perp + хедж | est +$%.2f",
                sym,
                rate,
                est,
            )
