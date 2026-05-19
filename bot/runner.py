from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from bot.config import Settings, load_settings
from bot.dispatcher import evaluate_dispatch
from bot.exchange import Exchange
from bot.funding.harvester import FundingHarvester
from bot.killswitch import KillSwitch
from bot.pipeline import prepare_df
from bot.risk import build_plan, size_position
from bot.stops import levels
from bot.strategy import Side

log = logging.getLogger(__name__)


class Bot:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or load_settings()
        self.exchange = Exchange(self.settings)
        self.funding = FundingHarvester(self.settings, self.exchange)
        self.killswitch = KillSwitch(self.settings.killswitch, 1_000.0)
        self._last_candle_ts: datetime | None = None
        self._cooldown_until: float = 0
        self._df = None

    def setup_logging(self) -> None:
        from pathlib import Path

        log_dir = Path(__file__).resolve().parent.parent / "logs"
        log_dir.mkdir(exist_ok=True)
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        root.handlers.clear()
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        fh = logging.FileHandler(log_dir / "bot.log", encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(sh)
        root.addHandler(fh)

    def run(self) -> None:
        self.setup_logging()
        log.info(
            "Старт 1112 v3 | %s %s | regime=%s | atr_stops=%s | paper=%s",
            self.settings.symbol,
            self.settings.timeframe,
            self.settings.regime.enabled,
            self.settings.risk_stops.use_atr_stops,
            self.settings.paper_trading,
        )
        self.exchange.connect()

        while True:
            try:
                self._tick()
            except KeyboardInterrupt:
                log.info("Остановка по Ctrl+C")
                break
            except Exception:
                log.exception("Ошибка в цикле")
            time.sleep(self.settings.loop_seconds)

    def _tick(self) -> None:
        raw = self.exchange.fetch_ohlcv()
        df = prepare_df(raw, self.settings)
        self._df = df

        if self.settings.funding.enabled:
            self.funding.tick()

        closed = df.iloc[-2]
        candle_ts = closed["timestamp"].to_pydatetime()
        if self._last_candle_ts and candle_ts <= self._last_candle_ts:
            return
        self._last_candle_ts = candle_ts

        regime = str(closed.get("regime", "?"))
        idx = len(df) - 2
        signal = evaluate_dispatch(df, idx, self.settings)
        log.info(
            "Свеча %s | regime=%s | close=%.2f | %s (%s)",
            candle_ts.strftime("%Y-%m-%d %H:%M UTC"),
            regime,
            signal.price,
            signal.side.value,
            signal.reason,
        )

        if signal.side == Side.FLAT:
            return

        balance = self.exchange.fetch_balance_usdt()
        if not self.killswitch.update(balance if balance > 0 else 1_000, candle_ts):
            log.warning("Kill-switch: торговля остановлена (%s)", self.killswitch.halt_reason)
            return

        if time.time() < self._cooldown_until:
            log.info("Кулдаун активен — пропуск")
            return

        positions = self.exchange.open_positions()
        if len(positions) >= self.settings.max_open_positions:
            log.info("Лимит позиций (%s) — пропуск", self.settings.max_open_positions)
            return

        position_side = signal.side.value
        if self.exchange.has_position_side(position_side):
            log.info("Уже есть позиция %s — пропуск", position_side)
            return

        price = float(closed["close"])
        atr = float(closed["atr"])
        _, sl, tp, sl_pct = levels(signal.side, price, atr, self.settings)

        plan = build_plan(self.settings, signal.side, price)
        if not plan:
            return
        plan.stop_loss = sl
        plan.take_profit = tp

        if not self.settings.paper_trading and balance <= 0:
            log.warning("Баланс USDT = 0")
            return

        qty = size_position(
            self.settings,
            balance if balance > 0 else 10_000,
            price,
            sl_pct,
        )
        self.exchange.execute(plan, qty, price)
        self._cooldown_until = time.time() + self.settings.cooldown_minutes * 60
