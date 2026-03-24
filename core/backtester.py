"""
Ultra Scalping Bot - Backtester Engine
Complete backtesting with historical data, metrics & equity curve
"""
import ccxt
import pandas as pd
import numpy as np
import logging
from datetime import datetime
from typing import List, Dict
from core.indicators import Indicators
from core.strategies import get_strategy, Signal
from core.risk_manager import RiskManager

logger = logging.getLogger(__name__)


class DataDownloader:
    """Download historical OHLCV data via CCXT"""
    @staticmethod
    def download(exchange_name, symbol, timeframe, start_date, end_date):
        exchange = getattr(ccxt, exchange_name)({"enableRateLimit": True})
        since = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
        end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)
        all_ohlcv = []
        logger.info(f"Downloading {symbol} {timeframe} {start_date} to {end_date}")
        while since < end_ts:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
            if not ohlcv:
                break
            all_ohlcv.extend(ohlcv)
            since = ohlcv[-1][0] + 1
        df = pd.DataFrame(all_ohlcv, columns=["timestamp","open","high","low","close","volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        df = df[~df.index.duplicated(keep="first")]
        logger.info(f"Downloaded {len(df)} candles")
        return df

    @staticmethod
    def save(df, path):
        df.to_csv(path)

    @staticmethod
    def load(path):
        return pd.read_csv(path, index_col="timestamp", parse_dates=True)


class BacktestTrade:
    def __init__(self, symbol, side, entry, size, time, sl, tp, strat):
        self.symbol = symbol
        self.side = side
        self.entry_price = entry
        self.size = size
        self.entry_time = time
        self.sl = sl
        self.tp = tp
        self.strategy = strat
        self.exit_price = 0
        self.exit_time = None
        self.pnl = 0
        self.exit_reason = ""


class Backtester:
    """Full backtesting engine with realistic simulation"""
    def __init__(self, config):
        self.config = config
        self.strategy = get_strategy(config)
        self.risk_manager = RiskManager(config)
        self.trades = []
        self.open_trades = {}
        self.equity_curve = []
        self.balance = config.backtest.initial_balance
        self.peak = self.balance

    def run(self, df, symbol="BTC/USDT"):
        logger.info(f"Backtest: {len(df)} candles, ${self.balance}")
        df = Indicators.calculate_all(df, self.config)
        for i in range(60, len(df)):
            window = df.iloc[:i+1].copy()
            cur = df.iloc[i]
            price, high, low = cur["close"], cur["high"], cur["low"]
            ts = df.index[i]
            # Check exits
            for sym in list(self.open_trades.keys()):
                t = self.open_trades[sym]
                if t.side == "long":
                    if low <= t.sl:
                        self._close(sym, t.sl, ts, "SL")
                    elif high >= t.tp:
                        self._close(sym, t.tp, ts, "TP")
                else:
                    if high >= t.sl:
                        self._close(sym, t.sl, ts, "SL")
                    elif low <= t.tp:
                        self._close(sym, t.tp, ts, "TP")
            # New signals
            if symbol not in self.open_trades:
                can, _ = self.risk_manager.can_trade()
                if not can:
                    continue
                setup = self.strategy.analyze(window)
                if setup.signal in (Signal.LONG, Signal.SHORT):
                    size = self.risk_manager.calculate_position_size(
                        self.balance, setup.entry_price, setup.stop_loss)
                    if size <= 0:
                        continue
                    cost = (size * price) / self.config.scalping.leverage
                    if cost > self.balance * 0.95:
                        continue
                    side = "long" if setup.signal == Signal.LONG else "short"
                    trade = BacktestTrade(symbol, side, price, size, ts,
                                          setup.stop_loss, setup.take_profit,
                                          setup.strategy_name)
                    self.open_trades[symbol] = trade
                    self.balance -= price * size * self.config.backtest.commission_pct
            self.equity_curve.append({"ts": ts, "bal": self._equity(price)})
        # Close remaining
        fp = df.iloc[-1]["close"]
        for sym in list(self.open_trades.keys()):
            self._close(sym, fp, df.index[-1], "END")
        return self._metrics()

    def _close(self, symbol, exit_price, exit_time, reason):
        t = self.open_trades.pop(symbol)
        t.exit_price = exit_price
        t.exit_time = exit_time
        t.exit_reason = reason
        if t.side == "long":
            t.pnl = (exit_price - t.entry_price) * t.size
        else:
            t.pnl = (t.entry_price - exit_price) * t.size
        comm = exit_price * t.size * self.config.backtest.commission_pct
        slip = exit_price * t.size * self.config.backtest.slippage_pct
        t.pnl -= (comm + slip)
        self.balance += t.pnl
        self.risk_manager.record_trade(t.pnl, symbol)
        if self.balance > self.peak:
            self.peak = self.balance
        self.trades.append(t)

    def _equity(self, price):
        eq = self.balance
        for t in self.open_trades.values():
            if t.side == "long":
                eq += (price - t.entry_price) * t.size
            else:
                eq += (t.entry_price - price) * t.size
        return eq

    def _metrics(self):
        if not self.trades:
            return {"error": "No trades"}
        wins = [t for t in self.trades if t.pnl > 0]
        losses = [t for t in self.trades if t.pnl <= 0]
        pnl = sum(t.pnl for t in self.trades)
        gp = sum(t.pnl for t in wins) if wins else 0
        gl = abs(sum(t.pnl for t in losses)) if losses else 0.01
        eq = pd.Series([e["bal"] for e in self.equity_curve])
        dd = ((eq - eq.cummax()) / eq.cummax() * 100).min()
        durs = [(t.exit_time - t.entry_time).total_seconds()/60
                for t in self.trades if t.exit_time and t.entry_time]
        init = self.config.backtest.initial_balance
        rets = eq.pct_change().dropna()
        sharpe = (rets.mean() / rets.std()) * np.sqrt(525600) if rets.std() > 0 else 0
        return {
            "total_trades": len(self.trades), "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins)/len(self.trades)*100,
            "total_pnl": pnl, "roi_pct": (self.balance-init)/init*100,
            "profit_factor": gp/gl, "max_drawdown_pct": dd,
            "avg_win": np.mean([t.pnl for t in wins]) if wins else 0,
            "avg_loss": np.mean([t.pnl for t in losses]) if losses else 0,
            "best_trade": max(t.pnl for t in self.trades),
            "worst_trade": min(t.pnl for t in self.trades),
            "avg_duration_min": np.mean(durs) if durs else 0,
            "sharpe_ratio": sharpe,
            "final_balance": self.balance,
        }

    def print_results(self, m):
        print("\n" + "="*55)
        print("         BACKTEST RESULTS")
        print("="*55)
        for k, v in m.items():
            print(f"  {k:.<35} {v:>12.4f}" if isinstance(v, float) else f"  {k:.<35} {v:>12}")
        print("="*55)
