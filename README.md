# Ultra Scalping Bot

**Advanced crypto scalping trading bot combining best practices from the top open-source trading frameworks.**

> Inspired by: Freqtrade (48k stars), CCXT (41k stars), Hummingbot (17k stars), Jesse AI (7.6k stars), Passivbot (1.9k stars), OctoBot (5.5k stars)

## Features

**From Freqtrade:** Multi-strategy framework, FreqAI-inspired ML optimization, backtesting, Telegram integration

**From Passivbot:** Grid scalping, trailing entries/exits, Martingale-inspired DCA, automatic volatile market selection, unstucking mechanism

**From Hummingbot:** Orderbook imbalance detection, high-frequency market making, multi-exchange support via CCXT

**From Jesse AI:** Simple strategy syntax, 100+ technical indicators, multi-timeframe analysis, AI-powered optimization

## Strategies Included

| Strategy | Description | Best For |
|----------|------------|----------|
| EMA+RSI+ATR | Triple EMA crossover with RSI momentum and ATR volatility filter | Trend-following scalps |
| Momentum Scalper | Bollinger Bands + RSI + MACD momentum plays | Mean-reversion scalps |
| Grid Scalper | Passivbot-style grid orders around EMA | Range-bound markets |
| Orderbook Imbalance | Hummingbot-style orderbook pressure analysis | HFT scalping |
| Combined (default) | Voting system - only trades when 2+ strategies agree | Highest win rate |

## Quick Start

### 1. Clone & Install
```bash
git clone https://github.com/ROMEROPS7/ultra-scalping-bot.git
cd ultra-scalping-bot
pip install -r requirements.txt
```

### 2. Configure
```bash
cp .env.example .env
# Edit .env with your API keys
```

### 3. Run
```bash
# Paper trading (safe, no real money)
python main.py paper

# Live trading (real money - USE AT YOUR OWN RISK)
python main.py live
```

## Project Structure

```
ultra-scalping-bot/
├── main.py                  # Entry point
├── requirements.txt         # Dependencies
├── .env.example            # API keys template
├── config/
│   ├── __init__.py
│   └── settings.py         # All configuration (exchange, strategy, risk)
├── core/
│   ├── __init__.py
│   ├── indicators.py       # 15+ technical indicators (EMA, RSI, ATR, MACD, BB, VWAP...)
│   ├── strategies.py       # 5 scalping strategies + combined voting system
│   ├── exchange.py         # CCXT exchange connector + paper trading simulator
│   └── risk_manager.py     # Risk management (daily limits, drawdown, position sizing)
└── logs/
    └── bot.log
```

## Configuration

Edit `config/settings.py` to customize:

- **Exchange**: Binance, Bybit, OKX, Bitget, Kraken, Gate.io, Hyperliquid
- **Symbols**: Any crypto futures pair (BTC/USDT, ETH/USDT, etc.)
- **Timeframe**: 1m, 3m, 5m, 15m (lower = more scalping opportunities)
- **Leverage**: 1x to 20x
- **Risk**: Max daily loss, max drawdown, position sizing, trailing stops
- **Strategy**: Choose from 5 strategies or use combined voting

## Risk Management

- Max daily loss limit (default: 3%)
- Max drawdown protection (default: 5%)
- Consecutive loss streak pause
- Dynamic position sizing (reduces after losses)
- Cooldown between trades
- Daily trade limit

## Supported Exchanges

All exchanges supported by CCXT (100+), optimized for:
- Binance Futures
- Bybit Perpetual
- OKX Futures
- Bitget Futures
- Hyperliquid
- Gate.io Futures

## Disclaimer

This software is for **educational purposes only**. Cryptocurrency trading involves substantial risk of loss. Past performance does not guarantee future results. Never invest more than you can afford to lose. Always start with paper trading.

## License

MIT License
