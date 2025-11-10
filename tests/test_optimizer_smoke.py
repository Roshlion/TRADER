"""
Smoke tests for optimizer modules.

Quick tests to ensure all optimizer components compile and run without errors.
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from trader.strategy_suite.optimizer.weights import StaticOptimizer, optimize_portfolio
from trader.strategy_suite.optimizer.walk_forward import WalkForwardValidator
from trader.strategy_suite.optimizer.turnover import calculate_turnover, add_turnover_metrics
from trader.strategy_suite.optimizer.regime import RegimeDetector, blend_with_regime_scores
from trader.strategy_suite.optimizer.meta import MetaSelector


def generate_sample_returns(n_periods=100, n_strategies=3):
    """Generate sample returns data for testing."""
    np.random.seed(42)
    dates = pd.date_range('2025-01-01', periods=n_periods, freq='1min')
    data = np.random.randn(n_periods, n_strategies) * 0.001  # Small returns
    returns_df = pd.DataFrame(data, index=dates, columns=[f"Strategy_{i}" for i in range(n_strategies)])
    return returns_df


def test_static_optimizer():
    """Test StaticOptimizer basic functionality."""
    print("Testing StaticOptimizer...")

    returns_df = generate_sample_returns()
    optimizer = StaticOptimizer(returns_df)

    # Test equal weights
    weights, port_returns, metrics = optimizer.equal()
    assert len(weights) == 3
    assert abs(sum(weights.values()) - 1.0) < 1e-6
    print("  [PASS] Equal weights")

    # Test risk parity
    weights, port_returns, metrics = optimizer.risk_parity()
    assert len(weights) == 3
    assert abs(sum(weights.values()) - 1.0) < 1e-6
    print("  [PASS] Risk parity")

    # Test mean-variance (Sharpe)
    weights, port_returns, metrics = optimizer.mean_variance(objective='sharpe')
    assert len(weights) == 3
    assert abs(sum(weights.values()) - 1.0) < 1e-6
    print("  [PASS] Mean-variance (Sharpe)")

    print("  StaticOptimizer: PASS\n")


def test_walk_forward_validator():
    """Test WalkForwardValidator basic functionality."""
    print("Testing WalkForwardValidator...")

    returns_df = generate_sample_returns(n_periods=50)

    # Create validator
    wfv = WalkForwardValidator(
        returns_df,
        train_days=10,
        test_days=5,
        overlap_days=0
    )

    # Run validation
    results = wfv.run(objective='sharpe')

    assert 'folds' in results
    assert 'summary' in results
    assert len(results['folds']) > 0
    print("  [PASS] Walk-forward validation runs")

    print("  WalkForwardValidator: PASS\n")


def test_turnover_calculation():
    """Test turnover calculation."""
    print("Testing turnover calculation...")

    returns_df = generate_sample_returns()
    weights = np.array([0.33, 0.33, 0.34])

    # Calculate turnover
    turnover = calculate_turnover(returns_df, weights, window=20)

    assert isinstance(turnover, (int, float))
    assert turnover >= 0
    print("  [PASS] Turnover calculation")

    # Test add_turnover_metrics
    metrics = {'sharpe': 1.5}
    weights_dict = {'Strategy_0': 0.33, 'Strategy_1': 0.33, 'Strategy_2': 0.34}
    updated_metrics = add_turnover_metrics(returns_df, weights_dict, metrics)

    assert 'turnover_pct' in updated_metrics
    assert 'cost_adjusted_sharpe' in updated_metrics
    print("  [PASS] Turnover metrics")

    print("  Turnover: PASS\n")


def test_regime_detector():
    """Test RegimeDetector basic functionality."""
    print("Testing RegimeDetector...")

    returns_df = generate_sample_returns()
    market_proxy = returns_df.mean(axis=1)

    # Create detector
    detector = RegimeDetector()

    # Detect regimes
    regimes = detector.detect(market_proxy)

    assert isinstance(regimes, dict)
    if len(regimes) > 0:
        first_regime = regimes[list(regimes.keys())[0]]
        assert 'vol' in first_regime
        assert 'trend' in first_regime
        assert first_regime['vol'] in ['high', 'low']
        assert first_regime['trend'] in ['up', 'down', 'flat']
    print("  [PASS] Regime detection")

    # Test regime scores
    regime_scores = detector.calculate_regime_scores(returns_df, returns_df)
    assert len(regime_scores) == 3
    print("  [PASS] Regime scores")

    # Test blending
    base_weights = {'Strategy_0': 0.5, 'Strategy_1': 0.3, 'Strategy_2': 0.2}
    blended = blend_with_regime_scores(base_weights, regime_scores, regime_weight=0.25)
    assert abs(sum(blended.values()) - 1.0) < 1e-6
    print("  [PASS] Regime blending")

    print("  RegimeDetector: PASS\n")


def test_meta_selector():
    """Test MetaSelector basic functionality."""
    print("Testing MetaSelector...")

    returns_df = generate_sample_returns()

    # Create meta selector (classifier mode)
    meta = MetaSelector(returns_df, mode='classifier', lookback=10)

    # Train
    meta.train()
    assert meta.is_trained
    print("  [PASS] Meta training (classifier)")

    # Predict weights
    weights = meta.predict_weights(20)
    assert len(weights) == 3
    assert abs(sum(weights.values()) - 1.0) < 1e-6
    print("  [PASS] Meta prediction")

    # Backtest
    port_returns, weights_df = meta.backtest()
    assert len(port_returns) > 0
    assert weights_df.shape[1] == 3
    print("  [PASS] Meta backtest")

    print("  MetaSelector: PASS\n")


def test_optimize_portfolio_convenience():
    """Test optimize_portfolio convenience function."""
    print("Testing optimize_portfolio convenience function...")

    returns_df = generate_sample_returns()

    # Test different methods
    for method in ['equal', 'risk_parity', 'sharpe']:
        weights, port_returns, metrics = optimize_portfolio(returns_df, method=method)
        assert len(weights) == 3
        assert abs(sum(weights.values()) - 1.0) < 1e-6
        print(f"  [PASS] Method: {method}")

    print("  optimize_portfolio: PASS\n")


def run_all_tests():
    """Run all smoke tests."""
    print("="*60)
    print("Running Optimizer Smoke Tests")
    print("="*60 + "\n")

    try:
        test_static_optimizer()
        test_walk_forward_validator()
        test_turnover_calculation()
        test_regime_detector()
        test_meta_selector()
        test_optimize_portfolio_convenience()

        print("="*60)
        print("ALL TESTS PASSED [OK]")
        print("="*60)
        return 0

    except Exception as e:
        print("\n" + "="*60)
        print(f"TEST FAILED: {e}")
        print("="*60)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
