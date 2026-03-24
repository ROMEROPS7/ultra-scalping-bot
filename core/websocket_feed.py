"""
Ultra Scalping Bot - WebSocket Real-Time Data Feed
Conexion en tiempo real via WebSocket para datos de mercado ultra-rapidos.
Soporta: Binance, Bybit, OKX con reconexion automatica.
"""

import asyncio
import json
import time
import logging
from typing import Dict, List, Callable, Optional, Any
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime

try:
    import websockets
except ImportError:
    websockets = None

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

@dataclass
class OrderBookLevel:
    """Nivel individual del orderbook."""
    price: float
    quantity: float


@dataclass
class OrderBook:
    """Orderbook completo con funcionalidad avanzada."""
    symbol: str
    bids: List[OrderBookLevel] = field(default_factory=list)
    asks: List[OrderBookLevel] = field(default_factory=list)
    timestamp: float = 0.0
    update_id: int = 0

    @property
    def best_bid(self) -> float:
        return self.bids[0].price if self.bids else 0.0

    @property
    def best_ask(self) -> float:
        return self.asks[0].price if self.asks else 0.0

    @property
    def spread(self) -> float:
        if self.best_bid and self.best_ask:
            return self.best_ask - self.best_bid
        return 0.0

    @property
    def spread_pct(self) -> float:
        if self.best_bid and self.best_ask:
            mid = (self.best_bid + self.best_ask) / 2
            return (self.spread / mid) * 100
        return 0.0

    @property
    def mid_price(self) -> float:
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2
        return 0.0

    def imbalance(self, levels: int = 5) -> float:
        """Calcula el desequilibrio del orderbook."""
        bid_vol = sum(b.quantity for b in self.bids[:levels])
        ask_vol = sum(a.quantity for a in self.asks[:levels])
        total = bid_vol + ask_vol
        if total == 0:
            return 0.0
        return (bid_vol - ask_vol) / total

    def weighted_mid_price(self, levels: int = 5) -> float:
        """Precio medio ponderado por volumen."""
        bid_vol = sum(b.quantity for b in self.bids[:levels])
        ask_vol = sum(a.quantity for a in self.asks[:levels])
        total = bid_vol + ask_vol
        if total == 0:
            return self.mid_price
        return (self.best_bid * ask_vol + self.best_ask * bid_vol) / total

    def depth_at_pct(self, pct: float = 0.1) -> Dict[str, float]:
        """Volumen acumulado dentro de un porcentaje del mid price."""
        mid = self.mid_price
        if mid == 0:
            return {"bid_depth": 0, "ask_depth": 0}
        bid_depth = sum(b.quantity for b in self.bids if b.price >= mid * (1 - pct / 100))
        ask_depth = sum(a.quantity for a in self.asks if a.price <= mid * (1 + pct / 100))
        return {"bid_depth": bid_depth, "ask_depth": ask_depth}

@dataclass
class Trade:
    """Trade individual del mercado."""
    symbol: str
    price: float
    quantity: float
    side: str  # "buy" or "sell"
    timestamp: float
    trade_id: str = ""


@dataclass
class Ticker:
    """Ticker en tiempo real."""
    symbol: str
    last_price: float
    bid: float
    ask: float
    volume_24h: float
    high_24h: float
    low_24h: float
    change_pct_24h: float
    timestamp: float


