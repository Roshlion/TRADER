"""
Meta-learning selector for dynamic strategy weighting using ML.
"""

import numpy as np
import pandas as pd
import pickle
from pathlib import Path
from typing import Dict, Tuple, Optional
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit


class MetaSelector:
    """
    ML-based meta-selector for strategy weighting.

    Trains a model to predict which strategy will perform best or
    predict optimal weights based on features.
    """

    def __init__(
        self,
        strat_returns: pd.DataFrame,
        mode: str = 'classifier',
        lookback: int = 20,
        n_splits: int = 3
    ):
        """
        Initialize meta selector.

        Args:
            strat_returns: DataFrame with strategy returns (columns = strategies)
            mode: 'classifier' (pick best) or 'regressor' (weight by predicted return)
            lookback: Number of periods to look back for features
            n_splits: Number of time-series CV splits
        """
        self.strat_returns = strat_returns
        self.strategy_names = list(strat_returns.columns)
        self.n_strategies = len(self.strategy_names)
        self.mode = mode
        self.lookback = lookback
        self.n_splits = n_splits

        self.model = None
        self.scaler = StandardScaler()
        self.is_trained = False

    def _extract_features(self, idx: int) -> np.ndarray:
        """
        Extract features for time step idx.

        Features include:
        - Last k returns per strategy
        - Rolling volatility per strategy
        - Cross-sectional rank
        - Time of day (sin/cos encoded)

        Args:
            idx: Index in returns dataframe

        Returns:
            Feature vector
        """
        if idx < self.lookback:
            return None

        features = []

        # Get lookback window
        window = self.strat_returns.iloc[idx-self.lookback:idx]

        # Per-strategy features
        for col in self.strategy_names:
            col_data = window[col].values

            # Recent returns (last 5)
            features.extend(col_data[-5:])

            # Rolling volatility
            features.append(np.std(col_data))

            # Cumulative return over window
            features.append(np.prod(1 + col_data) - 1)

        # Cross-sectional features
        last_returns = window.iloc[-1].values
        ranks = pd.Series(last_returns).rank(pct=True).values
        features.extend(ranks)

        # Time features (if datetime index)
        if hasattr(self.strat_returns.index[idx], 'hour'):
            hour = self.strat_returns.index[idx].hour
            minute = self.strat_returns.index[idx].minute
            time_of_day = hour + minute / 60
            features.append(np.sin(2 * np.pi * time_of_day / 24))
            features.append(np.cos(2 * np.pi * time_of_day / 24))
        else:
            features.extend([0, 0])

        return np.array(features)

    def _get_target(self, idx: int) -> int:
        """
        Get target for classifier mode: index of best-performing strategy next period.

        Args:
            idx: Current index

        Returns:
            Strategy index with highest return at idx+1
        """
        if idx + 1 >= len(self.strat_returns):
            return None

        next_returns = self.strat_returns.iloc[idx + 1].values
        best_idx = np.argmax(next_returns)

        return best_idx

    def train(self):
        """Train the meta model using walk-forward approach."""
        print(f"Training meta selector ({self.mode})...")

        # Prepare data
        X_list = []
        y_list = []

        for idx in range(self.lookback, len(self.strat_returns) - 1):
            features = self._extract_features(idx)

            if features is None:
                continue

            if self.mode == 'classifier':
                target = self._get_target(idx)
                if target is None:
                    continue
                y_list.append(target)
            else:  # regressor
                # Target = next period returns for all strategies
                next_returns = self.strat_returns.iloc[idx + 1].values
                y_list.append(next_returns)

            X_list.append(features)

        X = np.array(X_list)
        y = np.array(y_list)

        if len(X) == 0:
            raise ValueError("No training data generated")

        print(f"  Training samples: {len(X)}")
        print(f"  Features: {X.shape[1]}")

        # Standardize features
        X_scaled = self.scaler.fit_transform(X)

        # Train model
        if self.mode == 'classifier':
            self.model = GradientBoostingClassifier(
                n_estimators=100,
                max_depth=3,
                learning_rate=0.1,
                random_state=42
            )
            self.model.fit(X_scaled, y)

            # Report accuracy
            y_pred = self.model.predict(X_scaled)
            accuracy = np.mean(y_pred == y)
            print(f"  Training accuracy: {accuracy:.3f}")

        else:  # regressor
            # Train one regressor per strategy
            self.model = []
            for s_idx in range(self.n_strategies):
                model = GradientBoostingRegressor(
                    n_estimators=100,
                    max_depth=3,
                    learning_rate=0.1,
                    random_state=42
                )
                model.fit(X_scaled, y[:, s_idx])
                self.model.append(model)

            print(f"  Trained {len(self.model)} regressors")

        self.is_trained = True

    def predict_weights(self, idx: int) -> Dict[str, float]:
        """
        Predict weights for time step idx.

        Args:
            idx: Index in returns dataframe

        Returns:
            Dictionary of strategy -> weight
        """
        if not self.is_trained:
            raise ValueError("Model not trained yet")

        features = self._extract_features(idx)

        if features is None:
            # Return equal weights if can't extract features
            return {s: 1.0 / self.n_strategies for s in self.strategy_names}

        X = features.reshape(1, -1)
        X_scaled = self.scaler.transform(X)

        if self.mode == 'classifier':
            # Predict best strategy, give it full weight
            pred_idx = self.model.predict(X_scaled)[0]

            # Get probabilities for softer allocation
            probs = self.model.predict_proba(X_scaled)[0]

            weights = dict(zip(self.strategy_names, probs))

        else:  # regressor
            # Predict returns for each strategy
            pred_returns = []
            for model in self.model:
                pred_ret = model.predict(X_scaled)[0]
                pred_returns.append(max(pred_ret, 0))  # Floor at 0

            # Convert to weights
            total = sum(pred_returns)
            if total > 0:
                weights = {s: r / total for s, r in zip(self.strategy_names, pred_returns)}
            else:
                weights = {s: 1.0 / self.n_strategies for s in self.strategy_names}

        return weights

    def backtest(self) -> Tuple[pd.Series, pd.DataFrame]:
        """
        Backtest meta selector.

        Returns:
            Tuple of (portfolio_returns, weights_timeseries)
        """
        if not self.is_trained:
            self.train()

        portfolio_returns = []
        weights_list = []

        for idx in range(self.lookback, len(self.strat_returns)):
            # Predict weights
            weights_dict = self.predict_weights(idx)
            weights = np.array([weights_dict.get(s, 0) for s in self.strategy_names])

            # Calculate return
            strat_ret = self.strat_returns.iloc[idx].values
            port_ret = np.dot(weights, strat_ret)

            portfolio_returns.append(port_ret)
            weights_list.append(weights)

        portfolio_returns = pd.Series(
            portfolio_returns,
            index=self.strat_returns.index[self.lookback:]
        )

        weights_df = pd.DataFrame(
            weights_list,
            index=self.strat_returns.index[self.lookback:],
            columns=self.strategy_names
        )

        return portfolio_returns, weights_df

    def save(self, path: str):
        """Save model to disk."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)

        with open(path, 'wb') as f:
            pickle.dump({
                'model': self.model,
                'scaler': self.scaler,
                'strategy_names': self.strategy_names,
                'mode': self.mode,
                'lookback': self.lookback
            }, f)

        print(f"Model saved to {path}")

    @classmethod
    def load(cls, path: str, strat_returns: pd.DataFrame):
        """Load model from disk."""
        with open(path, 'rb') as f:
            data = pickle.load(f)

        selector = cls(strat_returns, mode=data['mode'], lookback=data['lookback'])
        selector.model = data['model']
        selector.scaler = data['scaler']
        selector.strategy_names = data['strategy_names']
        selector.is_trained = True

        print(f"Model loaded from {path}")

        return selector
