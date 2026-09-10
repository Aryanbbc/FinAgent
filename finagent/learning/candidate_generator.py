"""Bounded, deterministic configuration candidate generation for V0.5."""

from __future__ import annotations

import copy
import itertools
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from finagent.learning.models import CandidateProposal, CandidateReasonCode, LearningAgentInput, ParameterChange


class ConfigurationConstraintError(ValueError):
    """Raised when a candidate attempts an unapproved or invalid configuration change."""


APPROVED_PARAMETERS = frozenset(
    {
        "moving_average_fast_window",
        "moving_average_slow_window",
        "momentum_window",
        "mean_reversion_window",
        "mean_reversion_threshold",
        "momentum_entry_threshold",
        "momentum_exit_threshold",
        "execution_controls",
        "strategy_weights",
        "regime_strategy_mappings",
        "risk_confidence_threshold",
        "maximum_position_size",
        "maximum_volatility",
    }
)


@dataclass(frozen=True)
class CandidateGenerator:
    """Produces only explicit neighbourhood or grid changes in approved parameter space."""

    mode: str = "neighborhood"
    max_candidates: int = 5

    def __post_init__(self) -> None:
        if self.mode not in {"neighborhood", "grid"}:
            raise ValueError("Candidate search mode must be 'neighborhood' or 'grid'")
        if not 1 <= self.max_candidates <= 5:
            raise ValueError("max_candidates must be between 1 and 5")

    def generate(
        self,
        agent_input: LearningAgentInput,
        selected_parameters: Sequence[str],
        candidate_start: int = 1,
    ) -> tuple[CandidateProposal, ...]:
        """Return reproducible candidates ordered by approved parameter then proposed value."""
        unknown = set(selected_parameters) - APPROVED_PARAMETERS
        if unknown:
            raise ConfigurationConstraintError(f"Unapproved candidate parameters: {sorted(unknown)}")
        parameter_values = self._parameter_values(
            agent_input.current_configuration, agent_input.boundaries, selected_parameters
        )
        base_reasons = [CandidateReasonCode.MEMORY_RETRIEVED]
        if agent_input.critique:
            base_reasons.append(CandidateReasonCode.CRITIC_RECOMMENDATION)
        base_reasons.append(
            CandidateReasonCode.NEIGHBORHOOD_SEARCH if self.mode == "neighborhood" else CandidateReasonCode.GRID_SEARCH
        )
        proposals: list[CandidateProposal] = []
        fingerprints: set[str] = set()
        if self.mode == "neighborhood":
            combinations = self._neighborhood_combinations(parameter_values)
        else:
            active = [(parameter, values) for parameter, values in parameter_values if values]
            combinations = list(itertools.product(*[[(parameter, value) for value in values] for parameter, values in active]))

        for combination in combinations:
            if len(proposals) >= self.max_candidates:
                break
            configuration = copy.deepcopy(agent_input.current_configuration)
            changes: list[ParameterChange] = []
            for parameter, value in combination:
                previous = self._get_parameter(configuration, parameter)
                if previous == value:
                    continue
                self._set_parameter(configuration, parameter, value)
                changes.append(ParameterChange(parameter, previous, value))
            if not changes:
                continue
            self.validate_configuration(configuration)
            fingerprint = json.dumps(configuration, sort_keys=True, separators=(",", ":"), default=str)
            if fingerprint in fingerprints:
                continue
            fingerprints.add(fingerprint)
            proposal = CandidateProposal(
                candidate_id=f"CAND-{candidate_start + len(proposals):04d}",
                parent_version_id=agent_input.current_version_id,
                configuration=configuration,
                parameter_changes=tuple(changes),
                reason_codes=tuple(base_reasons),
            )
            proposals.append(proposal)
        return tuple(proposals)

    def generate_profiles(
        self,
        agent_input: LearningAgentInput,
        profiles: Sequence[Mapping[str, Any]],
        candidate_start: int = 1,
    ) -> tuple[CandidateProposal, ...]:
        """Generate predeclared multi-lever candidates without an open-ended search.

        A profile contains only an explicit ``changes`` mapping of allowlisted
        settings.  It lets research define a small, auditable combination such
        as a holding/cooldown policy plus position weights, where the levers are
        meaningful only together.  The resulting configuration contains the
        actual consumed settings, never a profile-only runtime key.
        """
        base_reasons = [CandidateReasonCode.MEMORY_RETRIEVED]
        if agent_input.critique:
            base_reasons.append(CandidateReasonCode.CRITIC_RECOMMENDATION)
        base_reasons.append(CandidateReasonCode.NEIGHBORHOOD_SEARCH)
        proposals: list[CandidateProposal] = []
        fingerprints: set[str] = set()
        for profile in profiles:
            if len(proposals) >= self.max_candidates:
                break
            changes_mapping = profile.get("changes")
            if not isinstance(changes_mapping, Mapping) or not changes_mapping:
                raise ConfigurationConstraintError("Candidate profiles require a non-empty changes mapping")
            unknown = set(changes_mapping) - APPROVED_PARAMETERS
            if unknown:
                raise ConfigurationConstraintError(f"Unapproved candidate parameters: {sorted(unknown)}")
            configuration = copy.deepcopy(agent_input.current_configuration)
            changes: list[ParameterChange] = []
            for parameter, value in changes_mapping.items():
                previous = self._get_parameter(configuration, parameter)
                if previous == value:
                    continue
                self._set_parameter(configuration, parameter, value)
                changes.append(ParameterChange(parameter, previous, value))
            if not changes:
                continue
            self.validate_configuration(configuration)
            fingerprint = json.dumps(configuration, sort_keys=True, separators=(",", ":"), default=str)
            if fingerprint in fingerprints:
                continue
            fingerprints.add(fingerprint)
            proposals.append(
                CandidateProposal(
                    candidate_id=f"CAND-{candidate_start + len(proposals):04d}",
                    parent_version_id=agent_input.current_version_id,
                    configuration=configuration,
                    parameter_changes=tuple(changes),
                    reason_codes=tuple(base_reasons),
                )
            )
        return tuple(proposals)

    @staticmethod
    def _neighborhood_combinations(
        parameter_values: Sequence[tuple[str, list[Any]]],
    ) -> list[tuple[tuple[str, Any], ...]]:
        """Interleave parameters so a small candidate budget explores distinct levers.

        A previous implementation exhausted both neighbours of one parameter
        before considering another.  With a four-candidate budget, that could
        leave a run exploring only a narrow part of the approved space.  This
        round-robin ordering remains deterministic and local to each boundary,
        but gives every selected, executable parameter one opportunity first.
        """
        combinations: list[tuple[tuple[str, Any], ...]] = []
        depth = 0
        while True:
            added = False
            for parameter, values in parameter_values:
                if depth < len(values):
                    combinations.append(((parameter, values[depth]),))
                    added = True
            if not added:
                return combinations
            depth += 1

    def apply_parameter_change(self, configuration: Mapping[str, Any], parameter: str, value: Any) -> dict[str, Any]:
        """Return a validated copy with one allowlisted value changed for sensitivity research."""
        if parameter not in APPROVED_PARAMETERS:
            raise ConfigurationConstraintError(f"Unapproved candidate parameter: {parameter}")
        result = copy.deepcopy(dict(configuration))
        self._set_parameter(result, parameter, value)
        self.validate_configuration(result)
        return result

    def _parameter_values(
        self,
        configuration: Mapping[str, Any],
        boundaries: Mapping[str, Any],
        selected_parameters: Sequence[str],
    ) -> list[tuple[str, list[Any]]]:
        values: list[tuple[str, list[Any]]] = []
        for parameter in dict.fromkeys(selected_parameters):
            if parameter not in boundaries:
                continue
            current = self._get_parameter(configuration, parameter)
            boundary = dict(boundaries[parameter])
            candidates = self._values_for_boundary(current, boundary)
            candidates = [candidate for candidate in candidates if candidate != current]
            values.append((parameter, candidates))
        return values

    def _values_for_boundary(self, current: Any, boundary: Mapping[str, Any]) -> list[Any]:
        if "values" in boundary:
            raw_values = list(boundary["values"])
        elif self.mode == "neighborhood":
            if not isinstance(current, (int, float)):
                raise ConfigurationConstraintError("Neighborhood search requires numeric current values or explicit values")
            if "step" not in boundary:
                raise ConfigurationConstraintError("Neighborhood search boundaries require a step")
            step = boundary["step"]
            raw_values = [current - step, current + step]
        else:
            raise ConfigurationConstraintError("Grid search boundaries require explicit values")
        lower, upper = boundary.get("min"), boundary.get("max")
        filtered = [value for value in raw_values if (lower is None or value >= lower) and (upper is None or value <= upper)]
        return sorted(filtered, key=lambda value: repr(value))

    @staticmethod
    def _agent_strategy(configuration: Mapping[str, Any], strategy_name: str) -> Any:
        return configuration.get("agents", {}).get("strategy", {}).get("available_strategies", {}).get(strategy_name, {})

    def _get_parameter(self, configuration: Mapping[str, Any], parameter: str) -> Any:
        agents = configuration.get("agents", {})
        strategy = agents.get("strategy", {})
        risk = agents.get("risk", {})
        direct = configuration.get("strategy", {})
        backtest = configuration.get("backtest", {})
        if parameter == "moving_average_fast_window":
            return self._agent_strategy(configuration, "moving_average").get(
                "fast_window", direct.get("parameters", {}).get("fast_window")
            )
        if parameter == "moving_average_slow_window":
            return self._agent_strategy(configuration, "moving_average").get(
                "slow_window", direct.get("parameters", {}).get("slow_window")
            )
        if parameter == "momentum_window":
            return self._agent_strategy(configuration, "momentum").get(
                "lookback_window", direct.get("parameters", {}).get("lookback_window")
            )
        if parameter == "mean_reversion_window":
            return self._agent_strategy(configuration, "mean_reversion").get(
                "lookback_window", direct.get("parameters", {}).get("lookback_window")
            )
        if parameter == "mean_reversion_threshold":
            return self._agent_strategy(configuration, "mean_reversion").get(
                "entry_zscore", direct.get("parameters", {}).get("entry_zscore")
            )
        if parameter == "momentum_entry_threshold":
            return self._agent_strategy(configuration, "momentum").get(
                "entry_threshold", direct.get("parameters", {}).get("entry_threshold")
            )
        if parameter == "momentum_exit_threshold":
            return self._agent_strategy(configuration, "momentum").get(
                "exit_threshold", direct.get("parameters", {}).get("exit_threshold")
            )
        if parameter == "execution_controls":
            return copy.deepcopy(backtest.get("execution_controls", {}))
        if parameter == "strategy_weights":
            return copy.deepcopy(strategy.get("strategy_weights", {}))
        if parameter == "regime_strategy_mappings":
            return copy.deepcopy(strategy.get("regime_strategy_map", {}))
        if parameter == "risk_confidence_threshold":
            return risk.get("minimum_confidence")
        if parameter == "maximum_position_size":
            return risk.get("max_position_size")
        if parameter == "maximum_volatility":
            return risk.get("max_volatility")
        raise ConfigurationConstraintError(f"Unapproved candidate parameter: {parameter}")

    def _set_parameter(self, configuration: dict[str, Any], parameter: str, value: Any) -> None:
        agents = configuration.setdefault("agents", {})
        strategy = agents.setdefault("strategy", {})
        available = strategy.setdefault("available_strategies", {})
        risk = agents.setdefault("risk", {})
        direct = configuration.setdefault("strategy", {})
        direct_parameters = direct.setdefault("parameters", {})
        backtest = configuration.setdefault("backtest", {})
        if parameter == "moving_average_fast_window":
            available.setdefault("moving_average", {})["fast_window"] = int(value)
            if direct.get("name") == "moving_average":
                direct_parameters["fast_window"] = int(value)
        elif parameter == "moving_average_slow_window":
            available.setdefault("moving_average", {})["slow_window"] = int(value)
            if direct.get("name") == "moving_average":
                direct_parameters["slow_window"] = int(value)
        elif parameter == "momentum_window":
            available.setdefault("momentum", {})["lookback_window"] = int(value)
            if direct.get("name") == "momentum":
                direct_parameters["lookback_window"] = int(value)
        elif parameter == "mean_reversion_window":
            available.setdefault("mean_reversion", {})["lookback_window"] = int(value)
            if direct.get("name") == "mean_reversion":
                direct_parameters["lookback_window"] = int(value)
        elif parameter == "mean_reversion_threshold":
            available.setdefault("mean_reversion", {})["entry_zscore"] = float(value)
            if direct.get("name") == "mean_reversion":
                direct_parameters["entry_zscore"] = float(value)
        elif parameter == "momentum_entry_threshold":
            available.setdefault("momentum", {})["entry_threshold"] = float(value)
            if direct.get("name") == "momentum":
                direct_parameters["entry_threshold"] = float(value)
        elif parameter == "momentum_exit_threshold":
            available.setdefault("momentum", {})["exit_threshold"] = float(value)
            if direct.get("name") == "momentum":
                direct_parameters["exit_threshold"] = float(value)
        elif parameter == "execution_controls":
            if not isinstance(value, Mapping):
                raise ConfigurationConstraintError("execution_controls must be a mapping")
            backtest["execution_controls"] = dict(value)
        elif parameter == "strategy_weights":
            strategy["strategy_weights"] = dict(value)
        elif parameter == "regime_strategy_mappings":
            strategy["regime_strategy_map"] = dict(value)
        elif parameter == "risk_confidence_threshold":
            risk["minimum_confidence"] = float(value)
        elif parameter == "maximum_position_size":
            risk["max_position_size"] = float(value)
        elif parameter == "maximum_volatility":
            risk["max_volatility"] = float(value)
        else:
            raise ConfigurationConstraintError(f"Unapproved candidate parameter: {parameter}")

    @classmethod
    def validate_configuration(cls, configuration: Mapping[str, Any]) -> None:
        """Validate the relevant strategy/risk invariants before a candidate is evaluated."""
        available = configuration.get("agents", {}).get("strategy", {}).get("available_strategies", {})
        moving_average = available.get("moving_average", {})
        if moving_average:
            fast, slow = moving_average.get("fast_window"), moving_average.get("slow_window")
            if fast is None or slow is None or int(fast) < 1 or int(slow) <= int(fast):
                raise ConfigurationConstraintError("moving_average fast_window must be positive and lower than slow_window")
        momentum = available.get("momentum", {})
        if momentum:
            if int(momentum.get("lookback_window", 0)) < 1:
                raise ConfigurationConstraintError("momentum lookback_window must be positive")
            if float(momentum.get("exit_threshold", 0)) > float(momentum.get("entry_threshold", 0)):
                raise ConfigurationConstraintError("momentum exit_threshold cannot exceed entry_threshold")
        mean_reversion = available.get("mean_reversion", {})
        if mean_reversion:
            if int(mean_reversion.get("lookback_window", 0)) < 2:
                raise ConfigurationConstraintError("mean_reversion lookback_window must be at least two")
            if float(mean_reversion.get("entry_zscore", 0)) >= float(mean_reversion.get("exit_zscore", 0)):
                raise ConfigurationConstraintError("mean_reversion entry_zscore must be lower than exit_zscore")
        strategy = configuration.get("agents", {}).get("strategy", {})
        available_names = set(available)
        mapping = strategy.get("regime_strategy_map", {})
        if any(selected not in available_names for selected in mapping.values()):
            raise ConfigurationConstraintError("regime_strategy_map must only select available baseline strategies")
        if any(not 0 < float(weight) <= 1 for weight in strategy.get("strategy_weights", {}).values()):
            raise ConfigurationConstraintError("strategy_weights must be in (0, 1]")
        risk = configuration.get("agents", {}).get("risk", {})
        if risk:
            if not 0 <= float(risk.get("minimum_confidence", 0)) <= 1:
                raise ConfigurationConstraintError("risk confidence threshold must be between zero and one")
            if not 0 < float(risk.get("max_position_size", 0)) <= 1:
                raise ConfigurationConstraintError("maximum position size must be in (0, 1]")
            if float(risk.get("max_volatility", 0)) <= 0:
                raise ConfigurationConstraintError("maximum volatility must be positive")
        controls = configuration.get("backtest", {}).get("execution_controls", {})
        if not isinstance(controls, Mapping):
            raise ConfigurationConstraintError("execution_controls must be a mapping")
        for name in ("minimum_holding_period_bars", "reentry_cooldown_bars"):
            value = controls.get(name, 0)
            if isinstance(value, bool) or int(value) != value or not 0 <= int(value) <= 252:
                raise ConfigurationConstraintError(f"{name} must be an integer between 0 and 252")