class TradeAggregator:
    """Agrega trades en tiempo real para analisis de flujo."""

    def __init__(self, window_seconds: int = 60, max_trades: int = 10000):
        self.window_seconds = window_seconds
        self.max_trades = max_trades
        self.trades: deque = deque(maxlen=max_trades)
        self.buy_volume = 0.0
        self.sell_volume = 0.0
        self.trade_count = 0

    def add_trade(self, trade: Trade):
        """Agrega un trade y actualiza metricas."""
        self.trades.append(trade)
        self.trade_count += 1
        if trade.side == "buy":
            self.buy_volume += trade.price * trade.quantity
        else:
            self.sell_volume += trade.price * trade.quantity
        self._cleanup_old_trades()

    def _cleanup_old_trades(self):
        """Elimina trades fuera de la ventana de tiempo."""
        cutoff = time.time() - self.window_seconds
        while self.trades and self.trades[0].timestamp < cutoff:
            old = self.trades.popleft()
            if old.side == "buy":
                self.buy_volume -= old.price * old.quantity
            else:
                self.sell_volume -= old.price * old.quantity

    @property
    def net_flow(self) -> float:
        """Flujo neto (positivo = mas compras)."""
        return self.buy_volume - self.sell_volume

    @property
    def flow_ratio(self) -> float:
        """Ratio compra/venta."""
        total = self.buy_volume + self.sell_volume
        if total == 0:
            return 0.5
        return self.buy_volume / total

    @property
    def vwap(self) -> float:
        """VWAP de trades recientes."""
        if not self.trades:
            return 0.0
        total_vol = sum(t.quantity for t in self.trades)
        if total_vol == 0:
            return 0.0
        return sum(t.price * t.quantity for t in self.trades) / total_vol

    def large_trades(self, threshold_multiplier: float = 3.0) -> List[Trade]:
        """Detecta trades grandes (ballenas)."""
        if not self.trades:
            return []
        avg_size = np.mean([t.quantity for t in self.trades])
        return [t for t in self.trades if t.quantity > avg_size * threshold_multiplier]

class BinanceWebSocketFeed:
    """WebSocket feed para Binance con reconexion automatica."""

    ENDPOINTS = {
        "spot": "wss://stream.binance.com:9443/ws",
        "futures": "wss://fstream.binance.com/ws",
    }

    def __init__(self, market_type: str = "futures"):
        if websockets is None:
            raise ImportError("pip install websockets")
        self.base_url = self.ENDPOINTS.get(market_type, self.ENDPOINTS["futures"])
        self.market_type = market_type
        self._ws = None
        self._running = False
        self._reconnect_delay = 1
        self._max_reconnect_delay = 60
        self._callbacks: Dict[str, List[Callable]] = {
            "orderbook": [],
            "trade": [],
            "ticker": [],
            "kline": [],
        }
        self._orderbooks: Dict[str, OrderBook] = {}
        self._aggregators: Dict[str, TradeAggregator] = {}
        self._subscriptions: List[str] = []
        self._message_count = 0
        self._last_message_time = 0
        self._latencies: deque = deque(maxlen=100)

    def on(self, event: str, callback: Callable):
        """Registra callback para un evento."""
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def subscribe_orderbook(self, symbol: str, depth: int = 20):
        """Suscribirse al orderbook de un simbolo."""
        s = symbol.lower().replace("/", "")
        stream = f"{s}@depth{depth}@100ms"
        self._subscriptions.append(stream)
        self._orderbooks[symbol] = OrderBook(symbol=symbol)

    def subscribe_trades(self, symbol: str):
        """Suscribirse a trades de un simbolo."""
        s = symbol.lower().replace("/", "")
        stream = f"{s}@aggTrade"
        self._subscriptions.append(stream)
        self._aggregators[symbol] = TradeAggregator()

    def subscribe_ticker(self, symbol: str):
        """Suscribirse al ticker de un simbolo."""
        s = symbol.lower().replace("/", "")
        stream = f"{s}@ticker"
        self._subscriptions.append(stream)

    def subscribe_kline(self, symbol: str, interval: str = "1m"):
        """Suscribirse a klines (velas) de un simbolo."""
        s = symbol.lower().replace("/", "")
        stream = f"{s}@kline_{interval}"
        self._subscriptions.append(stream)

    def get_orderbook(self, symbol: str) -> Optional[OrderBook]:
        """Obtiene el orderbook actual de un simbolo."""
        return self._orderbooks.get(symbol)

    def get_aggregator(self, symbol: str) -> Optional[TradeAggregator]:
        """Obtiene el agregador de trades de un simbolo."""
        return self._aggregators.get(symbol)

    @property
    def avg_latency_ms(self) -> float:
        """Latencia promedio en milisegundos."""
        if not self._latencies:
            return 0.0
        return np.mean(list(self._latencies))QUE OPINAS DE ESTO 
