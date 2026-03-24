"""
Ultra Scalping Bot - Telegram Notifications
Real-time trade alerts and daily reports
"""
import aiohttp
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, config):
        self.config = config.telegram
        self.base_url = f"https://api.telegram.org/bot{self.config.bot_token}"
        self.enabled = self.config.enabled and self.config.bot_token and self.config.chat_id

    async def send_message(self, text, parse_mode="HTML"):
        if not self.enabled:
            return
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {"chat_id": self.config.chat_id, "text": text, "parse_mode": parse_mode}
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        logger.error(f"Telegram error: {resp.status}")
        except Exception as e:
            logger.error(f"Telegram error: {e}")

    def send_sync(self, text):
        if not self.enabled:
            return
        try:
            asyncio.run(self.send_message(text))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self.send_message(text))

    def notify_trade_open(self, symbol, side, price, size, sl, tp, strategy, confidence):
        if not self.config.notify_on_trade: return
        msg = f"NEW TRADE\nSymbol: {symbol}\nSide: {side}\nEntry: {price:.2f}\nSize: {size:.6f}\nSL: {sl:.2f}\nTP: {tp:.2f}\nStrategy: {strategy}\nConf: {confidence:.0%}"
        self.send_sync(msg)

    def notify_trade_close(self, symbol, side, entry, exit_price, pnl, reason):
        if not self.config.notify_on_trade: return
        tag = "WIN" if pnl > 0 else "LOSS"
        msg = f"CLOSED [{tag}]\nSymbol: {symbol}\nSide: {side}\nEntry: {entry:.2f}\nExit: {exit_price:.2f}\nPnL: {pnl:+.4f}\nReason: {reason}"
        self.send_sync(msg)

    def notify_daily_report(self, stats):
        if not self.config.notify_daily_report: return
        msg = f"DAILY REPORT\nBalance: ${stats.get('balance', 0):.2f}\nTrades: {stats.get('total_trades', 0)}\nWin Rate: {stats.get('win_rate', 0):.1f}%\nPnL: {stats.get('total_pnl', 0):+.4f}"
        self.send_sync(msg)

    def notify_error(self, error_msg):
        if not self.config.notify_on_error: return
        self.send_sync(f"BOT ERROR: {error_msg}")

    def notify_start(self, config):
        msg = f"BOT STARTED\nMode: {config.mode}\nStrategy: {config.strategy.active_strategy}\nSymbols: {', '.join(config.scalping.symbols)}\nTF: {config.scalping.timeframe}"
        self.send_sync(msg)

    def notify_stop(self, stats):
        msg = f"BOT STOPPED\nBalance: ${stats.get('balance', 0):.2f}\nTrades: {stats.get('total_trades', 0)}\nPnL: {stats.get('total_pnl', 0):+.4f}"
        self.send_sync(msg)
