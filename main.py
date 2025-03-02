import ccxt
import time
import pandas as pd
import threading

# API-ключи Binance
API_KEY = "7VpePCmDtLbFrtZE8uFRdewBwQ0WK1PXWWzsstw"
API_SECRET = "Ndqy99B8D28JJsd8aZybbZv18rTPQffgIZm"

# Подключение к Binance
exchange = ccxt.binance({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'options': {'defaultType': 'future'},  # Торговля фьючерсами
    'rateLimit': 1200,
    'enableRateLimit': True
})

# Торговые параметры
symbol = "BTC/USDT"
timeframe = "15m"
risk_per_trade = 0.03  # 3% от баланса (увеличенный риск)
leverage = 20  # Плечо
stop_loss_pct = 0.005  # 0.5% (уменьшенный стоп-лосс)
take_profit_pct = 0.01  # 1% (уменьшенный тейк-профит)
min_trade_size = 0.002  # Минимальный объем сделки BTC

# Установка плеча
try:
    exchange.fapiPrivate_post_leverage({
        'symbol': symbol.replace('/', ''),
        'leverage': leverage
    })
except Exception as e:
    print(f"⚠️ Ошибка установки плеча: {e}")


def fetch_data():
    """Получение рыночных данных"""
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe, limit=200)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"⚠️ Ошибка при получении данных: {e}")
        return None


def calculate_indicators(df):
    """Добавление индикаторов и определение уровней поддержки/сопротивления"""
    df['EMA50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['EMA200'] = df['close'].ewm(span=200, adjust=False).mean()
    df['MACD'] = df['close'].ewm(span=12, adjust=False).mean() - df['close'].ewm(span=26, adjust=False).mean()
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['%K'] = ((df['close'] - df['low'].rolling(14).min()) / (
                df['high'].rolling(14).max() - df['low'].rolling(14).min())) * 100
    df['%D'] = df['%K'].rolling(3).mean()

    # Определение уровней поддержки и сопротивления
    df['support'] = df['low'].rolling(window=20).min()
    df['resistance'] = df['high'].rolling(window=20).max()

    return df.dropna()


def place_order(side, quantity, stop_loss, take_profit, position_side):
    """Размещение рыночного ордера с ограничением на максимальное количество сделок"""
    positions = exchange.fetch_positions()
    open_positions = [p for p in positions if p['symbol'] == symbol and float(p['positionAmt']) != 0]
    if len(open_positions) >= 3:
        print("⚠️ Достигнут лимит открытых сделок! Новая сделка не будет открыта.")
        return
    """Размещение рыночного ордера"""
    try:
        quantity = max(quantity, min_trade_size)  # Учитываем минимальный объем сделки
        order = exchange.create_market_order(symbol, side, quantity, params={"positionSide": position_side})

        # Установка стоп-лосса и тейк-профита
        stop_loss_order = exchange.create_order(
            symbol, 'STOP_MARKET', side='sell' if side == 'buy' else 'buy', amount=quantity,
            params={"stopPrice": stop_loss, "positionSide": position_side}
        )

        take_profit_order = exchange.create_order(
            symbol, 'TAKE_PROFIT_MARKET', side='sell' if side == 'buy' else 'buy', amount=quantity,
            params={"stopPrice": take_profit, "positionSide": position_side}
        )

        print(f"✅ Открыт {side} на {quantity} BTC (SL: {stop_loss}, TP: {take_profit})")
    except Exception as e:
        print(f"❌ Ошибка при открытии ордера: {e}")


def trading_logic():
    """Основная торговая логика"""
    while True:
        df = fetch_data()
        if df is None:
            time.sleep(10)
            continue
        df = calculate_indicators(df)
        latest = df.iloc[-1]
        trend = "BUY" if latest['EMA50'] > latest['EMA200'] else "SELL"

        try:
            balance = exchange.fetch_balance()['total']['USDT']
            risk_amount = balance * risk_per_trade
            position_size = max(min((risk_amount * leverage) / latest['close'], balance * 0.3 / latest['close']),
                                min_trade_size)
            stop_loss = latest['close'] * (1 - stop_loss_pct) if trend == "BUY" else latest['close'] * (
                        1 + stop_loss_pct)
            take_profit = latest['close'] * (1 + take_profit_pct) if trend == "BUY" else latest['close'] * (
                        1 - take_profit_pct)
            position_side = "LONG" if trend == "BUY" else "SHORT"
            place_order(trend.lower(), position_size, stop_loss, take_profit, position_side)
        except Exception as e:
            print(f"⚠️ Ошибка в расчёте торговых параметров: {e}")

        time.sleep(900)


if __name__ == "__main__":
    trading_thread = threading.Thread(target=trading_logic)
    trading_thread.start()
