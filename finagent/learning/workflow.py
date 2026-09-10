"""User-invoked V0.5 controlled improvement workflow; it never alters live execution."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from finagent.data.loader import CSVDataLoader
from finagent.data.registry import DatasetRegistry
from finagent.database.db import Database
from finagent.database.experiment_repository import ExperimentRepository
from finagent.learning.learning_agent import LearningAgent
from finagent.learning.models import (
    CandidateReasonCode,
    ConfigurationVersion,
    ImprovementRunResult,
    LearningAgentInput,
    PromotionDecision,
    PromotionStatus,
)
from finagent.learning.promotion_gate import PromotionGate, PromotionGateConfig
from finagent.learning.walk_forward import WalkForwardConfig, WalkForwardEvaluator
from finagent.runner import load_configuration


def _canonical_configuration(configuration: dict[str, Any]) -> str:
    """Stable comparison form for source/parent configuration provenance."""
    return json.dumps(configuration, sort_keys=True, separators=(",", ":"), default=str)


def _source_identity(configuration: dict[str, Any]) -> tuple[str, str]:
    experiment = dict(configuration["experiment"])
    asset = str(experiment.get("asset") or "").upper()
    dataset = str(experiment.get("dataset_id") or experiment.get("dataset") or "")
    if not asset or not dataset:
        raise ValueError("Learning source configuration requires experiment.asset and a dataset source")
    return asset, dataset


def _version_for_source(repository: ExperimentRepository, source_configuration: dict[str, Any]) -> ConfigurationVersion | None:
    """Find the latest version descended from this exact source baseline only."""
    history = repository.configuration_version_history()
    source_fingerprint = _canonical_configuration(source_configuration)
    baseline_ids = {
        version.version_id
        for version in history
        if version.status == PromotionStatus.BASELINE
        and _canonical_configuration(version.configuration) == source_fingerprint
    }
    if not baseline_ids:
        return None
    by_id = {version.version_id: version for version in history}

    def belongs_to_source(version: ConfigurationVersion) -> bool:
        cursor: ConfigurationVersion | None = version
        visited: set[str] = set()
        while cursor is not None and cursor.version_id not in visited:
            if cursor.version_id in baseline_ids:
                return True
            visited.add(cursor.version_id)
            cursor = by_id.get(cursor.parent_version_id or "")
        return False

    matches = [
        version
        for version in history
        if version.status in {PromotionStatus.BASELINE, PromotionStatus.PROMOTED} and belongs_to_source(version)
    ]
    return max(matches, key=lambda version: (version.created_at, version.version_id)) if matches else None


def _experiment_matches_source(
    repository: ExperimentRepository,
    experiment_id: str,
    source_asset: str,
    source_dataset: str,
    source_configuration: dict[str, Any],
) -> bool:
    experiment = repository.get_experiment(experiment_id)
    return bool(
        experiment
        and experiment.asset.upper() == source_asset
        and experiment.dataset == source_dataset
        and _canonical_configuration(experiment.configuration) == _canonical_configuration(source_configuration)
    )


def _duplicate_outcome(
    evaluation: Any,
    prior_evaluations: list[Any],
    tolerance: float = 1e-9,
) -> bool:
    """Detect semantically different candidates that produce the same OOS evidence."""
    fields = (
        "total_return",
        "sharpe_ratio",
        "maximum_drawdown",
        "turnover",
        "transaction_cost",
        "number_of_trades",
        "position_changes",
        "trades_per_year",
        "average_holding_period_bars",
    )

    def close(left: Any, right: Any) -> bool:
        if left is None or right is None:
            return left is right
        return abs(float(left) - float(right)) <= tolerance

    def same_metrics(left: Any, right: Any) -> bool:
        return all(close(getattr(left, field), getattr(right, field)) for field in fields)

    for prior in prior_evaluations:
        if len(evaluation.windows) != len(prior.windows):
            continue
        if not same_metrics(evaluation.candidate_aggregate, prior.candidate_aggregate):
            continue
        if all(
            same_metrics(window.candidate_metrics, previous.candidate_metrics)
            for window, previous in zip(evaluation.windows, prior.windows, strict=True)
        ):
            return True
    return False


def run_improvement(
    config_path: str | Path,
    project_root: str | Path,
    logger: logging.Logger | None = None,
    database_url: str | Path | None = None,
) -> ImprovementRunResult | None:
    """Generate, validate, gate, and record bounded V0.5 candidates when explicitly enabled."""
    root = Path(project_root)
    requested = Path(config_path)
    if not requested.is_absolute():
        requested = root / requested
    with requested.open(encoding="utf-8") as handle:
        improvement_config = yaml.safe_load(handle) or {}
    learning = dict(improvement_config.get("learning", {}))
    if not bool(learning.get("enabled", False)):
        if logger:
            logger.info("event=LEARNING_DISABLED config=%s", requested)
        return None

    source_value = improvement_config.get("source_experiment_config", "config/experiments.yaml")
    source_configuration = load_configuration(source_value, root)
    database_value = database_url or improvement_config.get("database_path", source_configuration.get("database_path", "data/finagent.db"))
    database = Database(database_value, root)
    if database_url is not None:
        source_configuration["database_path"] = str(database_url)
    repository = ExperimentRepository(database)
    source_asset, source_dataset = _source_identity(source_configuration)

    memory_id = learning.get("memory_experiment_id")
    memory = (
        repository.get_experiment_memory(str(memory_id))
        if memory_id
        else repository.latest_experiment_memory_for_source(
            asset=source_asset,
            dataset=source_dataset,
            configuration=source_configuration,
        )
    )
    if memory is None:
        raise ValueError(
            "V0.5 learning requires a persisted experiment-memory record for the configured asset and dataset"
        )
    if not _experiment_matches_source(
        repository, memory.experiment_id, source_asset, source_dataset, source_configuration
    ):
        raise ValueError(
            "V0.5 learning memory must belong to the exact configured baseline; run that baseline experiment first"
        )

    current_version = _version_for_source(repository, source_configuration)
    if current_version is None:
        current_version = ConfigurationVersion(
            version_id=repository.next_version_id(),
            parent_version_id=None,
            candidate_id=None,
            configuration=source_configuration,
            validation_metrics=None,
            status=PromotionStatus.BASELINE,
            reason_codes=(CandidateReasonCode.MEMORY_RETRIEVED,),
            created_at=datetime.now(UTC).isoformat(),
        )
        repository.save_configuration_version(current_version)
        if logger:
            logger.info("event=CONFIGURATION_BASELINE_REGISTERED version_id=%s", current_version.version_id)

    critique = repository.get_critique(memory.experiment_id) or memory.critique
    if logger:
        logger.info(
            "event=LEARNING_MEMORY_RETRIEVED experiment_id=%s parent_version=%s",
            memory.experiment_id,
            current_version.version_id,
        )

    search = dict(learning.get("search", {}))
    raw_profiles = search.get("profiles", [])
    if not isinstance(raw_profiles, list) or any(not isinstance(profile, dict) for profile in raw_profiles):
        raise ValueError("learning.search.profiles must be a list of mapping profiles")
    candidates = LearningAgent(logger).propose(
        agent_input=LearningAgentInput(
            current_version_id=current_version.version_id,
            current_configuration=current_version.configuration,
            memory=memory.to_dict(),
            critique=critique.to_dict(),
            boundaries=dict(search.get("boundaries", {})),
            search_mode=str(search.get("mode", "neighborhood")),
            max_candidates=int(search.get("max_candidates", 5)),
            candidate_profiles=tuple(dict(profile) for profile in raw_profiles),
        ),
        candidate_start=repository.next_candidate_number(),
    )
    previous_fingerprints = repository.candidate_configuration_fingerprints(current_version.version_id)
    if previous_fingerprints:
        unseen_candidates = tuple(
            candidate
            for candidate in candidates
            if _canonical_configuration(candidate.configuration) not in previous_fingerprints
        )
        skipped = len(candidates) - len(unseen_candidates)
        if skipped and logger:
            logger.info(
                "event=PREVIOUSLY_EVALUATED_CONFIGURATIONS_SKIPPED parent_version=%s count=%s",
                current_version.version_id,
                skipped,
            )
        candidates = unseen_candidates
    if not candidates:
        if logger:
            logger.info("event=NO_NEW_CANDIDATES_GENERATED parent_version=%s", current_version.version_id)
        return ImprovementRunResult(current_version, (), (), (), None)

    experiment_configuration = current_version.configuration["experiment"]
    dataset_id = experiment_configuration.get("dataset_id")
    if dataset_id:
        dataset_registry = DatasetRegistry(database)
        dataset = dataset_registry.latest(str(dataset_id))
        market_data = (
            dataset_registry.load_ohlcv(dataset.version_id)
            if dataset_registry.has_ohlcv(dataset.version_id)
            else CSVDataLoader().load(dataset.cache_path)
        )
    else:
        dataset_path = Path(experiment_configuration["dataset"])
        if not dataset_path.is_absolute():
            dataset_path = root / dataset_path
        market_data = CSVDataLoader().load(dataset_path)
    walk_forward = WalkForwardEvaluator(WalkForwardConfig.from_mapping(dict(learning.get("walk_forward", {}))))
    promotion_configuration = dict(learning.get("promotion_gate", {}))
    promotion_configuration.setdefault("minimum_windows", learning.get("walk_forward", {}).get("min_windows", 1))
    gate = PromotionGate(PromotionGateConfig.from_mapping(promotion_configuration))
    evaluations = []
    initial_decisions: list[PromotionDecision] = []
    for candidate in candidates:
        repository.save_candidate_configuration(candidate)
        evaluation = walk_forward.evaluate(market_data, current_version.configuration, candidate)
        decision = gate.decide(evaluation)
        if _duplicate_outcome(evaluation, evaluations):
            decision = PromotionDecision(
                candidate_id=decision.candidate_id,
                parent_version_id=decision.parent_version_id,
                status=PromotionStatus.REJECTED,
                reason_codes=(CandidateReasonCode.DUPLICATE_OUT_OF_SAMPLE_OUTCOME, CandidateReasonCode.REJECTED),
                parent_metrics=decision.parent_metrics,
                candidate_metrics=decision.candidate_metrics,
                window_pass_rate=decision.window_pass_rate,
            )
        evaluations.append(evaluation)
        initial_decisions.append(decision)
        if logger:
            changes = ";".join(
                f"{change.parameter}:{change.previous_value!r}->{change.proposed_value!r}"
                for change in candidate.parameter_changes
            )
            logger.info(
                "event=WALK_FORWARD_EVALUATED candidate_id=%s changes=%s windows=%s oos_return=%s "
                "oos_sharpe=%s oos_drawdown=%s trades=%s trades_per_year=%s average_holding_bars=%s "
                "position_changes=%s turnover=%s pass_rate=%s status=%s reasons=%s",
                candidate.candidate_id,
                changes,
                len(evaluation.windows),
                decision.candidate_metrics.total_return,
                decision.candidate_metrics.sharpe_ratio,
                decision.candidate_metrics.maximum_drawdown,
                decision.candidate_metrics.number_of_trades,
                decision.candidate_metrics.trades_per_year,
                decision.candidate_metrics.average_holding_period_bars,
                decision.candidate_metrics.position_changes,
                decision.candidate_metrics.turnover,
                decision.window_pass_rate,
                decision.status.value,
                ",".join(code.value for code in decision.reason_codes),
            )

    eligible = [decision for decision in initial_decisions if decision.status == PromotionStatus.PROMOTED]
    selected = max(
        eligible,
        key=lambda decision: (
            decision.candidate_metrics.sharpe_ratio if decision.candidate_metrics.sharpe_ratio is not None else float("-inf"),
            decision.candidate_id,
        ),
        default=None,
    )
    decisions: list[PromotionDecision] = []
    for decision in initial_decisions:
        if selected is not None and decision.candidate_id != selected.candidate_id and decision.status == PromotionStatus.PROMOTED:
            decision = PromotionDecision(
                candidate_id=decision.candidate_id,
                parent_version_id=decision.parent_version_id,
                status=PromotionStatus.REJECTED,
                reason_codes=(CandidateReasonCode.NOT_SELECTED, CandidateReasonCode.REJECTED),
                parent_metrics=decision.parent_metrics,
                candidate_metrics=decision.candidate_metrics,
                window_pass_rate=decision.window_pass_rate,
            )
        repository.save_walk_forward_evaluation(evaluations[len(decisions)], decision)
        decisions.append(decision)

    promoted_version: ConfigurationVersion | None = None
    if selected is not None:
        candidate = next(item for item in candidates if item.candidate_id == selected.candidate_id)
        promoted_version = ConfigurationVersion(
            version_id=repository.next_version_id(),
            parent_version_id=current_version.version_id,
            candidate_id=candidate.candidate_id,
            configuration=candidate.configuration,
            validation_metrics=selected.candidate_metrics,
            status=PromotionStatus.PROMOTED,
            reason_codes=selected.reason_codes,
            created_at=datetime.now(UTC).isoformat(),
        )
        repository.save_configuration_version(promoted_version)
        if logger:
            logger.info(
                "event=CANDIDATE_PROMOTED candidate_id=%s new_version=%s parent_version=%s",
                candidate.candidate_id,
                promoted_version.version_id,
                current_version.version_id,
            )
    elif logger:
        logger.info("event=NO_CANDIDATE_PROMOTED parent_version=%s", current_version.version_id)
    return ImprovementRunResult(
        current_version=current_version,
        candidates=candidates,
        evaluations=tuple(evaluations),
        decisions=tuple(decisions),
        promoted_version=promoted_version,
    )
