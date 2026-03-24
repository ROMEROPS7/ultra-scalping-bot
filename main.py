"""
Ultra Scalping Bot - Main Entry Point
Combines the best of Freqtrade, Passivbot, Hummingbot & Jesse AI
"""
import time
import logging
import sys
from datetime import datetime
from rich.console import Console
from rich.table import Table

from config.settings import BotConfig
from core.indicators import Indicators
from core.strategies import get_strategy, Signal
from core.exchange import ExchangeConnector, PaperExchange
from core.risk_manager import RiskManager

console = Console()
logging.basicConfig(level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(),
              logging.FileHandler('logs/bot.log')])
logger = logging.getLogger(__name__)


class UltraScalpingBot:
    def __init__(self, config=None):
        self.config = config or BotConfig()
        self.strategy = get_strategy(self.config)
        self.risk_manager = RiskManager(self.config)
        self.running = False
        self.cycle_count = 0
        if self.config.mode == "live":
            self.exchange = ExchangeConnector(self.config).connect()
        else:
            self.exchange = PaperExchange(self.config)

    def show_banner(self):
        console.print("[bold cyan]ULTRA SCALPING BOT v1.0[/bold cyan]")
        console.print("[cyan]Freqtrade + Passivbot + Hummingbot + Jesse AI[/cyan]")
        console.print(f"Mode: {self.config.mode} | Strategy: {self.config.strategy.active_strategy}")
        console.print(f"Symbols: {', '.join(self.config.scalping.symbols)}")
        console.print(f"TF: {self.config.scalping.timeframe} | Leverage: {self.config.scalping.leverage}x")

    def process_symbol(self, symbol):
        try:
            if self.config.mode == "live":
                df = self.exchange.fetch_ohlcv(symbol, self.config.scalping.timeframe, 200)
            else:
                return  # Paper mode needs live data feed
            df = Indicators.calculate_all(df, self.config)
            setup = self.strategy.analyze(df)
            if setup.signal == Signal.HOLD:
                return
            can_trade, reason = self.risk_manager.can_trade()
            if not can_trade:
                logger.info(f"[{symbol}] {setup.signal.value} blocked: {reason}")
                return
            if self.exchange.get_position(symbol):
                return
            size = self.risk_manager.calculate_position_size(
                self.risk_manager.current_balance, setup.entry_price, setup.stop_loss)
            if size <= 0:
                return
            side = 'buy' if setup.signal == Signal.LONG else 'sell'
            logger.info(f"[{symbol}] {setup.signal.value} @{setup.entry_price:.2f} "
                       f"SL:{setup.stop_loss:.2f} TP:{setup.take_profit:.2f} "
                       f"Size:{size:.6f} Conf:{setup.confidence:.2f}")
            if self.config.mode == "live":
                self.exchange.set_leverage(symbol, self.config.scalping.leverage)
                self.exchange.create_market_order(symbol, side, size)
                opp = 'sell' if side == 'buy' else 'buy'
                self.exchange.create_stop_loss(symbol, opp, size, setup.stop_loss)
            else:
                self.exchange.create_market_order(symbol, side, size,
                    {'price': setup.entry_price})
        except Exception as e:
            logger.error(f"Error {symbol}: {e}")

    def check_exits(self, symbol):
        try:
            pos = self.exchange.get_position(symbol)
            if not pos or self.config.mode != "live":
                return
            df = self.exchange.fetch_ohlcv(symbol, self.config.scalping.timeframe, 10)
            price = df.iloc[-1]['close']
            entry = float(pos.get('entryPrice', 0))
            side = pos.get('side', 'long')
            sc = self.config.scalping
            hit_tp = hit_sl = False
            if side == 'long':
                hit_tp = price >= entry * (1 + sc.take_profit_pct)
                hit_sl = price <= entry * (1 - sc.stop_loss_pct)
                pnl = (price - entry) * float(pos.get('contracts', 0))
            else:
                hit_tp = price <= entry * (1 - sc.take_profit_pct)
                hit_sl = price >= entry * (1 + sc.stop_loss_pct)
                pnl = (entry - price) * float(pos.get('contracts', 0))
            if hit_tp or hit_sl:
                self.risk_manager.record_trade(pnl, symbol)
        except Exception as e:
            logger.error(f"Exit error {symbol}: {e}")

    def print_status(self):
        stats = self.risk_manager.get_stats()
        table = Table(title="Bot Status")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        for k, v in stats.items():
            table.add_row(k, f"{v:.4f}" if isinstance(v, float) else str(v))
        table.add_row("Cycle", str(self.cycle_count))
        console.print(table)

    def run(self):
        self.show_banner()
        self.running = True
        logger.info("Bot started!")
        try:
            while self.running:
                self.cycle_count += 1
                for sym in self.config.scalping.symbols:
                    self.check_exits(sym)
                    self.process_symbol(sym)
                if self.cycle_count % 10 == 0:
                    self.print_status()
                sleeps = {'1m': 60, '3m': 180, '5m': 300, '15m': 900}
                time.sleep(sleeps.get(self.config.scalping.timeframe, 60))
        except KeyboardInterrupt:
            logger.info("Stopped by user")
            self.print_status()


def main():
    import os
    os.makedirs('logs', exist_ok=True)
    config = BotConfig()
    if len(sys.argv) > 1 and sys.argv[1] in ('live', 'paper', 'backtest'):
        config.mode = sys.argv[1]
    console.print("[yellow]WARNING: Trading involves risk.[/yellow]")
    bot = UltraScalpingBot(config)
    bot.run()


if __name__ == "__main__":
    main()
