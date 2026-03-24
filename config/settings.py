"""
Ultra Scalping Bot - Configuration
Inspired by Freqtrade, Passivbot, Hummingbot & Jesse AI
"""
from dataclasses import dataclass, field
from typing import List, Optional
import os
from dotenv import load_dotenv

load_dotenv()


@dataclass
class ExchangeConfig:
    """Exchange API configuration"""
    name: str = "binance"
    api_key: str = os.getenv("API_KEY", "")
    api_secret: str = os.getenv("API_SECRET", "")
    testnet: bool = True
    rate_limit: int = 1200


@dataclass
class ScalpingConfig:
    """Core scalping parameters"""
    symbols: List[str] = field(default_factory=lambda: ["BTC/USDT", "ETH/USDT"])
    timeframe: str = "1m"
    higher_timeframe: str = "5m"
    initial_capital: float = 1000.0
    risk_per_trade: float = 0.01
    max_positions: int = 3
    leverage: int = 5
    take_profit_pct: float = 0.003
    stop_loss_pct: float = 0.002
    trailing_stop: bool = True
    trailing_stop_pct: float = 0.001
    use_grid: bool = True
    grid_levels: int = 3
    grid_spacing_pct: float = 0.001
    cooldown_seconds: int = 30


@dataclass
class StrategyConfig:
    """Strategy parameters"""
    active_strategy: str = "combined"
    ema_fast: int = 8
    ema_medium: int = 21
    ema_slow: int = 55
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    rsi_scalp_upper: float = 60.0
    rsi_scalp_lower: float = 40.0
    atr_period: int = 14
    atr_multiplier: float = 1.5
    min_atr_threshold: float = 0.0005
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bb_period: int = 20
    bb_std: float = 2.0
    volume_sma_period: int = 20
    min_volume_multiplier: float = 1.2
    orderbook_depth: int = 10
    imbalance_threshold: float = 0.6


@dataclass
class RiskConfig:
    """Risk management inspired by Passivbot"""
    max_daily_loss_pct: float = 0.03
    max_drawdown_pct: float = 0.05
    max_consecutive_losses: int = 5
    daily_trade_limit: int = 50
    pause_after_loss_streak: int = 300
    max_position_size_pct: float = 0.1
    reduce_size_on_loss: bool = True
    size_reduction_factor: float = 0.5


@dataclass
class TelegramConfig:
    """Telegram notifications"""
    enabled: bool = False
    bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    notify_on_trade: bool = True
    notify_on_error: bool = True
    notify_daily_report: bool = True


@dataclass
class BacktestConfig:
    """Backtesting configuration"""
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    initial_balance: float = 10000.0
    commission_pct: float = 0.0004
    slippage_pct: float = 0.0001


@dataclass
class BotConfig:
    """Master configuration"""
    exchange: ExchangeConfig = field(default_factory=ExchangeConfig)
    scalping: ScalpingConfig = field(default_factory=ScalpingConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    log_level: str = "INFO"
    log_file: str = "logs/bot.log"
    mode: str = "paper"
