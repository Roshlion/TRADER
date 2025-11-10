"""
Static portfolio weight optimizers (equal, risk parity, mean-variance).
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple
from scipy.optimize import minimize
import warnings


class StaticOptimizer:
    """
    Static portfolio weight optimizer.

    Given returns for multiple strategies, computes optimal weights using
    various allocation methods.
    """

    def __init__(self, returns_df: pd.DataFrame):
        """
        Initialize optimizer.

        Args:
            returns_df: DataFrame with columns = strategy names, index = timestamp
                Each column contains period returns for that strategy
        """
        self.returns_df = returns_df
        self.strategy_names = list(returns_df.columns)
        self.n_strategies = len(self.strategy_names)

        # Compute statistics
        self.mean_returns = returns_df.mean().values
        self.cov_matrix = returns_df.cov().values

        # Regularize covariance matrix to ensure positive definiteness
        self.cov_matrix = self._regularize_cov(self.cov_matrix)

    def _regularize_cov(self, cov: np.ndarray, epsilon: float = 1e-6) -> np.ndarray:
        """
        Regularize covariance matrix to ensure it's positive definite.

        Args:
            cov: Covariance matrix
            epsilon: Regularization parameter

        Returns:
            Regularized covariance matrix
        """
        # Add small value to diagonal
        cov_reg = cov + epsilon * np.eye(cov.shape[0])
        return cov_reg

    def equal(self) -> Tuple[Dict[str, float], pd.Series, Dict[str, float]]:
        """
        Equal weight allocation.

        Returns:
            Tuple of (weights_dict, portfolio_returns, metrics)
        """
        weights = np.ones(self.n_strategies) / self.n_strategies
        weights_dict = dict(zip(self.strategy_names, weights))

        # Calculate portfolio returns
        portfolio_returns = (self.returns_df * weights).sum(axis=1)

        # Calculate metrics
        metrics = self._calculate_metrics(weights, portfolio_returns)

        return weights_dict, portfolio_returns, metrics

    def risk_parity(self, max_iter: int = 1000, tol: float = 1e-8) -> Tuple[Dict[str, float], pd.Series, Dict[str, float]]:
        """
        Risk parity (Equal Risk Contribution) allocation.

        Iteratively solves for weights where each strategy contributes equal risk.

        Args:
            max_iter: Maximum iterations
            tol: Convergence tolerance

        Returns:
            Tuple of (weights_dict, portfolio_returns, metrics)
        """

        def risk_contribution(weights: np.ndarray, cov: np.ndarray) -> np.ndarray:
            """Calculate risk contribution of each asset."""
            portfolio_vol = np.sqrt(weights @ cov @ weights)
            marginal_contrib = cov @ weights
            risk_contrib = weights * marginal_contrib / portfolio_vol
            return risk_contrib

        def risk_parity_objective(weights: np.ndarray, cov: np.ndarray) -> float:
            """Objective: minimize variance of risk contributions."""
            rc = risk_contribution(weights, cov)
            target_rc = np.mean(rc)
            return np.sum((rc - target_rc) ** 2)

        # Initial guess: equal weights
        w0 = np.ones(self.n_strategies) / self.n_strategies

        # Constraints: weights sum to 1, all weights >= 0
        constraints = [
            {'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}
        ]

        bounds = [(0, 1) for _ in range(self.n_strategies)]

        # Optimize
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = minimize(
                risk_parity_objective,
                w0,
                args=(self.cov_matrix,),
                method='SLSQP',
                bounds=bounds,
                constraints=constraints,
                options={'maxiter': max_iter, 'ftol': tol}
            )

        if not result.success:
            print(f"Warning: Risk parity optimization did not converge: {result.message}")

        weights = result.x
        weights_dict = dict(zip(self.strategy_names, weights))

        # Calculate portfolio returns
        portfolio_returns = (self.returns_df * weights).sum(axis=1)

        # Calculate metrics
        metrics = self._calculate_metrics(weights, portfolio_returns)

        return weights_dict, portfolio_returns, metrics

    def mean_variance(
        self,
        objective: str = 'sharpe',
        max_weight: Optional[float] = None,
        long_only: bool = True,
        target_return: Optional[float] = None
    ) -> Tuple[Dict[str, float], pd.Series, Dict[str, float]]:
        """
        Mean-variance optimization (Markowitz).

        Args:
            objective: Optimization objective
                - 'sharpe': Maximize Sharpe ratio
                - 'return': Maximize return for given volatility
                - 'volatility': Minimize volatility for given return
            max_weight: Maximum weight per strategy (e.g., 0.5 for 50%)
            long_only: Only positive weights (no shorting)
            target_return: Target return (for 'volatility' objective)

        Returns:
            Tuple of (weights_dict, portfolio_returns, metrics)
        """

        def portfolio_stats(weights: np.ndarray) -> Tuple[float, float]:
            """Calculate portfolio return and volatility."""
            port_return = np.sum(weights * self.mean_returns)
            port_vol = np.sqrt(weights @ self.cov_matrix @ weights)
            return port_return, port_vol

        def neg_sharpe(weights: np.ndarray) -> float:
            """Negative Sharpe ratio (for minimization)."""
            port_return, port_vol = portfolio_stats(weights)
            if port_vol == 0:
                return 0
            return -(port_return / port_vol)

        def neg_return(weights: np.ndarray) -> float:
            """Negative return (for minimization)."""
            port_return, _ = portfolio_stats(weights)
            return -port_return

        def portfolio_vol(weights: np.ndarray) -> float:
            """Portfolio volatility."""
            _, port_vol = portfolio_stats(weights)
            return port_vol

        # Initial guess: equal weights
        w0 = np.ones(self.n_strategies) / self.n_strategies

        # Constraints: weights sum to 1
        constraints = [
            {'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}
        ]

        # Add target return constraint if specified
        if objective == 'volatility' and target_return is not None:
            constraints.append({
                'type': 'eq',
                'fun': lambda w: np.sum(w * self.mean_returns) - target_return
            })

        # Bounds
        if long_only:
            if max_weight:
                bounds = [(0, max_weight) for _ in range(self.n_strategies)]
            else:
                bounds = [(0, 1) for _ in range(self.n_strategies)]
        else:
            if max_weight:
                bounds = [(-max_weight, max_weight) for _ in range(self.n_strategies)]
            else:
                bounds = [(-1, 1) for _ in range(self.n_strategies)]

        # Select objective function
        if objective == 'sharpe':
            obj_func = neg_sharpe
        elif objective == 'return':
            obj_func = neg_return
        elif objective == 'volatility':
            obj_func = portfolio_vol
        else:
            raise ValueError(f"Unknown objective: {objective}")

        # Optimize
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = minimize(
                obj_func,
                w0,
                method='SLSQP',
                bounds=bounds,
                constraints=constraints,
                options={'maxiter': 1000, 'ftol': 1e-8}
            )

        if not result.success:
            print(f"Warning: Mean-variance optimization did not converge: {result.message}")

        weights = result.x
        weights_dict = dict(zip(self.strategy_names, weights))

        # Calculate portfolio returns
        portfolio_returns = (self.returns_df * weights).sum(axis=1)

        # Calculate metrics
        metrics = self._calculate_metrics(weights, portfolio_returns)

        return weights_dict, portfolio_returns, metrics

    def _calculate_metrics(self, weights: np.ndarray, portfolio_returns: pd.Series) -> Dict[str, float]:
        """
        Calculate portfolio metrics.

        Args:
            weights: Strategy weights
            portfolio_returns: Portfolio return series

        Returns:
            Dictionary of metrics
        """
        # Import here to avoid circular dependency
        from ..metrics import sharpe, sortino, max_drawdown, hit_rate

        # Portfolio statistics
        port_return_mean = np.mean(portfolio_returns)
        port_return_std = np.std(portfolio_returns)

        # Annualize (assuming daily returns, 252 trading days)
        annual_return = port_return_mean * 252
        annual_vol = port_return_std * np.sqrt(252)

        # Sharpe and Sortino
        sharpe_ratio = sharpe(portfolio_returns.values, rf=0.0, annualize=True, periods_per_year=252)
        sortino_ratio = sortino(portfolio_returns.values, rf=0.0, annualize=True, periods_per_year=252)

        # Drawdown
        equity = (1 + portfolio_returns).cumprod()
        max_dd = max_drawdown(equity.values)

        # Hit rate
        hr = hit_rate(portfolio_returns.values)

        # Diversification
        # Effective number of strategies (inverse of Herfindahl index)
        herfindahl = np.sum(weights ** 2)
        eff_n_strategies = 1 / herfindahl if herfindahl > 0 else 0

        return {
            "annual_return": annual_return * 100,  # As percentage
            "annual_volatility": annual_vol * 100,
            "sharpe": sharpe_ratio,
            "sortino": sortino_ratio,
            "max_dd": max_dd * 100,  # As percentage
            "hit_rate": hr,
            "total_return": ((1 + portfolio_returns).prod() - 1) * 100,
            "effective_n_strategies": eff_n_strategies,
        }


def optimize_portfolio(
    returns_df: pd.DataFrame,
    method: str = "sharpe",
    **kwargs
) -> Tuple[Dict[str, float], pd.Series, Dict[str, float]]:
    """
    Convenience function to optimize portfolio weights.

    Args:
        returns_df: DataFrame with strategy returns
        method: Optimization method
            - 'equal': Equal weight
            - 'risk_parity': Equal risk contribution
            - 'sharpe': Maximize Sharpe ratio
            - 'min_vol': Minimum volatility
        **kwargs: Additional arguments for optimizer

    Returns:
        Tuple of (weights_dict, portfolio_returns, metrics)
    """
    optimizer = StaticOptimizer(returns_df)

    if method == "equal":
        return optimizer.equal()
    elif method == "risk_parity":
        return optimizer.risk_parity(**kwargs)
    elif method == "sharpe":
        return optimizer.mean_variance(objective='sharpe', **kwargs)
    elif method == "min_vol":
        return optimizer.mean_variance(objective='volatility', **kwargs)
    elif method == "max_return":
        return optimizer.mean_variance(objective='return', **kwargs)
    else:
        raise ValueError(f"Unknown method: {method}")
