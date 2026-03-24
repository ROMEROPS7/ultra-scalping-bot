"""
Ultra Scalping Bot - Risk Manager
Inspired by Passivbot's unstucking & Freqtrade's edge module
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict

logger = logging.getLogger(__name__)


class RiskManager:
    def __init__(self, config):
        self.config = config
        self.rc = config.risk
        self.daily_pnl = 0.0
        self.peak_balance = config.scalping.initial_capital
        self.current_balance = config.scalping.initial_capital
        self.consecutive_losses = 0
        self.daily_trades = 0
        self.last_trade_time = None
        self.pause_until = None
        self.trade_log: List[Dict] = []

    def can_trade(self) -> tuple:
        if self.pause_until and datetime.now() < self.pause_until:
            return False, "Paused after loss streak"
        if self.daily_trades >= self.rc.daily_trade_limit:
            return False, "Daily limit reached"
        if self.daily_pnl <= -(self.current_balance * self.rc.max_daily_loss_pct):
            return False, "Max daily loss"
        drawdown = (self.peak_balance - self.current_balance) / self.peak_balance
        if drawdown >= self.rc.max_drawdown_pct:
            return False, f"Max drawdown {drawdown*100:.1f}%"
        if self.consecutive_losses >= self.rc.max_consecutive_losses:
            self.pause_until = datetime.now() + timedelta(seconds=self.rc.pause_after_loss_streak)
            self.consecutive_losses = 0
            return False, "Loss streak pause"
        if self.last_trade_time:
            cooldown = timedelta(seconds=self.config.scalping.cooldown_seconds)
            if datetime.now() - self.last_trade_time < cooldown:
                return False, "Cooldown"
        return True, "OK"

    def calculate_position_size(self, capital, entry, stop_loss):
        risk_pct = self.config.scalping.risk_per_trade
        if self.rc.reduce_size_on_loss and self.consecutive_losses > 0:
            risk_pct *= self.rc.size_reduction_factor ** self.consecutive_losses
        max_size = capital * self.rc.max_position_size_pct
        price_risk = abs(entry - stop_loss)
        if price_risk == 0:
            return 0
        size_value = min((capital * risk_pct) / price_risk * entry, max_size)
        return size_value / entry

    def record_trade(self, pnl, symbol=""):
        self.daily_pnl += pnl
        self.current_balance += pnl
        self.daily_trades += 1
        self.last_trade_time = datetime.now()
        if pnl >= 0:
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
        if self.current_balance > self.peak_balance:
            self.peak_balance = self.current_balance
        self.trade_log.append({'timestamp': datetime.now().isoformat(),
            'symbol': symbol, 'pnl': pnl, 'balance': self.current_balance})
        tag = "WIN" if pnl >= 0 else "LOSS"
        logger.info(f"[{tag}] PnL:{pnl:.4f} Bal:{self.current_balance:.2f}")

    def reset_daily(self):
        self.daily_pnl = 0.0
        self.daily_trades = 0

    def get_stats(self):
        total = len(self.trade_log)
        wins = sum(1 for t in self.trade_log if t['pnl'] > 0)
        losses = total - wins
        total_pnl = sum(t['pnl'] for t in self.trade_log)
        wr = (wins / total * 100) if total > 0 else 0
        dd = (self.peak_balance - self.current_balance) / self.peak_balance * 100
        return {'total_trades': total, 'wins': wins, 'losses': losses,
                'win_rate': wr, 'total_pnl': total_pnl, 'max_drawdown': dd,
                'balance': self.current_balance, 'peak': self.peak_balance}
