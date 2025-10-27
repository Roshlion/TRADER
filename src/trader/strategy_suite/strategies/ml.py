"""
Machine Learning-based trading strategies.

Strategies that use predictive models to classify short-term price direction
or volatility and trade based on model predictions.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import polars as pl
import numpy as np
from .base import BaseStrategy, Signal, SignalAction, validate_data


class MLClassifierStrategy(BaseStrategy):
    """
    ML classifier-based strategy.

    Uses a pre-trained classification model to predict price direction.
    Trades based on model confidence.

    Parameters:
        model: Pre-trained model with predict_proba method (e.g., sklearn classifier)
        feature_columns: List of column names to use as features
        confidence_threshold: Minimum prediction confidence to trade (default: 0.7)
        holding_period: Bars to hold position (default: 10)
        use_technical_features: Whether to calculate technical indicators (default: True)

    Note: This is a template. You'll need to train a model separately and pass it in.
    """

    def __init__(self, params: Dict[str, Any] = None):
        default_params = {
            "model": None,  # Must be provided
            "feature_columns": None,
            "confidence_threshold": 0.7,
            "holding_period": 10,
            "use_technical_features": True,
        }
        if params:
            default_params.update(params)
        super().__init__("MLClassifierStrategy", default_params)

        if self.params["model"] is None:
            # Create a simple dummy model for demonstration
            self.params["model"] = DummyClassifier()

    def generate_signals(self, data: pl.DataFrame) -> List[Signal]:
        """Generate ML-based signals."""
        validate_data(data, ["timestamp", "ticker", "open", "high", "low", "close", "volume"])

        model = self.params["model"]
        confidence_thresh = self.params["confidence_threshold"]
        holding_period = self.params["holding_period"]

        signals = []

        # Group by ticker
        for ticker in data["ticker"].unique():
            ticker_data = data.filter(pl.col("ticker") == ticker).sort("timestamp")

            # Generate features
            if self.params["use_technical_features"]:
                ticker_data = self._calculate_technical_features(ticker_data)

            # Get feature columns
            feature_cols = self.params["feature_columns"]
            if feature_cols is None:
                # Use all technical features by default
                feature_cols = [
                    "returns_1", "returns_5", "rsi", "ma_ratio",
                    "volume_ratio", "volatility"
                ]

            # Ensure all feature columns exist
            available_features = [col for col in feature_cols if col in ticker_data.columns]
            if not available_features:
                continue

            # Prepare features for prediction
            feature_data = ticker_data.select(available_features).to_numpy()

            # Handle NaN values (from rolling windows)
            valid_idx = ~np.isnan(feature_data).any(axis=1)

            if not np.any(valid_idx):
                continue

            # Make predictions on valid rows
            predictions = np.full(len(ticker_data), -1)
            probabilities = np.zeros((len(ticker_data), 2))

            try:
                # Predict probability of up (class 1) vs down (class 0)
                probs = model.predict_proba(feature_data[valid_idx])
                probabilities[valid_idx] = probs

                # Class 1 = Up, Class 0 = Down
                predictions[valid_idx] = (probs[:, 1] > 0.5).astype(int)
            except Exception as e:
                # Model prediction failed, skip this ticker
                continue

            # Add predictions to dataframe
            ticker_data = ticker_data.with_columns([
                pl.Series("prediction", predictions),
                pl.Series("prob_up", probabilities[:, 1]),
                pl.Series("prob_down", probabilities[:, 0]),
            ])

            # Generate signals based on predictions
            position = None
            position_entry_idx = None

            for i, row in enumerate(ticker_data.iter_rows(named=True)):
                if row["prediction"] == -1:  # Invalid prediction
                    continue

                prob_up = row["prob_up"]
                prob_down = row["prob_down"]

                # Strong buy signal
                if prob_up > confidence_thresh and position != "long":
                    # Close short if open
                    if position == "short":
                        signals.append(Signal(
                            timestamp=row["timestamp"],
                            ticker=ticker,
                            action=SignalAction.COVER,
                            size=1.0,
                            price=row["close"],
                            reason="ML model predicts reversal"
                        ))

                    # Enter long
                    signals.append(Signal(
                        timestamp=row["timestamp"],
                        ticker=ticker,
                        action=SignalAction.BUY,
                        size=1.0,
                        price=row["close"],
                        confidence=prob_up,
                        reason=f"ML predicts up with {prob_up:.2%} confidence",
                        indicators={
                            "prob_up": prob_up,
                            "prob_down": prob_down,
                        }
                    ))
                    position = "long"
                    position_entry_idx = i

                # Strong sell signal
                elif prob_down > confidence_thresh and position != "short":
                    # Close long if open
                    if position == "long":
                        signals.append(Signal(
                            timestamp=row["timestamp"],
                            ticker=ticker,
                            action=SignalAction.SELL,
                            size=1.0,
                            price=row["close"],
                            reason="ML model predicts reversal"
                        ))

                    # Enter short
                    signals.append(Signal(
                        timestamp=row["timestamp"],
                        ticker=ticker,
                        action=SignalAction.SHORT,
                        size=1.0,
                        price=row["close"],
                        confidence=prob_down,
                        reason=f"ML predicts down with {prob_down:.2%} confidence",
                        indicators={
                            "prob_up": prob_up,
                            "prob_down": prob_down,
                        }
                    ))
                    position = "short"
                    position_entry_idx = i

                # Exit on holding period
                elif position and position_entry_idx is not None:
                    if i - position_entry_idx >= holding_period:
                        if position == "long":
                            signals.append(Signal(
                                timestamp=row["timestamp"],
                                ticker=ticker,
                                action=SignalAction.SELL,
                                size=1.0,
                                price=row["close"],
                                reason=f"Holding period ({holding_period} bars) reached"
                            ))
                        elif position == "short":
                            signals.append(Signal(
                                timestamp=row["timestamp"],
                                ticker=ticker,
                                action=SignalAction.COVER,
                                size=1.0,
                                price=row["close"],
                                reason=f"Holding period ({holding_period} bars) reached"
                            ))
                        position = None
                        position_entry_idx = None

        return signals

    def _calculate_technical_features(self, data: pl.DataFrame) -> pl.DataFrame:
        """Calculate technical indicator features for ML model."""
        # Returns
        data = data.with_columns([
            ((pl.col("close") - pl.col("close").shift(1)) / pl.col("close").shift(1)).alias("returns_1"),
            ((pl.col("close") - pl.col("close").shift(5)) / pl.col("close").shift(5)).alias("returns_5"),
        ])

        # RSI
        delta = data["close"].diff()
        gain = delta.clip_min(0)
        loss = (-delta).clip_min(0)
        avg_gain = gain.rolling_mean(14)
        avg_loss = loss.rolling_mean(14)
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        data = data.with_columns([pl.Series("rsi", rsi)])

        # Moving average ratio
        data = data.with_columns([
            (pl.col("close") / pl.col("close").rolling_mean(20)).alias("ma_ratio"),
        ])

        # Volume ratio
        data = data.with_columns([
            (pl.col("volume") / pl.col("volume").rolling_mean(20)).alias("volume_ratio"),
        ])

        # Volatility (rolling std of returns)
        data = data.with_columns([
            pl.col("returns_1").rolling_std(20).alias("volatility"),
        ])

        return data


class DummyClassifier:
    """
    Dummy classifier for demonstration purposes.

    Predicts based on simple momentum: if recent returns are positive,
    predict up; otherwise predict down.
    """

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """
        Predict probability of up/down.

        Args:
            X: Feature matrix (n_samples, n_features)

        Returns:
            Array of shape (n_samples, 2) with [prob_down, prob_up]
        """
        # Simple heuristic: use first feature (returns_1) as signal
        if X.shape[1] == 0:
            return np.array([[0.5, 0.5]] * len(X))

        returns = X[:, 0]  # Assume first feature is returns

        # Convert returns to probabilities
        probs_up = 1 / (1 + np.exp(-10 * returns))  # Sigmoid function
        probs_down = 1 - probs_up

        return np.column_stack([probs_down, probs_up])


# Example of how to use a real sklearn model:
"""
from sklearn.ensemble import RandomForestClassifier

# Train your model
model = RandomForestClassifier(n_estimators=100, random_state=42)
X_train, y_train = prepare_training_data()  # Your training data
model.fit(X_train, y_train)

# Use in strategy
strategy = MLClassifierStrategy(params={
    "model": model,
    "feature_columns": ["returns_1", "returns_5", "rsi", "ma_ratio", "volume_ratio", "volatility"],
    "confidence_threshold": 0.75,
    "holding_period": 15,
})
"""
