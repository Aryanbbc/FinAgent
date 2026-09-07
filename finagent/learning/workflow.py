"""User-invoked V0.5 controlled improvement workflow; it never alters live execution."""

from __future__ import annotations

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
    current_version = repository.current_configuration_version()
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

    memory_id = learning.get("memory_experiment_id")
    memory = repository.get_experiment_memory(str(memory_id)) if memory_id else repository.latest_experiment_memory()
    if memory is None:
        raise ValueError("V0.5 learning requires a persisted V0.4 experiment-memory record")
    critique = repository.get_critique(memory.experiment_id) or memory.critique
    if logger:
        logger.info(
            "event=LEARNING_MEMORY_RETRIEVED experiment_id=%s parent_version=%s",
            memory.experiment_id,
            current_version.version_id,
        )

    search = dict(learning.get("search", {}))
    candidates = LearningAgent(logger).propose(
        agent_input=LearningAgentInput(
            current_version_id=current_version.version_id,
            current_configuration=current_version.configuration,
            memory=memory.to_dict(),
            critique=critique.to_dict(),
            boundaries=dict(search.get("boundaries", {})),
            search_mode=str(search.get("mode", "neighborhood")),
            max_candidates=int(search.get("max_candidates", 5)),
        ),
        candidate_start=repository.next_candidate_number(),
    )
    if not candidates:
        if logger:
            logger.info("event=NO_CANDIDATES_GENERATED parent_version=%s", current_version.version_id)
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
        evaluations.append(evaluation)
        initial_decisions.append(decision)
        if logger:
            logger.info(
                "event=WALK_FORWARD_EVALUATED candidate_id=%s windows=%s status=%s sharpe=%s",
                candidate.candidate_id,
                len(evaluation.windows),
                decision.status.value,
                decision.candidate_metrics.sharpe_ratio,
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
