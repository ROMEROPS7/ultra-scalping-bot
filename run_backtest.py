#!/usr/bin/env python3
"""
Ultra Scalping Bot - Backtest Runner
Script independiente para ejecutar backtests con datos historicos.

Uso:
    python run_backtest.py --symbol BTC/USDT:USDT --timeframe 1m --days 30
    python run_backtest.py --symbol ETH/USDT:USDT --strategy momentum --days 7
    python run_backtest.py --symbol BTC/USDT:USDT --optimize --days 14
"""

import argparse
import sys
import os
import json
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import BotConfig
from core.backtester import Backtester, DataDownloader
from core.strategies import (
    EmaRsiAtrStrategy,
    MomentumScalperStrategy,
    GridScalperStrategy,
    CombinedStrategy,
)

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    RICH = True
except ImportError:
    RICH = False

STRATEGIES = {
    "ema_rsi": EmaRsiAtrStrategy,
    "momentum": MomentumScalperStrategy,
    "grid": GridScalperStrategy,
    "combined": CombinedStrategy,
}


def print_results(results: dict):
    """Imprime resultados del backtest."""
    if RICH:
        console = Console()
        table = Table(title="Backtest Results", box=box.DOUBLE_EDGE)
        table.add_column("Metric", style="cyan", width=30)
        table.add_column("Value", style="green", justify="right")
        metrics = [
            ("Total Trades", str(results.get("total_trades", 0))),
            ("Win Rate", f"{results.get('win_rate', 0):.1f}%"),
            ("Profit Factor", f"{results.get('profit_factor', 0):.2f}"),
            ("Total PnL", f"${results.get('total_pnl', 0):.2f}"),
            ("Max Drawdown", f"{results.get('max_drawdown_pct', 0):.2f}%"),
            ("Sharpe Ratio", f"{results.get('sharpe_ratio', 0):.2f}"),
        ]
        for name, val in metrics:
            table.add_row(name, val)
        console.print(table)
        pnl = results.get("total_pnl", 0)
        status = "[green]PROFIT[/green]" if pnl > 0 else "[red]LOSS[/red]"
        console.print(Panel(f"Result: {status} | ${pnl:.2f}", title="Summary"))
    else:
        print("\n=== BACKTEST RESULTS ===")
        for k, v in results.items():
            print(f"  {k}: {v}")


def save_results(results: dict, filepath: str):
    """Guarda resultados en JSON."""
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Results saved to {filepath}")


def run_single_backtest(args):
    """Ejecuta un backtest individual."""
    config = BotConfig()
    config.exchange.exchange_id = args.exchange
    config.scalping.symbols = [args.symbol]
    config.scalping.timeframe = args.timeframe
    config.backtest.initial_capital = args.capital
    config.backtest.commission_pct = args.commission

    # Download data
    print(f"Downloading {args.days} days of {args.symbol} data...")
    downloader = DataDownloader(config)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.days)
    data = downloader.download(
        symbol=args.symbol,
        timeframe=args.timeframe,
        start_date=start_date,
        end_date=end_date,
    )

    if data is None or data.empty:
        print("ERROR: No data downloaded. Check symbol and exchange.")
        sys.exit(1)

    print(f"Downloaded {len(data)} candles")

    # Create strategy
    strategy_cls = STRATEGIES.get(args.strategy)
    if not strategy_cls:
        print(f"Unknown strategy: {args.strategy}")
        print(f"Available: {list(STRATEGIES.keys())}")
        sys.exit(1)

    strategy = strategy_cls(config.strategy)

    # Run backtest
    print(f"Running backtest with {args.strategy} strategy...")
    backtester = Backtester(config)
    results = backtester.run(data, strategy)

    print_results(results)

    if args.output:
        save_results(results, args.output)

    return results


def run_compare(args):
    """Compara todas las estrategias."""
    config = BotConfig()
    config.exchange.exchange_id = args.exchange
    config.scalping.symbols = [args.symbol]
    config.scalping.timeframe = args.timeframe
    config.backtest.initial_capital = args.capital

    print(f"Downloading data...")
    downloader = DataDownloader(config)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.days)
    data = downloader.download(args.symbol, args.timeframe, start_date, end_date)

    if data is None or data.empty:
        print("ERROR: No data downloaded.")
        sys.exit(1)

    all_results = {}
    for name, cls in STRATEGIES.items():
        print(f"\nTesting {name}...")
        strategy = cls(config.strategy)
        backtester = Backtester(config)
        results = backtester.run(data, strategy)
        all_results[name] = results

    # Print comparison
    if RICH:
        console = Console()
        table = Table(title="Strategy Comparison", box=box.DOUBLE_EDGE)
        table.add_column("Strategy", style="cyan")
        table.add_column("Trades", justify="right")
        table.add_column("Win Rate", justify="right")
        table.add_column("PnL", justify="right")
        table.add_column("Sharpe", justify="right")
        table.add_column("MaxDD", justify="right")

        for name, r in all_results.items():
            pnl = r.get("total_pnl", 0)
            style = "green" if pnl > 0 else "red"
            table.add_row(
                name,
                str(r.get("total_trades", 0)),
                f"{r.get('win_rate', 0):.1f}%",
                f"[{style}]${pnl:.2f}[/{style}]",
                f"{r.get('sharpe_ratio', 0):.2f}",
                f"{r.get('max_drawdown_pct', 0):.2f}%",
            )
        console.print(table)
    else:
        for name, r in all_results.items():
            print(f"{name}: PnL=${r.get('total_pnl', 0):.2f} WR={r.get('win_rate', 0):.1f}%")


def main():
    parser = argparse.ArgumentParser(description="Ultra Scalping Bot Backtester")
    parser.add_argument("--symbol", default="BTC/USDT:USDT", help="Trading pair")
    parser.add_argument("--timeframe", default="1m", help="Candle timeframe")
    parser.add_argument("--days", type=int, default=30, help="Days of history")
    parser.add_argument("--strategy", default="combined", choices=list(STRATEGIES.keys()))
    parser.add_argument("--exchange", default="binance", help="Exchange ID")
    parser.add_argument("--capital", type=float, default=1000.0, help="Initial capital")
    parser.add_argument("--commission", type=float, default=0.04, help="Commission %")
    parser.add_argument("--compare", action="store_true", help="Compare all strategies")
    parser.add_argument("--output", default="", help="Save results to JSON file")

    args = parser.parse_args()

    print("=" * 60)
    print("  ULTRA SCALPING BOT - BACKTESTER")
    print("=" * 60)
    print(f"  Symbol: {args.symbol}")
    print(f"  Timeframe: {args.timeframe}")
    print(f"  Period: {args.days} days")
    print(f"  Capital: ${args.capital}")
    print(f"  Exchange: {args.exchange}")
    print("=" * 60)

    if args.compare:
        run_compare(args)
    else:
        run_single_backtest(args)


if __name__ == "__main__":
    main()
