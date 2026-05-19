from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from bot.config import Settings, load_settings
from bot.exchange import Exchange
from bot.indicators import enrich
from bot.risk import build_plan, size_position
from bot.strategy import Side, evaluate

log = logging.getLogger(__name__)


class Bot:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or load_settings()
        self.exchange = Exchange(self.settings)
        self._last_candle_ts: datetime | None = None
        self._cooldown_until: float = 0

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
            "Старт 1112 | %s %s | leverage %sx | paper=%s",
            self.settings.symbol,
            self.settings.timeframe,
            self.settings.leverage,
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
        df = self.exchange.fetch_ohlcv()
        df = enrich(df, self.settings.strategy)

        closed = df.iloc[-2]
        candle_ts = closed["timestamp"].to_pydatetime()
        if self._last_candle_ts and candle_ts <= self._last_candle_ts:
            return
        self._last_candle_ts = candle_ts

        signal = evaluate(df, self.settings.strategy)
        log.info(
            "Свеча %s | close=%.2f | сигнал=%s (%s)",
            candle_ts.strftime("%Y-%m-%d %H:%M UTC"),
            signal.price,
            signal.side.value,
            signal.reason,
        )

        if signal.side == Side.FLAT:
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

        plan = build_plan(self.settings, signal.side, signal.price)
        if not plan:
            return

        balance = self.exchange.fetch_balance_usdt()
        if not self.settings.paper_trading and balance <= 0:
            log.warning("Баланс USDT = 0")
            return

        qty = size_position(
            self.settings,
            balance if balance > 0 else 10_000,
            signal.price,
            self.settings.stop_loss_pct,
        )
        self.exchange.execute(plan, qty, signal.price)
        self._cooldown_until = time.time() + self.settings.cooldown_minutes * 60
