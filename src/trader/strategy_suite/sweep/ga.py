"""
Genetic Algorithm optimizer for strategy parameter tuning.
"""

import json
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Type, Optional, Tuple
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass

from ..strategies.base import BaseStrategy
from ..backtest import run_backtest


@dataclass
class GAConfig:
    """Configuration for genetic algorithm."""
    population_size: int = 50
    generations: int = 20
    mutation_rate: float = 0.2
    crossover_rate: float = 0.7
    elitism_pct: float = 0.1
    tournament_size: int = 3
    seed: int = 42


class Individual:
    """Represents one parameter set (genome) in the population."""

    def __init__(self, params: Dict[str, Any]):
        self.params = params
        self.fitness = 0.0
        self.metrics = {}

    def __repr__(self):
        return f"Individual(fitness={self.fitness:.3f}, params={self.params})"


class GAOptimizer:
    """
    Genetic Algorithm optimizer for strategy parameters.

    Evolves parameter sets over multiple generations to maximize fitness
    (typically Sharpe ratio or another risk-adjusted metric).
    """

    def __init__(
        self,
        strategy_cls: Type[BaseStrategy],
        param_ranges: Dict[str, Tuple[Any, Any]],  # param_name -> (min, max) or list of choices
        tickers: List[str],
        start_date: str,
        end_date: str,
        capital: float = 100000.0,
        fitness_metric: str = "sharpe",
        config: Optional[GAConfig] = None,
        out_json: Optional[str] = None
    ):
        """
        Initialize GA optimizer.

        Args:
            strategy_cls: Strategy class
            param_ranges: Dictionary of parameter ranges
                - For continuous params: (min_value, max_value)
                - For discrete params: list of choices
            tickers: List of ticker symbols
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            capital: Initial capital
            fitness_metric: Metric to optimize (sharpe, sortino, calmar, etc.)
            config: GA configuration
            out_json: Output JSON path for best genomes
        """
        self.strategy_cls = strategy_cls
        self.param_ranges = param_ranges
        self.tickers = tickers
        self.start_date = start_date
        self.end_date = end_date
        self.capital = capital
        self.fitness_metric = fitness_metric
        self.config = config or GAConfig()

        # Set random seed
        np.random.seed(self.config.seed)

        # Output path
        if out_json is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            strategy_name = strategy_cls.__name__
            out_json = f"artifacts/sweeps/{strategy_name}_ga_{timestamp}.json"

        self.out_json = out_json
        self.population = []
        self.best_individual = None
        self.history = []

    def _random_params(self) -> Dict[str, Any]:
        """Generate random parameter set within ranges."""
        params = {}

        for param_name, param_range in self.param_ranges.items():
            if isinstance(param_range, (list, tuple)) and len(param_range) == 2:
                # Check if it's a numeric range or discrete choices
                if isinstance(param_range[0], (int, float)) and isinstance(param_range[1], (int, float)):
                    # Numeric range (min, max)
                    min_val, max_val = param_range

                    if isinstance(min_val, int) and isinstance(max_val, int):
                        # Integer parameter
                        params[param_name] = np.random.randint(min_val, max_val + 1)
                    else:
                        # Float parameter
                        params[param_name] = np.random.uniform(min_val, max_val)
                else:
                    # Discrete choices (tuple/list of options)
                    params[param_name] = np.random.choice(param_range)
            else:
                # List of discrete choices
                params[param_name] = np.random.choice(param_range)

        return params

    def _initialize_population(self):
        """Initialize random population."""
        self.population = []

        for _ in range(self.config.population_size):
            params = self._random_params()
            individual = Individual(params)
            self.population.append(individual)

    def _evaluate_fitness(self, individual: Individual) -> float:
        """
        Evaluate fitness of an individual by running backtest.

        Args:
            individual: Individual to evaluate

        Returns:
            Fitness value
        """
        try:
            strategy = self.strategy_cls(params=individual.params)

            results = run_backtest(
                strategy=strategy,
                tickers=self.tickers,
                start_date=self.start_date,
                end_date=self.end_date,
                initial_capital=self.capital
            )

            metrics = results["metrics"]

            if metrics is None:
                return 0.0

            # Store metrics
            individual.metrics = {
                "sharpe": metrics.sharpe_ratio,
                "sortino": metrics.sortino_ratio,
                "calmar": metrics.calmar_ratio,
                "return_pct": metrics.total_return_pct,
                "max_dd": metrics.max_drawdown_pct,
                "trades": metrics.total_trades
            }

            # Extract fitness metric
            if self.fitness_metric == "sharpe":
                fitness = metrics.sharpe_ratio
            elif self.fitness_metric == "sortino":
                fitness = metrics.sortino_ratio
            elif self.fitness_metric == "calmar":
                fitness = metrics.calmar_ratio
            elif self.fitness_metric == "return":
                fitness = metrics.total_return_pct
            else:
                fitness = metrics.sharpe_ratio

            return fitness

        except Exception as e:
            print(f"  Error evaluating individual: {e}")
            return 0.0

    def _tournament_selection(self) -> Individual:
        """Select individual using tournament selection."""
        tournament = np.random.choice(self.population, size=self.config.tournament_size, replace=False)
        winner = max(tournament, key=lambda ind: ind.fitness)
        return winner

    def _crossover(self, parent1: Individual, parent2: Individual) -> Tuple[Individual, Individual]:
        """Perform crossover between two parents."""
        if np.random.random() > self.config.crossover_rate:
            # No crossover, return copies of parents
            child1 = Individual(parent1.params.copy())
            child2 = Individual(parent2.params.copy())
            return child1, child2

        # Uniform crossover
        child1_params = {}
        child2_params = {}

        for param_name in parent1.params.keys():
            if np.random.random() < 0.5:
                child1_params[param_name] = parent1.params[param_name]
                child2_params[param_name] = parent2.params[param_name]
            else:
                child1_params[param_name] = parent2.params[param_name]
                child2_params[param_name] = parent1.params[param_name]

        child1 = Individual(child1_params)
        child2 = Individual(child2_params)

        return child1, child2

    def _mutate(self, individual: Individual):
        """Mutate individual's parameters."""
        for param_name, param_range in self.param_ranges.items():
            if np.random.random() < self.config.mutation_rate:
                # Mutate this parameter
                if isinstance(param_range, (list, tuple)) and len(param_range) == 2:
                    if isinstance(param_range[0], (int, float)) and isinstance(param_range[1], (int, float)):
                        # Numeric range - add gaussian noise or random reset
                        min_val, max_val = param_range

                        if np.random.random() < 0.5:
                            # Gaussian mutation
                            current = individual.params[param_name]
                            range_span = max_val - min_val
                            noise = np.random.normal(0, range_span * 0.1)
                            new_val = current + noise
                            new_val = np.clip(new_val, min_val, max_val)

                            if isinstance(min_val, int):
                                new_val = int(round(new_val))

                            individual.params[param_name] = new_val
                        else:
                            # Random reset
                            if isinstance(min_val, int):
                                individual.params[param_name] = np.random.randint(min_val, max_val + 1)
                            else:
                                individual.params[param_name] = np.random.uniform(min_val, max_val)
                    else:
                        # Discrete choices
                        individual.params[param_name] = np.random.choice(param_range)
                else:
                    # List of choices
                    individual.params[param_name] = np.random.choice(param_range)

    def run(self) -> Dict[str, Any]:
        """
        Run genetic algorithm optimization.

        Returns:
            Dictionary with best parameters and fitness
        """
        print(f"\n{'=' * 60}")
        print(f"GENETIC ALGORITHM: {self.strategy_cls.__name__}")
        print(f"{'=' * 60}")
        print(f"Population size: {self.config.population_size}")
        print(f"Generations: {self.config.generations}")
        print(f"Fitness metric: {self.fitness_metric}")
        print(f"Tickers: {', '.join(self.tickers)}")
        print(f"Date range: {self.start_date} to {self.end_date}")
        print(f"{'=' * 60}\n")

        # Initialize population
        print("Initializing population...")
        self._initialize_population()

        # Evolution loop
        for generation in range(self.config.generations):
            print(f"\nGeneration {generation + 1}/{self.config.generations}")

            # Evaluate fitness
            for individual in self.population:
                individual.fitness = self._evaluate_fitness(individual)

            # Sort by fitness
            self.population.sort(key=lambda ind: ind.fitness, reverse=True)

            # Track best
            best = self.population[0]
            avg_fitness = np.mean([ind.fitness for ind in self.population])

            print(f"  Best fitness: {best.fitness:.3f}")
            print(f"  Avg fitness: {avg_fitness:.3f}")
            print(f"  Best params: {best.params}")

            # Store history
            self.history.append({
                "generation": generation + 1,
                "best_fitness": best.fitness,
                "avg_fitness": avg_fitness,
                "best_params": best.params.copy()
            })

            # Update global best
            if self.best_individual is None or best.fitness > self.best_individual.fitness:
                self.best_individual = Individual(best.params.copy())
                self.best_individual.fitness = best.fitness
                self.best_individual.metrics = best.metrics.copy()

            # Selection and reproduction
            if generation < self.config.generations - 1:
                # Elitism - keep top performers
                n_elite = max(1, int(self.config.population_size * self.config.elitism_pct))
                new_population = self.population[:n_elite]

                # Generate offspring
                while len(new_population) < self.config.population_size:
                    # Select parents
                    parent1 = self._tournament_selection()
                    parent2 = self._tournament_selection()

                    # Crossover
                    child1, child2 = self._crossover(parent1, parent2)

                    # Mutation
                    self._mutate(child1)
                    self._mutate(child2)

                    new_population.extend([child1, child2])

                # Trim to population size
                self.population = new_population[:self.config.population_size]

        # Save results
        result = {
            "strategy": self.strategy_cls.__name__,
            "fitness_metric": self.fitness_metric,
            "best_fitness": self.best_individual.fitness,
            "best_params": self.best_individual.params,
            "best_metrics": self.best_individual.metrics,
            "history": self.history,
            "config": {
                "population_size": self.config.population_size,
                "generations": self.config.generations,
                "mutation_rate": self.config.mutation_rate,
                "crossover_rate": self.config.crossover_rate
            }
        }

        # Save to JSON
        Path(self.out_json).parent.mkdir(parents=True, exist_ok=True)
        with open(self.out_json, 'w') as f:
            json.dump(result, f, indent=2)

        print(f"\n{'=' * 60}")
        print("OPTIMIZATION COMPLETE")
        print(f"{'=' * 60}")
        print(f"Best fitness ({self.fitness_metric}): {self.best_individual.fitness:.3f}")
        print(f"Best parameters: {self.best_individual.params}")
        print(f"Results saved to: {self.out_json}")
        print(f"{'=' * 60}\n")

        return result
