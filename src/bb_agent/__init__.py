"""Foundations for the offline BB-Agent decision kernel."""

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
    "OutcomeBranch",
    "evaluate_ordinary_attack",
    "load_fixture",
    "save_fixture",
    "validate_fixture_pair",
]
