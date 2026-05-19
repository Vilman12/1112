from __future__ import annotations

import logging
from typing import Any

import ccxt
import pandas as pd

from bot.config import Settings
from bot.risk import TradePlan

log = logging.getLogger(__name__)


class Exchange:
    def __init__(self, settings: Settings):
        self.settings = settings
        opts: dict[str, Any] = {
            "apiKey": settings.api_key,
            "secret": settings.api_secret,
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        }
        self.client = ccxt.binance(opts)
        self._markets_loaded = False

    def connect(self) -> None:
        if not self.settings.api_key and not self.settings.paper_trading:
            raise ValueError("Задай BINANCE_API_KEY и BINANCE_API_SECRET в .env")
        self.client.load_markets()
        self._markets_loaded = True
        if self.settings.paper_trading:
            log.warning("PAPER_TRADING=true — ордера не отправляются")
            return
        sym = self._market_id()
        try:
            self.client.set_leverage(self.settings.leverage, sym)
        except Exception as e:
            log.warning("Не удалось выставить плечо: %s", e)

    def _market_id(self) -> str:
        return self.settings.symbol

    def fetch_ohlcv(self) -> pd.DataFrame:
        bars = self.client.fetch_ohlcv(
            self.settings.symbol,
            self.settings.timeframe,
            limit=self.settings.candle_limit,
        )
        df = pd.DataFrame(
            bars, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df

    def fetch_balance_usdt(self) -> float:
        bal = self.client.fetch_balance()
        return float(bal.get("total", {}).get("USDT", 0) or 0)

    def open_positions(self) -> list[dict]:
        if self.settings.paper_trading:
            return []
        positions = self.client.fetch_positions([self.settings.symbol])
        out = []
        for p in positions:
            amt = float(p.get("contracts") or p.get("positionAmt") or 0)
            if abs(amt) > 0:
                out.append(p)
        return out

    def has_position_side(self, position_side: str) -> bool:
        for p in self.open_positions():
            side = (p.get("side") or "").upper()
            info = p.get("info") or {}
            ps = (info.get("positionSide") or side).upper()
            if ps == position_side:
                return True
        return False

    def _prec(self, price: float, amount: float) -> tuple[float, float]:
        p = float(self.client.price_to_precision(self.settings.symbol, price))
        a = float(self.client.amount_to_precision(self.settings.symbol, amount))
        return p, a

    def execute(self, plan: TradePlan, quantity: float, entry_price: float) -> None:
        _, quantity = self._prec(entry_price, quantity)
        sl_p, _ = self._prec(plan.stop_loss, quantity)
        tp_p, _ = self._prec(plan.take_profit, quantity)

        if self.settings.paper_trading:
            log.info(
                "[PAPER] %s %s BTC @ ~%s | SL %s | TP %s | %s",
                plan.position_side,
                quantity,
                entry_price,
                sl_p,
                tp_p,
                plan.side,
            )
            return

        params = {"positionSide": plan.position_side}
        self.client.create_order(
            self.settings.symbol, "market", plan.side, quantity, params=params
        )
        close_side = "sell" if plan.side == "buy" else "buy"
        self.client.create_order(
            self.settings.symbol,
            "STOP_MARKET",
            close_side,
            quantity,
            params={"stopPrice": sl_p, "positionSide": plan.position_side},
        )
        self.client.create_order(
            self.settings.symbol,
            "TAKE_PROFIT_MARKET",
            close_side,
            quantity,
            params={"stopPrice": tp_p, "positionSide": plan.position_side},
        )
        log.info(
            "Открыто %s %s BTC | SL %s | TP %s",
            plan.position_side,
            quantity,
            sl_p,
            tp_p,
        )