class BinanceWebSocketFeed:
    """WebSocket feed para Binance con reconexion automatica."""
    ENDPOINTS = {
        "spot": "wss://stream.binance.com:9443/ws",
        "futures": "wss://fstream.binance.com/ws",
    }
    def __init__(self, market_type: str = "futures"):
        if websockets is None:
            raise ImportError("pip install websockets")
        self.base_url = self.ENDPOINTS.get(market_type, self.ENDPOINTS["futures"])
        self.market_type = market_type
        self._ws = None
        self._running = False
        self._reconnect_delay = 1
        self._max_reconnect_delay = 60
        self._callbacks: Dict[str, List[Callable]] = {
            "orderbook": [],
            "trade": [],
            "ticker": [],
            "kline": [],
        }
        self._orderbooks: Dict[str, OrderBook] = {}
        self._aggregators: Dict[str, TradeAggregator] = {}
        self._subscriptions: List[str] = []
        self._message_count = 0
        self._last_message_time = 0
        self._latencies: deque = deque(maxlen=100)
    def on(self, event: str, callback: Callable):
        """Registra callback para un evento."""
        if event in self._callbacks:
            self._callbacks[event].append(callback)
    def subscribe_orderbook(self, symbol: str, depth: int = 20):
        """Suscribirse al orderbook de un simbolo."""
        s = symbol.lower().replace("/", "")
        stream = f"{s}@depth{depth}@100ms"
        self._subscriptions.append(stream)
        self._orderbooks[symbol] = OrderBook(symbol=symbol)
    def subscribe_trades(self, symbol: str):
        """Suscribirse a trades de un simbolo."""
        s = symbol.lower().replace("/", "")
        stream = f"{s}@aggTrade"
        self._subscriptions.append(stream)
        self._aggregators[symbol] = TradeAggregator()
    def subscribe_ticker(self, symbol: str):
        """Suscribirse al ticker de un simbolo."""
        s = symbol.lower().replace("/", "")
        stream = f"{s}@ticker"
        self._subscriptions.append(stream)
    def subscribe_kline(self, symbol: str, interval: str = "1m"):
        """Suscribirse a klines (velas) de un simbolo."""
        s = symbol.lower().replace("/", "")
        stream = f"{s}@kline_{interval}"
        self._subscriptions.append(stream)
    def get_orderbook(self, symbol: str) -> Optional[OrderBook]:
        """Obtiene el orderbook actual de un simbolo."""
        return self._orderbooks.get(symbol)
    def get_aggregator(self, symbol: str) -> Optional[TradeAggregator]:
        """Obtiene el agregador de trades de un simbolo."""
        return self._aggregators.get(symbol)
    @property
    def avg_latency_ms(self) -> float:
        """Latencia promedio en milisegundos."""
        if not self._latencies:
            return 0.0
        return np.mean(list(self._latencies))
    def _process_orderbook(self, data: dict):
        """Procesa actualizacion del orderbook."""
        symbol = data.get("s", "").upper()
        for sym, ob in self._orderbooks.items():
            if sym.replace("/", "").replace(":", "").upper() == symbol:
                ob.bids = [
                    OrderBookLevel(float(b[0]), float(b[1]))
                    for b in data.get("b", []) if float(b[1]) > 0
                ]
                ob.asks = [
                    OrderBookLevel(float(a[0]), float(a[1]))
                    for a in data.get("a", []) if float(a[1]) > 0
                ]
                ob.bids.sort(key=lambda x: x.price, reverse=True)
                ob.asks.sort(key=lambda x: x.price)
                ob.timestamp = data.get("E", time.time() * 1000)
                ob.update_id = data.get("u", 0)

                for cb in self._callbacks["orderbook"]:
                    try:
                        cb(ob)
                    except Exception as e:
                        logger.error(f"Error en callback orderbook: {e}")
                break

    def _process_trade(self, data: dict):
        """Procesa un trade agregado."""
        symbol = data.get("s", "").upper()
        trade = Trade(
            symbol=symbol,
            price=float(data.get("p", 0)),
            quantity=float(data.get("q", 0)),
            side="sell" if data.get("m", False) else "buy",
            timestamp=data.get("T", time.time() * 1000) / 1000,
            trade_id=str(data.get("a", "")),
        )

        for sym, agg in self._aggregators.items():
            if sym.replace("/", "").replace(":", "").upper() == symbol:
                agg.add_trade(trade)
                break

        for cb in self._callbacks["trade"]:
            try:
                cb(trade)
            except Exception as e:
                logger.error(f"Error en callback trade: {e}")

    def _process_ticker(self, data: dict):
        """Procesa un ticker de 24h."""
        ticker = Ticker(
            symbol=data.get("s", ""),
            last_price=float(data.get("c", 0)),
            bid=float(data.get("b", 0)),
            ask=float(data.get("a", 0)),
            volume_24h=float(data.get("v", 0)),
            high_24h=float(data.get("h", 0)),
            low_24h=float(data.get("l", 0)),
            change_pct_24h=float(data.get("P", 0)),
            timestamp=data.get("E", time.time() * 1000) / 1000,
        )

        for cb in self._callbacks["ticker"]:
            try:
                cb(ticker)
            except Exception as e:
                logger.error(f"Error en callback ticker: {e}")

    def _process_kline(self, data: dict):
        """Procesa un kline (vela)."""
        k = data.get("k", {})
        kline_data = {
            "symbol": data.get("s", ""),
            "interval": k.get("i", ""),
            "open": float(k.get("o", 0)),
            "high": float(k.get("h", 0)),
            "low": float(k.get("l", 0)),
            "close": float(k.get("c", 0)),
            "volume": float(k.get("v", 0)),
            "is_closed": k.get("x", False),
            "timestamp": k.get("t", 0),
        }

        for cb in self._callbacks["kline"]:
            try:
                cb(kline_data)
            except Exception as e:
                logger.error(f"Error en callback kline: {e}")
    def _process_orderbook(self, data: dict):
        """Procesa actualizacion del orderbook."""
        symbol = data.get("s", "").upper()
        for sym, ob in self._orderbooks.items():
            if sym.replace("/", "").replace(":", "").upper() == symbol:
                ob.bids = [
                    OrderBookLevel(float(b[0]), float(b[1]))
                    for b in data.get("b", []) if float(b[1]) > 0
                ]
                ob.asks = [
                    OrderBookLevel(float(a[0]), float(a[1]))
                    for a in data.get("a", []) if float(a[1]) > 0
                ]
                ob.bids.sort(key=lambda x: x.price, reverse=True)
                ob.asks.sort(key=lambda x: x.price)
                ob.timestamp = data.get("E", time.time() * 1000)
                ob.update_id = data.get("u", 0)

                for cb in self._callbacks["orderbook"]:
                    try:
                        cb(ob)
                    except Exception as e:
                        logger.error(f"Error en callback orderbook: {e}")
                break

    def _process_trade(self, data: dict):
        """Procesa un trade agregado."""
        symbol = data.get("s", "").upper()
        trade = Trade(
            symbol=symbol,
            price=float(data.get("p", 0)),
            quantity=float(data.get("q", 0)),
            side="sell" if data.get("m", False) else "buy",
            timestamp=data.get("T", time.time() * 1000) / 1000,
            trade_id=str(data.get("a", "")),
        )

        for sym, agg in self._aggregators.items():
            if sym.replace("/", "").replace(":", "").upper() == symbol:
                agg.add_trade(trade)
                break

        for cb in self._callbacks["trade"]:
            try:
                cb(trade)
            except Exception as e:
                logger.error(f"Error en callback trade: {e}")

    def _process_ticker(self, data: dict):
        """Procesa un ticker de 24h."""
        ticker = Ticker(
            symbol=data.get("s", ""),
            last_price=float(data.get("c", 0)),
            bid=float(data.get("b", 0)),
            ask=float(data.get("a", 0)),
            volume_24h=float(data.get("v", 0)),
            high_24h=float(data.get("h", 0)),
            low_24h=float(data.get("l", 0)),
            change_pct_24h=float(data.get("P", 0)),
            timestamp=data.get("E", time.time() * 1000) / 1000,
        )

        for cb in self._callbacks["ticker"]:
            try:
                cb(ticker)
            except Exception as e:
                logger.error(f"Error en callback ticker: {e}")

    def _process_kline(self, data: dict):
        """Procesa un kline (vela)."""
        k = data.get("k", {})
        kline_data = {
            "symbol": data.get("s", ""),
            "interval": k.get("i", ""),
            "open": float(k.get("o", 0)),
            "high": float(k.get("h", 0)),
            "low": float(k.get("l", 0)),
            "close": float(k.get("c", 0)),
            "volume": float(k.get("v", 0)),
            "is_closed": k.get("x", False),
            "timestamp": k.get("t", 0),
        }

        for cb in self._callbacks["kline"]:
            try:
                cb(kline_data)
            except Exception as e:
                logger.error(f"Error en callback kline: {e}")

