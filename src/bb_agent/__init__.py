"""Foundations for the offline BB-Agent decision kernel."""

from bb_agent.evaluator import (
    CONFIG_VERSION as EVALUATION_CONFIG_VERSION,
)
from bb_agent.evaluator import (
    MODEL_VERSION as EVALUATOR_MODEL_VERSION,
)
from bb_agent.evaluator import (
    CandidateEvaluation,
    DEFAULT_EVALUATION_PROFILE,
    DEFAULT_UNIT_VALUE_POLICY,
    DecisionEvaluation,
    DecisionSelection,
    EvaluationProfile,
    EvaluationScales,
    EvaluationWeights,
    UnitValuePolicy,
    evaluate_decision,
    score_candidate_features,
    select_candidate_evaluations,
)
from bb_agent.features import (
    MODEL_VERSION as TACTICAL_FEATURE_MODEL_VERSION,
)
from bb_agent.features import (
    MetricRange,
    TacticalFeatures,
    extract_candidate_features,
)
from bb_agent.fixtures import (
    FixtureEnvelope,
    FixtureMetadata,
    ReplayInput,
    load_fixture,
    save_fixture,
    validate_fixture_pair,
)
from bb_agent.outcomes import AttackOutcome, OutcomeBranch, evaluate_ordinary_attack
from bb_agent.tactical_state import TacticalState
from bb_agent.versions import CURRENT_VERSIONS, ContractVersions

__all__ = [
    "CURRENT_VERSIONS",
    "ContractVersions",
    "FixtureEnvelope",
    "FixtureMetadata",
    "ReplayInput",
    "TacticalState",
    "AttackOutcome",
    "CandidateEvaluation",
    "DEFAULT_EVALUATION_PROFILE",
    "DEFAULT_UNIT_VALUE_POLICY",
    "DecisionEvaluation",
    "DecisionSelection",
    "EVALUATION_CONFIG_VERSION",
    "EVALUATOR_MODEL_VERSION",
    "EvaluationProfile",
    "EvaluationScales",
    "EvaluationWeights",
    "MetricRange",
    "OutcomeBranch",
    "TACTICAL_FEATURE_MODEL_VERSION",
    "TacticalFeatures",
    "UnitValuePolicy",
    "evaluate_decision",
    "evaluate_ordinary_attack",
    "extract_candidate_features",
    "load_fixture",
    "save_fixture",
    "score_candidate_features",
    "select_candidate_evaluations",
    "validate_fixture_pair",
]
