"""
Ultra Scalping Bot - ML Signal Predictor & Parameter Optimizer
Machine Learning para predecir senales de trading y optimizar parametros.
"""

import logging
import time
import random
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass

import numpy as np
import pandas as pd

try:
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import cross_val_score, TimeSeriesSplit
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
    import joblib
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False

logger = logging.getLogger(__name__)


class MLSignalPredictor:
    """Predictor de senales basado en Gradient Boosting."""

    def __init__(self, n_estimators: int = 200, max_depth: int = 5, learning_rate: float = 0.05):
        if not ML_AVAILABLE:
            raise ImportError("pip install scikit-learn joblib")
        self.model = GradientBoostingClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            subsample=0.8,
            random_state=42,
        )
        self.scaler = StandardScaler()
        self.feature_names: List[str] = []
        self.is_trained = False

    def _extract_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Extrae features del DataFrame de precios."""
        features = pd.DataFrame(index=df.index)

        # Price returns
        features["return_1"] = df["close"].pct_change(1)
        features["return_3"] = df["close"].pct_change(3)
        features["return_5"] = df["close"].pct_change(5)
        features["return_10"] = df["close"].pct_change(10)

        # Moving averages
        features["sma_ratio_5_20"] = df["close"].rolling(5).mean() / df["close"].rolling(20).mean()
        features["ema_ratio_9_21"] = df["close"].ewm(span=9).mean() / df["close"].ewm(span=21).mean()

        # Volatility
        features["volatility_5"] = df["close"].rolling(5).std() / df["close"].rolling(5).mean()
        features["volatility_20"] = df["close"].rolling(20).std() / df["close"].rolling(20).mean()
        features["atr_ratio"] = (df["high"] - df["low"]) / df["close"]

        # RSI
        delta = df["close"].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / (loss + 1e-10)
        features["rsi"] = 100 - (100 / (1 + rs))

        # Volume features
        features["volume_ratio"] = df["volume"] / df["volume"].rolling(20).mean()
        features["volume_change"] = df["volume"].pct_change(1)

        # Momentum
        features["momentum_10"] = df["close"] / df["close"].shift(10) - 1

        # Bollinger Band position
        bb_mid = df["close"].rolling(20).mean()
        bb_std = df["close"].rolling(20).std()
        features["bb_position"] = (df["close"] - bb_mid) / (2 * bb_std + 1e-10)

        self.feature_names = list(features.columns)
        return features

    def _create_labels(self, df: pd.DataFrame, lookahead: int = 5, threshold: float = 0.001) -> pd.Series:
        """Crea etiquetas: 1 = precio sube, 0 = baja."""
        future_return = df["close"].shift(-lookahead) / df["close"] - 1
        labels = (future_return > threshold).astype(int)
        return labels
    def train(self, df: pd.DataFrame) -> Dict[str, float]:
        """Entrena el modelo con datos historicos."""
        logger.info("Entrenando modelo ML...")

        features = self._extract_features(df)
        labels = self._create_labels(df)

        # Drop NaN rows
        valid = features.dropna().index.intersection(labels.dropna().index)
        X = features.loc[valid].values
        y = labels.loc[valid].values

        if len(X) < 100:
            logger.warning("Insufficient data for training")
            return {"error": "insufficient_data"}

        # Scale features
        X_scaled = self.scaler.fit_transform(X)

        # Time series cross-validation
        tscv = TimeSeriesSplit(n_splits=5)
        cv_scores = cross_val_score(self.model, X_scaled, y, cv=tscv, scoring="accuracy")

        # Train on all data
        self.model.fit(X_scaled, y)
        self.is_trained = True

        # Evaluate
        y_pred = self.model.predict(X_scaled)
        metrics = {
            "accuracy": accuracy_score(y, y_pred),
            "precision": precision_score(y, y_pred, zero_division=0),
            "recall": recall_score(y, y_pred, zero_division=0),
            "f1": f1_score(y, y_pred, zero_division=0),
            "cv_mean": float(np.mean(cv_scores)),
            "cv_std": float(np.std(cv_scores)),
            "samples": len(X),
            "features": len(self.feature_names),
        }

        # Feature importance
        importance = dict(zip(self.feature_names, self.model.feature_importances_))
        metrics["top_features"] = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True)[:5])

        logger.info(f"Model trained: accuracy={metrics['accuracy']:.3f} cv={metrics['cv_mean']:.3f}")
        return metrics

    def predict(self, df: pd.DataFrame) -> float:
        """Predice probabilidad de subida."""
        if not self.is_trained:
            return 0.5
        features = self._extract_features(df)
        last_features = features.iloc[-1:].values
        if np.any(np.isnan(last_features)):
            return 0.5
        X_scaled = self.scaler.transform(last_features)
        proba = self.model.predict_proba(X_scaled)[0]
        return float(proba[1]) if len(proba) > 1 else 0.5

    def save(self, filepath: str):
        """Guarda el modelo."""
        joblib.dump({"model": self.model, "scaler": self.scaler, "features": self.feature_names}, filepath)

    def load(self, filepath: str):
        """Carga un modelo guardado."""
        data = joblib.load(filepath)
        self.model = data["model"]
        self.scaler = data["scaler"]
        self.feature_names = data["features"]
        self.is_trained = True

class ParameterOptimizer:
    """Optimizador de parametros mediante busqueda aleatoria."""

    PARAM_RANGES = {
        "ema_fast": (3, 15),
        "ema_medium": (10, 30),
        "ema_slow": (20, 60),
        "rsi_period": (7, 21),
        "rsi_oversold": (20, 40),
        "rsi_overbought": (60, 80),
        "atr_period": (7, 21),
        "take_profit_pct": (0.1, 1.0),
        "stop_loss_pct": (0.1, 0.5),
    }

    def __init__(self, config=None):
        self.config = config
        self.best_params: Dict = {}
        self.best_score: float = -999
        self.all_results: List[Dict] = []

    def _random_params(self) -> Dict:
        """Genera parametros aleatorios."""
        params = {}
        for name, (low, high) in self.PARAM_RANGES.items():
            if isinstance(low, int):
                params[name] = random.randint(low, high)
            else:
                params[name] = round(random.uniform(low, high), 4)
        return params

    def _score(self, results: Dict) -> float:
        """Calcula score compuesto de un backtest."""
        pnl_pct = results.get("total_pnl_pct", 0)
        win_rate = results.get("win_rate", 0)
        sharpe = results.get("sharpe_ratio", 0)
        max_dd = results.get("max_drawdown_pct", 0)
        trades = results.get("total_trades", 0)

        if trades < 10:
            return -999

        score = (
            pnl_pct * 0.3
            + win_rate * 0.2
            + sharpe * 10 * 0.2
            - abs(max_dd) * 0.2
            + min(trades, 100) * 0.001 * 0.1
        )
        return score

    def optimize(self, data, n_iterations: int = 100) -> Tuple[Dict, float, List[Dict]]:
        """Ejecuta optimizacion por busqueda aleatoria."""
        from core.backtester import Backtester
        from core.strategies import CombinedStrategy

        logger.info(f"Starting optimization with {n_iterations} iterations")

        for i in range(n_iterations):
            params = self._random_params()

            try:
                if self.config:
                    self.config.strategy.ema_fast = params.get("ema_fast", 8)
                    self.config.strategy.ema_medium = params.get("ema_medium", 21)
                    self.config.strategy.ema_slow = params.get("ema_slow", 50)
                    self.config.strategy.rsi_period = params.get("rsi_period", 14)
                    self.config.strategy.rsi_oversold = params.get("rsi_oversold", 30)
                    self.config.strategy.rsi_overbought = params.get("rsi_overbought", 70)

                strategy = CombinedStrategy(self.config.strategy if self.config else None)
                backtester = Backtester(self.config)
                results = backtester.run(data, strategy)

                score = self._score(results)
                self.all_results.append({"params": params, "score": score, "results": results})

                if score > self.best_score:
                    self.best_score = score
                    self.best_params = params
                    logger.info(f"  New best: score={score:.4f} params={params}")

                if (i + 1) % 10 == 0:
                    logger.info(f"  Progress: {i+1}/{n_iterations} best={self.best_score:.4f}")

            except Exception as e:
                logger.warning(f"  Iteration {i+1} failed: {e}")

        logger.info(f"Optimization complete. Best score: {self.best_score:.4f}")
        return self.best_params, self.best_score, self.all_results
