"""
OptimalStrategy wrapper that loads best portfolio configuration and combines signals.
"""

import json
from typing import List, Dict, Any
from pathlib import Path
import polars as pl
import numpy as np

from ..strategies.base import BaseStrategy, Signal, SignalAction

# Import all strategies
from ..strategies.opening_range import ORB
from ..strategies.volatility_breakout import ATRBreakout
from ..strategies.vwap_bands import VWAPBands
from ..strategies.bollinger_revert import BollRevert
from ..strategies.intraday_seasonality import Seasonality
from ..strategies.cross_sectional_momo import CSM
from ..strategies.kalman_pairs import KalPairs
from ..strategies.kf_trend import KFTrend
from ..strategies.momentum import BreakoutMomentumStrategy, VolumeSpikeStrategy
from ..strategies.mean_reversion import VWAPReversionStrategy, BollingerBandStrategy
from ..strategies.stat_arb import PairsTradingStrategy


# Strategy registry
STRATEGY_REGISTRY = {
    "ORB": ORB,
    "ATRBreakout": ATRBreakout,
    "VWAPBands": VWAPBands,
    "BollRevert": BollRevert,
    "Seasonality": Seasonality,
    "CSM": CSM,
    "KalPairs": KalPairs,
    "KFTrend": KFTrend,
    "BreakoutMomentum": BreakoutMomentumStrategy,
    "VolumeSpike": VolumeSpikeStrategy,
    "VWAPReversion": VWAPReversionStrategy,
    "BollingerBand": BollingerBandStrategy,
    "PairsTrading": PairsTradingStrategy,
}


class OptimalStrategy(BaseStrategy):
    """
    Wrapper that loads best portfolio configuration and combines multiple strategies.

    Can load:
    - Single strategy with best params from sweep
    - Multi-strategy portfolio with weights
    """

    def __init__(self, params: Dict[str, Any] = None):
        """
        Initialize optimal strategy.

        Args:
            params: Dictionary with optional keys:
                - config_file: Path to portfolio config JSON
                - default_config: If config_file not found, use this
        """
        default_params = {
            "config_file": "artifacts/portfolios/best_weights.json",
            "default_config": None,
        }

        if params:
            default_params.update(params)

        super().__init__("OptimalStrategy", default_params)

        # Load configuration
        self.config = self._load_config()

        # Initialize sub-strategies
        self.strategies = self._init_strategies()

    def _load_config(self) -> Dict[str, Any]:
        """Load portfolio configuration."""
        config_file = self.params["config_file"]

        if Path(config_file).exists():
            with open(config_file, 'r') as f:
                config = json.load(f)
            print(f"Loaded optimal portfolio config from {config_file}")
            return config

        elif self.params["default_config"]:
            config = self.params["default_config"]
            print("Using provided default config")
            return config

        else:
            # Fallback: use single default strategy
            print(f"Warning: Config file {config_file} not found. Using default ORB strategy.")
            return {
                "strategies": {
                    "ORB": {
                        "weight": 1.0,
                        "params": {}
                    }
                }
            }

    def _init_strategies(self) -> Dict[str, BaseStrategy]:
        """Initialize sub-strategies from config."""
        strategies = {}

        for strategy_name, strategy_config in self.config.get("strategies", {}).items():
            # Get strategy class
            strategy_cls = STRATEGY_REGISTRY.get(strategy_name)

            if strategy_cls is None:
                print(f"Warning: Unknown strategy '{strategy_name}', skipping")
                continue

            # Get parameters
            strat_params = strategy_config.get("params", {})

            # Instantiate
            strategy = strategy_cls(params=strat_params)
            strategies[strategy_name] = strategy

            weight = strategy_config.get("weight", 0.0)
            print(f"  Initialized {strategy_name} (weight: {weight:.2f})")

        return strategies

    def generate_signals(self, data: pl.DataFrame) -> List[Signal]:
        """
        Generate combined signals from all sub-strategies.

        Signals are weighted and aggregated. For now, we use a simple approach:
        - Each strategy generates its signals independently
        - We combine them by weighting signal strength/size
        - Conflicts are resolved by highest weight strategy

        Args:
            data: Market data

        Returns:
            List of aggregated signals
        """
        all_signals = {}  # (timestamp, ticker, action) -> signal list

        # Generate signals from each strategy
        for strategy_name, strategy in self.strategies.items():
            weight = self.config["strategies"][strategy_name].get("weight", 0.0)

            if weight == 0:
                continue

            try:
                signals = strategy.generate_signals(data)

                # Weight the signals
                for sig in signals:
                    key = (sig.timestamp, sig.ticker, sig.action)

                    if key not in all_signals:
                        all_signals[key] = []

                    # Adjust size by weight
                    weighted_sig = Signal(
                        timestamp=sig.timestamp,
                        ticker=sig.ticker,
                        action=sig.action,
                        size=sig.size * weight,
                        price=sig.price,
                        confidence=sig.confidence if sig.confidence else weight,
                        reason=f"[{strategy_name}:{weight:.2f}] {sig.reason}",
                        indicators=sig.indicators
                    )

                    all_signals[key].append(weighted_sig)

            except Exception as e:
                print(f"  Warning: {strategy_name} failed to generate signals: {e}")

        # Aggregate signals
        final_signals = []

        for key, signal_list in all_signals.items():
            if len(signal_list) == 1:
                # Single signal
                final_signals.append(signal_list[0])
            else:
                # Multiple signals for same (timestamp, ticker, action) - combine
                combined_size = sum(s.size for s in signal_list)
                combined_conf = np.mean([s.confidence for s in signal_list if s.confidence])
                reasons = "; ".join([s.reason for s in signal_list])

                combined_sig = Signal(
                    timestamp=signal_list[0].timestamp,
                    ticker=signal_list[0].ticker,
                    action=signal_list[0].action,
                    size=combined_size,
                    price=signal_list[0].price,
                    confidence=combined_conf,
                    reason=f"Combined: {reasons}",
                    indicators=signal_list[0].indicators
                )

                final_signals.append(combined_sig)

        # Sort by timestamp
        final_signals.sort(key=lambda s: s.timestamp)

        return final_signals


def create_portfolio_config(
    weights: Dict[str, float],
    strategy_params: Dict[str, Dict[str, Any]],
    out_file: str = "artifacts/portfolios/best_weights.json"
):
    """
    Create and save portfolio configuration file.

    Args:
        weights: Dictionary of strategy_name -> weight
        strategy_params: Dictionary of strategy_name -> params dict
        out_file: Output file path
    """
    config = {
        "strategies": {}
    }

    for strategy_name, weight in weights.items():
        config["strategies"][strategy_name] = {
            "weight": weight,
            "params": strategy_params.get(strategy_name, {})
        }

    # Save
    Path(out_file).parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, 'w') as f:
        json.dump(config, f, indent=2)

    print(f"Portfolio config saved to {out_file}")

    return config
