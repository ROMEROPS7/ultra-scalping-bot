"""
Ultra Scalping Bot - Exchange Connector (CCXT)
"""
import ccxt
import pandas as pd
import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ExchangeConnector:
    def __init__(self, config):
        self.config = config
        self.exchange = None

    def connect(self):
        ec = self.config.exchange
        exchange_class = getattr(ccxt, ec.name)
        params = {'apiKey': ec.api_key, 'secret': ec.api_secret,
                  'enableRateLimit': True, 'options': {'defaultType': 'future'}}
        if ec.testnet:
            params['sandbox'] = True
        self.exchange = exchange_class(params)
        logger.info(f"Connected to {ec.name}")
        return self

    def fetch_ohlcv(self, symbol, timeframe='1m', limit=200):
        ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df

    def fetch_orderbook(self, symbol, limit=10):
        return self.exchange.fetch_order_book(symbol, limit)

    def fetch_balance(self):
        return self.exchange.fetch_balance()

    def get_position(self, symbol):
        try:
            positions = self.exchange.fetch_positions([symbol])
            for pos in positions:
                if pos['symbol'] == symbol and float(pos.get('contracts', 0)) > 0:
                    return pos
        except Exception as e:
            logger.error(f"Error: {e}")
        return None

    def set_leverage(self, symbol, leverage):
        try:
            self.exchange.set_leverage(leverage, symbol)
        except Exception as e:
            logger.warning(f"Leverage error: {e}")

    def create_market_order(self, symbol, side, amount, params=None):
        return self.exchange.create_order(symbol, 'market', side, amount, None, params or {})

    def create_limit_order(self, symbol, side, amount, price, params=None):
        return self.exchange.create_order(symbol, 'limit', side, amount, price, params or {})

    def create_stop_loss(self, symbol, side, amount, stop_price):
        params = {'stopPrice': stop_price, 'reduceOnly': True}
        return self.exchange.create_order(symbol, 'stop_market', side, amount, None, params)

    def cancel_all_orders(self, symbol):
        self.exchange.cancel_all_orders(symbol)

    def calculate_position_size(self, symbol, capital, risk_pct, entry, stop_loss):
        risk_amount = capital * risk_pct
        price_risk = abs(entry - stop_loss)
        if price_risk == 0:
            return 0
        size = risk_amount / price_risk
        min_amt = self.exchange.market(symbol).get('limits',{}).get('amount',{}).get('min', 0.001)
        return max(size, min_amt)


class PaperExchange:
    def __init__(self, config):
        self.config = config
        self.balance = config.scalping.initial_capital
        self.positions = {}
        self.trade_history = []
        self.order_id = 0

    def fetch_balance(self):
        return {'USDT': {'free': self.balance, 'total': self.balance}}

    def get_position(self, symbol):
        return self.positions.get(symbol)

    def set_leverage(self, symbol, leverage):
        pass

    def create_market_order(self, symbol, side, amount, params=None):
        self.order_id += 1
        price = params.get('price', 0) if params else 0
        self.positions[symbol] = {'side': 'long' if side == 'buy' else 'short',
                                   'amount': amount, 'entry_price': price}
        return {'id': str(self.order_id), 'symbol': symbol, 'side': side}

    def close_position(self, symbol, current_price):
        pos = self.positions.pop(symbol, None)
        if not pos:
            return 0
        entry = pos['entry_price']
        amount = pos['amount']
        pnl = (current_price - entry) * amount if pos['side'] == 'long' else (entry - current_price) * amount
        fee = abs(current_price * amount) * self.config.backtest.commission_pct * 2
        net_pnl = pnl - fee
        self.balance += net_pnl
        self.trade_history.append({'symbol': symbol, 'side': pos['side'],
                                    'entry': entry, 'exit': current_price, 'pnl': net_pnl})
        return net_pnl

    def calculate_position_size(self, symbol, capital, risk_pct, entry, stop_loss):
        price_risk = abs(entry - stop_loss)
        return (capital * risk_pct) / price_risk if price_risk > 0 else 0
