"""
Ultra Scalping Bot - Trading Strategies
Best strategies from Freqtrade, Passivbot, Hummingbot & Jesse AI
"""
import pandas as pd
import numpy as np
from typing import Optional, Dict, Tuple
from enum import Enum
from core.indicators import Indicators


class Signal(Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    CLOSE_LONG = "CLOSE_LONG"
    CLOSE_SHORT = "CLOSE_SHORT"
    HOLD = "HOLD"


class TradeSetup:
    def __init__(self, signal: Signal, entry_price: float = 0,
                 stop_loss: float = 0, take_profit: float = 0,
                 confidence: float = 0, strategy_name: str = ""):
        self.signal = signal
        self.entry_price = entry_price
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.confidence = confidence
        self.strategy_name = strategy_name


class BaseStrategy:
    def __init__(self, config):
        self.config = config
        self.name = "base"

    def analyze(self, df: pd.DataFrame) -> TradeSetup:
        raise NotImplementedError


class EmaRsiAtrStrategy(BaseStrategy):
    """
    Triple EMA + RSI + ATR Strategy (Freqtrade inspired)
    Uses EMA crossovers for trend, RSI for momentum, ATR for volatility filter
    """
    def __init__(self, config):
        super().__init__(config)
        self.name = "ema_rsi_atr"

    def analyze(self, df: pd.DataFrame) -> TradeSetup:
        if len(df) < 60:
            return TradeSetup(Signal.HOLD)

        c = self.config.strategy
        sc = self.config.scalping
        last = df.iloc[-1]
        prev = df.iloc[-2]
        price = last['close']

        ema_fast = last['ema_fast']
        ema_medium = last['ema_medium']
        ema_slow = last['ema_slow']
        rsi = last['rsi']
        atr = last['atr']

        if atr / price < c.min_atr_threshold:
            return TradeSetup(Signal.HOLD)

        vol_ok = last['volume'] > last['vol_sma'] * c.min_volume_multiplier

        # LONG: Fast EMA > Medium > Slow + RSI recovering from oversold
        if (ema_fast > ema_medium > ema_slow and
                rsi > c.rsi_scalp_lower and rsi < c.rsi_scalp_upper and
                prev['ema_fast'] <= prev['ema_medium'] and vol_ok):
            sl = price - (atr * c.atr_multiplier)
            tp = price + (atr * c.atr_multiplier * 2)
            confidence = min(0.9, 0.5 + (0.1 if vol_ok else 0) +
                           (0.1 if rsi < 50 else 0) +
                           (0.1 if last['macd_hist'] > 0 else 0))
            return TradeSetup(Signal.LONG, price, sl, tp, confidence, self.name)

        # SHORT: Fast EMA < Medium < Slow + RSI dropping from overbought
        if (ema_fast < ema_medium < ema_slow and
                rsi < c.rsi_scalp_upper and rsi > c.rsi_scalp_lower and
                prev['ema_fast'] >= prev['ema_medium'] and vol_ok):
            sl = price + (atr * c.atr_multiplier)
            tp = price - (atr * c.atr_multiplier * 2)
            confidence = min(0.9, 0.5 + (0.1 if vol_ok else 0) +
                           (0.1 if rsi > 50 else 0) +
                           (0.1 if last['macd_hist'] < 0 else 0))
            return TradeSetup(Signal.SHORT, price, sl, tp, confidence, self.name)

        return TradeSetup(Signal.HOLD)


class MomentumScalperStrategy(BaseStrategy):
    """
    Momentum Scalper (Jesse AI inspired)
    Uses RSI + MACD + Bollinger Bands for quick momentum plays
    """
    def __init__(self, config):
        super().__init__(config)
        self.name = "momentum_scalper"

    def analyze(self, df: pd.DataFrame) -> TradeSetup:
        if len(df) < 30:
            return TradeSetup(Signal.HOLD)

        c = self.config.strategy
        last = df.iloc[-1]
        prev = df.iloc[-2]
        price = last['close']
        atr = last['atr']

        rsi = last['rsi']
        macd_hist = last['macd_hist']
        bb_upper = last['bb_upper']
        bb_lower = last['bb_lower']
        bb_middle = last['bb_middle']

        # LONG: Price bounces off lower BB + RSI oversold + MACD turning up
        if (price <= bb_lower * 1.002 and rsi < c.rsi_oversold + 10 and
                macd_hist > prev['macd_hist']):
            sl = price - (atr * 2)
            tp = bb_middle
            confidence = 0.7 if rsi < c.rsi_oversold else 0.5
            return TradeSetup(Signal.LONG, price, sl, tp, confidence, self.name)

        # SHORT: Price hits upper BB + RSI overbought + MACD turning down
        if (price >= bb_upper * 0.998 and rsi > c.rsi_overbought - 10 and
                macd_hist < prev['macd_hist']):
            sl = price + (atr * 2)
            tp = bb_middle
            confidence = 0.7 if rsi > c.rsi_overbought else 0.5
            return TradeSetup(Signal.SHORT, price, sl, tp, confidence, self.name)

        return TradeSetup(Signal.HOLD)


class GridScalperStrategy(BaseStrategy):
    """
    Grid Scalping Strategy (Passivbot inspired)
    Places grid orders and profits from price oscillations
    """
    def __init__(self, config):
        super().__init__(config)
        self.name = "grid_scalper"
        self.grid_orders = []

    def analyze(self, df: pd.DataFrame) -> TradeSetup:
        if len(df) < 30:
            return TradeSetup(Signal.HOLD)

        last = df.iloc[-1]
        price = last['close']
        atr = last['atr']
        sc = self.config.scalping

        ema = last['ema_medium']
        rsi = last['rsi']

        # Grid LONG: Price below EMA, buy on grid levels
        if price < ema * (1 - sc.grid_spacing_pct):
            levels_below = int((ema - price) / (price * sc.grid_spacing_pct))
            levels_below = min(levels_below, sc.grid_levels)
            if levels_below >= 1 and rsi < 50:
                sl = price - (atr * 3)
                tp = ema
                confidence = min(0.8, 0.4 + (levels_below * 0.15))
                return TradeSetup(Signal.LONG, price, sl, tp, confidence, self.name)

        # Grid SHORT: Price above EMA, sell on grid levels
        if price > ema * (1 + sc.grid_spacing_pct):
            levels_above = int((price - ema) / (price * sc.grid_spacing_pct))
            levels_above = min(levels_above, sc.grid_levels)
            if levels_above >= 1 and rsi > 50:
                sl = price + (atr * 3)
                tp = ema
                confidence = min(0.8, 0.4 + (levels_above * 0.15))
                return TradeSetup(Signal.SHORT, price, sl, tp, confidence, self.name)

        return TradeSetup(Signal.HOLD)


class OrderbookStrategy(BaseStrategy):
    """
    Orderbook Imbalance Strategy (Hummingbot inspired)
    Uses orderbook depth to detect buying/selling pressure
    """
    def __init__(self, config):
        super().__init__(config)
        self.name = "orderbook_imbalance"

    def analyze_with_orderbook(self, df: pd.DataFrame,
                                orderbook: dict) -> TradeSetup:
        if len(df) < 20 or not orderbook:
            return TradeSetup(Signal.HOLD)

        c = self.config.strategy
        last = df.iloc[-1]
        price = last['close']
        atr = last['atr']

        bids = orderbook.get('bids', [])
        asks = orderbook.get('asks', [])
        imbalance = Indicators.orderbook_imbalance(bids, asks, c.orderbook_depth)

        ema_trend = last['ema_fast'] > last['ema_medium']

        # Strong buy pressure + uptrend
        if imbalance > c.imbalance_threshold and ema_trend:
            sl = price - (atr * 1.5)
            tp = price + (atr * 2)
            confidence = min(0.85, 0.5 + abs(imbalance) * 0.5)
            return TradeSetup(Signal.LONG, price, sl, tp, confidence, self.name)

        # Strong sell pressure + downtrend
        if imbalance < -c.imbalance_threshold and not ema_trend:
            sl = price + (atr * 1.5)
            tp = price - (atr * 2)
            confidence = min(0.85, 0.5 + abs(imbalance) * 0.5)
            return TradeSetup(Signal.SHORT, price, sl, tp, confidence, self.name)

        return TradeSetup(Signal.HOLD)

    def analyze(self, df: pd.DataFrame) -> TradeSetup:
        return TradeSetup(Signal.HOLD)


class CombinedStrategy(BaseStrategy):
    """
    Combined Strategy - Voting system from all strategies
    Only trades when multiple strategies agree (high confidence)
    """
    def __init__(self, config):
        super().__init__(config)
        self.name = "combined"
        self.strategies = [
            EmaRsiAtrStrategy(config),
            MomentumScalperStrategy(config),
            GridScalperStrategy(config),
        ]

    def analyze(self, df: pd.DataFrame) -> TradeSetup:
        signals = []
        for strategy in self.strategies:
            setup = strategy.analyze(df)
            if setup.signal != Signal.HOLD:
                signals.append(setup)

        if not signals:
            return TradeSetup(Signal.HOLD)

        long_signals = [s for s in signals if s.signal == Signal.LONG]
        short_signals = [s for s in signals if s.signal == Signal.SHORT]

        # Need at least 2 strategies to agree
        if len(long_signals) >= 2:
            best = max(long_signals, key=lambda x: x.confidence)
            avg_confidence = sum(s.confidence for s in long_signals) / len(long_signals)
            best.confidence = min(0.95, avg_confidence + 0.1)
            best.strategy_name = f"combined({','.join(s.strategy_name for s in long_signals)})"
            return best

        if len(short_signals) >= 2:
            best = max(short_signals, key=lambda x: x.confidence)
            avg_confidence = sum(s.confidence for s in short_signals) / len(short_signals)
            best.confidence = min(0.95, avg_confidence + 0.1)
            best.strategy_name = f"combined({','.join(s.strategy_name for s in short_signals)})"
            return best

        # Single strategy with high confidence
        best_single = max(signals, key=lambda x: x.confidence)
        if best_single.confidence >= 0.75:
            return best_single

        return TradeSetup(Signal.HOLD)


def get_strategy(config) -> BaseStrategy:
    strategies = {
        "ema_rsi_atr": EmaRsiAtrStrategy,
        "momentum_scalper": MomentumScalperStrategy,
        "grid_scalper": GridScalperStrategy,
        "orderbook_imbalance": OrderbookStrategy,
        "combined": CombinedStrategy,
    }
    name = config.strategy.active_strategy
    if name not in strategies:
        raise ValueError(f"Unknown strategy: {name}")
    return strategies[name](config)
