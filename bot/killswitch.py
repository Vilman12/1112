"""Стоп торговли при просадке / недельном убытке."""
from __future__ import annotations

from datetime import datetime, timezone

from bot.config import KillSwitchConfig


class KillSwitch:
    def __init__(self, cfg: KillSwitchConfig, initial_balance: float):
        self.cfg = cfg
        self.peak = initial_balance
        self.week_start_balance = initial_balance
        self._week_id: int | None = None
        self.halted = False
        self.halt_reason = ""

    def _week_key(self, ts: datetime) -> int:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        iso = ts.isocalendar()
        return iso[0] * 100 + iso[1]

    def update(self, balance: float, ts: datetime) -> bool:
        """True = торговля разрешена."""
        if not self.cfg.enabled:
            return True

        wk = self._week_key(ts)
        if self._week_id != wk:
            if self.halted and self.halt_reason.startswith("weekly"):
                self.halted = False
                self.halt_reason = ""
            self._week_id = wk
            self.week_start_balance = balance

        self.peak = max(self.peak, balance)

        dd_pct = ((self.peak - balance) / self.peak * 100) if self.peak > 0 else 0
        if dd_pct >= self.cfg.max_drawdown_pct:
            self.halted = True
            self.halt_reason = f"drawdown_{dd_pct:.1f}pct"
            return False

        if self.week_start_balance > 0:
            week_loss = (self.week_start_balance - balance) / self.week_start_balance * 100
            if week_loss >= self.cfg.max_weekly_loss_pct:
                self.halted = True
                self.halt_reason = f"weekly_loss_{week_loss:.1f}pct"
                return False

        return not self.halted