class WebSocketManager:
    """Gestor principal de feeds WebSocket multi-exchange."""

    def __init__(self):
        self.feeds: Dict[str, BinanceWebSocketFeed] = {}
        self._tasks: List[asyncio.Task] = []
        self._running = False

    def add_feed(self, name: str, feed: BinanceWebSocketFeed):
        """Agrega un feed al manager."""
        self.feeds[name] = feed

    async def start_all(self):
        """Inicia todos los feeds en paralelo."""
        self._running = True
        for name, feed in self.feeds.items():
            task = asyncio.create_task(feed.connect())
            self._tasks.append(task)
            logger.info(f"Feed {name} iniciado")
        try:
            await asyncio.gather(*self._tasks)
        except asyncio.CancelledError:
            logger.info("Feeds cancelados")

    async def stop_all(self):
        """Detiene todos los feeds."""
        self._running = False
        for name, feed in self.feeds.items():
            await feed.disconnect()
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

    def get_status(self) -> Dict[str, Any]:
        """Obtiene estado de todos los feeds."""
        status = {}
        for name, feed in self.feeds.items():
            status[name] = {
                "connected": feed._ws is not None and feed._running,
                "messages": feed._message_count,
                "avg_latency_ms": round(feed.avg_latency_ms, 2),
                "subscriptions": len(feed._subscriptions),
            }
        return status


def create_default_feed(
    symbols: List[str],
    market_type: str = "futures",
    subscribe_orderbook: bool = True,
    subscribe_trades: bool = True,
    subscribe_ticker: bool = True,
) -> BinanceWebSocketFeed:
    """Crea un feed WebSocket con suscripciones por defecto."""
    feed = BinanceWebSocketFeed(market_type=market_type)
    for symbol in symbols:
        if subscribe_orderbook:
            feed.subscribe_orderbook(symbol)
        if subscribe_trades:
            feed.subscribe_trades(symbol)
        if subscribe_ticker:
            feed.subscribe_ticker(symbol)
    return feed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    async def main():
        feed = create_default_feed(
            symbols=["BTC/USDT:USDT", "ETH/USDT:USDT"],
        )
        feed.on("trade", lambda t: print(f"Trade: {t.symbol} {t.side} {t.price}"))
        feed.on("orderbook", lambda ob: print(f"OB: {ob.symbol} spread={ob.spread_pct:.4f}%"))
        try:
            await feed.connect()
        except KeyboardInterrupt:
            await feed.disconnect()

    asyncio.run(main())
