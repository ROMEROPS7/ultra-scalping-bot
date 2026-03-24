#!/usr/bin/env python3
"""
Ultra Scalping Bot - ML Optimizer Runner
Script para optimizar parametros y entrenar el modelo ML.

Uso:
    python run_optimizer.py --symbol BTC/USDT:USDT --days 30
    python run_optimizer.py --symbol ETH/USDT:USDT --iterations 200
    python run_optimizer.py --train-ml --symbol BTC/USDT:USDT --days 60
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
from core.ml_optimizer import MLSignalPredictor, ParameterOptimizer
from core.strategies import CombinedStrategy

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich import box
    RICH = True
except ImportError:
    RICH = False


def optimize_parameters(args):
    """Optimiza parametros de la estrategia."""
    config = BotConfig()
    config.exchange.exchange_id = args.exchange
    config.scalping.symbols = [args.symbol]
    config.scalping.timeframe = args.timeframe
    config.backtest.initial_capital = args.capital

    print(f"Downloading {args.days} days of {args.symbol} data...")
    downloader = DataDownloader(config)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.days)
    data = downloader.download(args.symbol, args.timeframe, start_date, end_date)

    if data is None or data.empty:
        print("ERROR: No data downloaded.")
        sys.exit(1)

    print(f"Downloaded {len(data)} candles")
    print(f"Running optimization with {args.iterations} iterations...")

    optimizer = ParameterOptimizer(config)
    best_params, best_score, all_results = optimizer.optimize(
        data=data,
        n_iterations=args.iterations,
    )

    if RICH:
        console = Console()
        console.print(Panel("Optimization Complete", style="bold green"))
        table = Table(title="Best Parameters", box=box.DOUBLE_EDGE)
        table.add_column("Parameter", style="cyan")
        table.add_column("Value", style="green", justify="right")
        for k, v in best_params.items():
            table.add_row(k, f"{v:.4f}" if isinstance(v, float) else str(v))
        console.print(table)
        console.print(f"Best Score: [bold green]{best_score:.4f}[/bold green]")
    else:
        print(f"\nBest Score: {best_score:.4f}")
        print("Best Parameters:")
        for k, v in best_params.items():
            print(f"  {k}: {v}")

    if args.output:
        output = {"best_params": best_params, "best_score": best_score}
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(output, f, indent=2, default=str)
        print(f"Saved to {args.output}")


def train_ml_model(args):
    """Entrena el modelo ML de prediccion de senales."""
    config = BotConfig()
    config.exchange.exchange_id = args.exchange

    print(f"Downloading {args.days} days of {args.symbol} data...")
    downloader = DataDownloader(config)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.days)
    data = downloader.download(args.symbol, args.timeframe, start_date, end_date)

    if data is None or data.empty:
        print("ERROR: No data.")
        sys.exit(1)

    print(f"Training ML model on {len(data)} candles...")
    predictor = MLSignalPredictor()
    metrics = predictor.train(data)

    if RICH:
        console = Console()
        table = Table(title="ML Model Metrics", box=box.DOUBLE_EDGE)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green", justify="right")
        for k, v in metrics.items():
            table.add_row(k, f"{v:.4f}" if isinstance(v, float) else str(v))
        console.print(table)
    else:
        print("\nML Model Metrics:")
        for k, v in metrics.items():
            print(f"  {k}: {v}")

    # Save model
    model_path = args.model_path or "models/ml_predictor.joblib"
    Path(model_path).parent.mkdir(parents=True, exist_ok=True)
    predictor.save(model_path)
    print(f"Model saved to {model_path}")


def main():
    parser = argparse.ArgumentParser(description="Ultra Scalping Bot Optimizer")
    parser.add_argument("--symbol", default="BTC/USDT:USDT", help="Trading pair")
    parser.add_argument("--timeframe", default="1m", help="Candle timeframe")
    parser.add_argument("--days", type=int, default=30, help="Days of history")
    parser.add_argument("--exchange", default="binance", help="Exchange ID")
    parser.add_argument("--capital", type=float, default=1000.0, help="Initial capital")
    parser.add_argument("--iterations", type=int, default=100, help="Optimization iterations")
    parser.add_argument("--train-ml", action="store_true", help="Train ML model")
    parser.add_argument("--model-path", default="", help="Path to save ML model")
    parser.add_argument("--output", default="", help="Save results to JSON file")

    args = parser.parse_args()

    print("=" * 60)
    print("  ULTRA SCALPING BOT - OPTIMIZER")
    print("=" * 60)

    if args.train_ml:
        train_ml_model(args)
    else:
        optimize_parameters(args)


if __name__ == "__main__":
    main()
