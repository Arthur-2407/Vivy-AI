"""
evolution/evolution_engine.py
==================================
Vivy AI — Evolution Engine: Offline Evolutionary Search & Self-Play

Executes background evolutionary search cycles and synthetic self-play evaluations
during circadian quiet hours (e.g. Night, LateNight, PreDawn) to discover optimized
prompt strategies and parameter configurations.
"""

from __future__ import annotations
import os
import json
import time
import random
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from evolution.consolidation_layer import get_consolidation_layer

try:
    from resource_scheduler_ml import get_resource_scheduler_ml
    _resource_ml = get_resource_scheduler_ml()
except ImportError:
    _resource_ml = None


@dataclass
class CandidateGenome:
    genome_id: str
    timestamp: float
    parameters: Dict[str, Any]
    fitness_score: float = 0.0

class EvolutionEngine:
    """
    Population-Based Evolutionary Search & Synthetic Self-Play Evaluator.
    """
    def __init__(self, population_size: int = 5):
        self._lock = threading.Lock()
        self._population_size = population_size
        self._population: List[CandidateGenome] = self._initialize_population()
        self._best_genome: Optional[CandidateGenome] = None

    def _initialize_population(self) -> List[CandidateGenome]:
        pop = []
        now = time.time()
        base_params = {
            "prompt_style_weight": 0.8,
            "rie_threshold": 0.75,
            "search_trigger_sensitivity": 0.5,
            "context_injection_budget": 800
        }
        for i in range(self._population_size):
            gid = f"genome_{i}_{int(now)}"
            # Mutate base parameters slightly for initial population diversity
            mutated = dict(base_params)
            mutated["prompt_style_weight"] = round(max(0.1, min(1.0, base_params["prompt_style_weight"] + random.uniform(-0.1, 0.1))), 2)
            mutated["search_trigger_sensitivity"] = round(max(0.1, min(1.0, base_params["search_trigger_sensitivity"] + random.uniform(-0.1, 0.1))), 2)
            pop.append(CandidateGenome(genome_id=gid, timestamp=now, parameters=mutated, fitness_score=0.5))
        return pop

    def evaluate_candidate_self_play(self, genome: CandidateGenome) -> float:
        """
        Simulate a lightweight synthetic evaluation cycle on CPU to score genome fitness.
        Zero GPU consumption.
        """
        # Synthetic fitness scoring based on parameter balance
        sens = genome.parameters.get("search_trigger_sensitivity", 0.5)
        weight = genome.parameters.get("prompt_style_weight", 0.8)
        # Optimal parameters are balanced (neither extreme zero nor extreme max)
        fitness = 1.0 - abs(sens - 0.5) * 0.4 - abs(weight - 0.7) * 0.4
        return round(max(0.0, min(1.0, fitness)), 4)

    def run_evolution_cycle(self, circadian_phase: str = "Night") -> Optional[CandidateGenome]:
        """
        Run an evolutionary search cycle if in a quiet circadian phase.
        """
        quiet_phases = ["Night", "LateNight", "PreDawn"]
        if circadian_phase not in quiet_phases:
            return None

        # ML Resource Throttling
        if _resource_ml is not None:
            if not _resource_ml.can_run_background_tasks():
                print("[EvolutionEngine] ML Resource Scheduler throttled evolution cycle due to high predicted load.")
                return None

        with self._lock:
            # 1. Evaluate fitness for current population
            for genome in self._population:
                genome.fitness_score = self.evaluate_candidate_self_play(genome)

            # 2. Sort by fitness
            self._population.sort(key=lambda g: g.fitness_score, reverse=True)
            self._best_genome = self._population[0]

            # 3. Create next generation (Elitism + Mutation)
            new_pop = [self._best_genome]
            now = time.time()

            while len(new_pop) < self._population_size:
                parent = random.choice(self._population[:3])
                mutated_params = dict(parent.parameters)
                # Apply small Gaussian mutation
                mutated_params["search_trigger_sensitivity"] = round(
                    max(0.1, min(1.0, mutated_params["search_trigger_sensitivity"] + random.gauss(0, 0.05))), 2
                )
                gid = f"genome_gen_{len(new_pop)}_{int(now)}"
                new_pop.append(CandidateGenome(genome_id=gid, timestamp=now, parameters=mutated_params, fitness_score=0.0))

            self._population = new_pop
            return self._best_genome

    def get_best_candidate(self) -> Optional[CandidateGenome]:
        with self._lock:
            return self._best_genome

_global_evolution_engine: Optional[EvolutionEngine] = None
_evolution_lock = threading.Lock()

def get_evolution_engine() -> EvolutionEngine:
    global _global_evolution_engine
    if _global_evolution_engine is None:
        with _evolution_lock:
            if _global_evolution_engine is None:
                _global_evolution_engine = EvolutionEngine()
    return _global_evolution_engine
