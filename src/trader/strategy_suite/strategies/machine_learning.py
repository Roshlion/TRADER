"""
Machine Learning-based intraday trading strategy.

Uses ML classification to predict short-term price movements based on
technical indicators and features derived from minute-bar data.
"""

from typing import List, Dict, Any
import polars as pl
import numpy as np
from datetime import datetime
from .base import BaseStrategy, Signal, SignalAction


class MLClassifierStrategy(BaseStrategy):
    """
    ML-powered strategy using technical features to predict price direction.

    Parameters:
        threshold: Confidence threshold for trades (default: 0.55)
        lookback: Number of bars to look back for features (default: 30)
        train_pct: Percentage of data to use for training (default: 0.7)
        model_type: Type of model to use - 'rf' or 'gb' (default: 'gb')
    """

    name = "MLClassifierStrategy"

    def __init__(self, params: Dict[str, Any] = None):
        """Initialize ML strategy with parameters."""
        super().__init__(params)
        self.threshold = params.get('threshold', 0.55) if params else 0.55
        self.lookback = params.get('lookback', 30) if params else 30
        self.train_pct = params.get('train_pct', 0.7) if params else 0.7
        self.model_type = params.get('model_type', 'gb') if params else 'gb'
        self.model = None
        self.scaler = None

    def _calculate_rsi(self, close_prices: pl.Series, period: int = 14) -> pl.Series:
        """Calculate RSI indicator."""
        # Calculate price changes
        delta = close_prices.diff()

        # Separate gains and losses
        gains = delta.clip(lower_bound=0)
        losses = -delta.clip(upper_bound=0)

        # Calculate rolling averages
        avg_gain = gains.rolling_mean(window_size=period)
        avg_loss = losses.rolling_mean(window_size=period)

        # Calculate RS and RSI
        rs = avg_gain / (avg_loss + 1e-10)  # Add small value to avoid division by zero
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def _engineer_features(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Create technical features from OHLCV data.

        Features include:
        - Recent returns (1, 5, 10, 30 minutes)
        - Rolling volatility
        - Volume ratios
        - RSI
        - Price position in range
        """
        # Make a copy to avoid modifying original
        data = df.clone()

        # Sort by timestamp
        data = data.sort("timestamp")

        # Recent returns
        data = data.with_columns([
            (pl.col("close").pct_change(1)).alias("ret1"),
            (pl.col("close").pct_change(5)).alias("ret5"),
            (pl.col("close").pct_change(10)).alias("ret10"),
            (pl.col("close").pct_change(30)).alias("ret30"),
        ])

        # Rolling volatility (standard deviation of returns)
        data = data.with_columns([
            pl.col("ret1").rolling_std(window_size=20).alias("vol_20"),
            pl.col("ret1").rolling_std(window_size=60).alias("vol_60"),
        ])

        # Volume features
        data = data.with_columns([
            pl.col("volume").rolling_mean(window_size=20).alias("vol_ma_20"),
            pl.col("volume").rolling_mean(window_size=60).alias("vol_ma_60"),
        ])

        # Volume ratio (current / average)
        data = data.with_columns([
            (pl.col("volume") / (pl.col("vol_ma_20") + 1)).alias("vol_ratio_20"),
            (pl.col("volume") / (pl.col("vol_ma_60") + 1)).alias("vol_ratio_60"),
        ])

        # RSI
        rsi = self._calculate_rsi(data["close"], period=14)
        data = data.with_columns(rsi.alias("rsi_14"))

        # Price position in recent range (0 = at low, 1 = at high)
        rolling_high = data["high"].rolling_max(window_size=20)
        rolling_low = data["low"].rolling_min(window_size=20)
        data = data.with_columns([
            ((pl.col("close") - rolling_low) / (rolling_high - rolling_low + 1e-10)).alias("price_pos_20")
        ])

        # Time of day features (sin/cos encoding of minute index)
        # Assume market hours 9:30 AM to 4:00 PM (390 minutes)
        # Extract hour and minute from timestamp
        data = data.with_columns([
            pl.col("timestamp").dt.hour().alias("hour"),
            pl.col("timestamp").dt.minute().alias("minute"),
        ])

        # Calculate minute index (0-390)
        data = data.with_columns([
            ((pl.col("hour") - 9) * 60 + pl.col("minute") - 30).alias("minute_idx")
        ])

        # Sin/cos encoding for cyclical time feature
        data = data.with_columns([
            (2 * np.pi * pl.col("minute_idx") / 390).sin().alias("time_sin"),
            (2 * np.pi * pl.col("minute_idx") / 390).cos().alias("time_cos"),
        ])

        return data

    def _create_labels(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Create target labels for training.

        Label = 1 if next minute's close > current close, else 0
        """
        data = df.clone()

        # Future return (next minute)
        data = data.with_columns([
            pl.col("close").shift(-1).alias("close_next")
        ])

        # Create binary label
        data = data.with_columns([
            (pl.col("close_next") > pl.col("close")).cast(pl.Int32).alias("label")
        ])

        return data

    def _train_model(self, X: np.ndarray, y: np.ndarray):
        """Train ML model on features and labels."""
        from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
        from sklearn.preprocessing import StandardScaler

        # Scale features
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        # Train model
        if self.model_type == 'rf':
            self.model = RandomForestClassifier(
                n_estimators=100,
                max_depth=5,
                random_state=42,
                n_jobs=-1
            )
        else:  # 'gb'
            self.model = GradientBoostingClassifier(
                n_estimators=100,
                max_depth=3,
                random_state=42
            )

        self.model.fit(X_scaled, y)

    def generate_signals(self, data: pl.DataFrame) -> List[Signal]:
        """
        Generate trading signals using ML predictions.

        Returns:
            List of Signal objects
        """
        if len(data) < self.lookback + 1:
            return []  # Not enough data

        signals = []

        # Filter to single ticker if multiple present
        tickers = data["ticker"].unique().to_list()
        if len(tickers) > 1:
            # Process first ticker only for simplicity
            # In production, would handle multi-ticker properly
            ticker = tickers[0]
            data = data.filter(pl.col("ticker") == ticker)
        else:
            ticker = tickers[0]

        # Engineer features
        data_with_features = self._engineer_features(data)

        # Create labels
        data_with_labels = self._create_labels(data_with_features)

        # Define feature columns
        feature_cols = [
            "ret1", "ret5", "ret10", "ret30",
            "vol_20", "vol_60",
            "vol_ratio_20", "vol_ratio_60",
            "rsi_14",
            "price_pos_20",
            "time_sin", "time_cos"
        ]

        # Drop rows with NaN values
        data_clean = data_with_labels.drop_nulls(subset=feature_cols + ["label"])

        if len(data_clean) < self.lookback:
            return []  # Not enough valid data after cleaning

        # Extract features and labels as numpy arrays
        X = data_clean.select(feature_cols).to_numpy()
        y = data_clean.select("label").to_numpy().ravel()
        timestamps = data_clean.select("timestamp").to_series().to_list()
        closes = data_clean.select("close").to_series().to_list()

        # Split into train and prediction sets
        train_size = int(len(X) * self.train_pct)

        if train_size < self.lookback:
            return []  # Not enough training data

        X_train = X[:train_size]
        y_train = y[:train_size]

        # Train model on training data
        self._train_model(X_train, y_train)

        # Generate signals for the remaining period
        # Note: In production, should use walk-forward approach
        # For now, predict on all data after training period
        X_pred = X[train_size:]
        timestamps_pred = timestamps[train_size:]
        closes_pred = closes[train_size:]

        if len(X_pred) == 0:
            return []

        # Scale and predict
        X_pred_scaled = self.scaler.transform(X_pred)
        predictions_proba = self.model.predict_proba(X_pred_scaled)

        # Generate signals based on probability threshold
        for i in range(len(predictions_proba) - 1):  # -1 because we exit next bar
            prob_up = predictions_proba[i][1]  # Probability of class 1 (price up)
            timestamp = timestamps_pred[i]
            price = closes_pred[i]

            # Buy signal if high confidence of up move
            if prob_up > self.threshold:
                signals.append(Signal(
                    timestamp=timestamp,
                    ticker=ticker,
                    action=SignalAction.BUY,
                    size=1.0,
                    price=price,
                    confidence=prob_up,
                    reason=f"ML predicts up (p={prob_up:.2f})"
                ))

                # Exit signal at next bar
                if i + 1 < len(timestamps_pred):
                    signals.append(Signal(
                        timestamp=timestamps_pred[i + 1],
                        ticker=ticker,
                        action=SignalAction.SELL,
                        size=1.0,
                        price=closes_pred[i + 1],
                        confidence=1.0,
                        reason="ML exit"
                    ))

            # Short signal if high confidence of down move
            elif prob_up < (1 - self.threshold):
                signals.append(Signal(
                    timestamp=timestamp,
                    ticker=ticker,
                    action=SignalAction.SHORT,
                    size=1.0,
                    price=price,
                    confidence=1 - prob_up,
                    reason=f"ML predicts down (p={1-prob_up:.2f})"
                ))

                # Cover signal at next bar
                if i + 1 < len(timestamps_pred):
                    signals.append(Signal(
                        timestamp=timestamps_pred[i + 1],
                        ticker=ticker,
                        action=SignalAction.COVER,
                        size=1.0,
                        price=closes_pred[i + 1],
                        confidence=1.0,
                        reason="ML exit"
                    ))

        return signals
