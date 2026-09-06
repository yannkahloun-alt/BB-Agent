"""Risk-sensitive deterministic evaluation and selection for M1 decisions.

The evaluator consumes #20 raw features. It does not invent commands, reconstruct
hidden state, search future turns, or turn uncertain ranges into midpoint facts.
Ranking-affecting policy is explicit and versioned so #22 can trace and replay it.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from itertools import product
from time import perf_counter_ns

from bb_agent.features import (
    EpistemicAssignment,
    EpistemicFeatureScenario,
    MetricRange,
    TacticalFeatures,
    extract_candidate_feature_scenarios,
    extract_candidate_features,
)
from bb_agent.mechanics import MechanicsAuthority
from bb_agent.results import ErrorCode, Problem, Result, ResultStatus
from bb_agent.serialization import canonical_sha256
from bb_agent.tactical_state import TacticalState

MODEL_VERSION = "risk-evaluator.v1"
CONFIG_VERSION = "m1-evaluation-profile.v2"
UNIT_VALUE_POLICY_VERSION = "m1-common-preservation.v1"
_TOLERANCE = 1e-9

StageTimingSink = Callable[[str, int], None]
StageObserver = Callable[[str], None]
CounterSink = Callable[[str, int], None]


@dataclass(frozen=True, slots=True)
class EvaluationWeights:
    """Versioned family weights; calibration may replace these generically."""

    enemy_effect: float = 1.25
    immediate_friendly_harm: float = 1.25
    post_action_exposure: float = 0.8
    position_control_protection: float = 0.8
    resource_future_capacity: float = 0.65
    tempo: float = 0.35


@dataclass(frozen=True, slots=True)
class EvaluationScales:
    """Interpretable raw-to-comparable normalization scales."""

    hp_damage: float = 60.0
    armor_damage: float = 100.0
    hostile_pressure: float = 3.0
    ranged_exposure: float = 3.0
    elevation_delta: float = 2.0
    elevation_contacts: float = 3.0
    formation_links: float = 2.0
    flanked_hostiles: float = 3.0
    open_reposition_tiles: float = 6.0
    action_points: float = 9.0
    fatigue_headroom: float = 60.0
    resource_units: float = 2.0


@dataclass(frozen=True, slots=True)
class EvaluationProfile:
    """All ranking-affecting M1 evaluator policy for one deterministic run."""

    version: str = CONFIG_VERSION
    weights: EvaluationWeights = EvaluationWeights()
    scales: EvaluationScales = EvaluationScales()
    tail_risk_weight: float = 2.5
    uncertainty_weight: float = 0.25
    near_tie_margin: float = 0.05
    max_self_death_probability: float | None = None

    def __post_init__(self) -> None:
        if not self.version:
            raise ValueError("evaluation profile version must be nonempty")
        nonnegative = (
            self.weights.enemy_effect,
            self.weights.immediate_friendly_harm,
            self.weights.post_action_exposure,
            self.weights.position_control_protection,
            self.weights.resource_future_capacity,
            self.weights.tempo,
            self.tail_risk_weight,
            self.uncertainty_weight,
            self.near_tie_margin,
        )
        if any(not math.isfinite(value) or value < 0 for value in nonnegative):
            raise ValueError(
                "evaluation weights and margins must be finite and nonnegative"
            )
        positive = (
            self.scales.hp_damage,
            self.scales.armor_damage,
            self.scales.hostile_pressure,
            self.scales.ranged_exposure,
            self.scales.elevation_delta,
            self.scales.elevation_contacts,
            self.scales.formation_links,
            self.scales.flanked_hostiles,
            self.scales.open_reposition_tiles,
            self.scales.action_points,
            self.scales.fatigue_headroom,
            self.scales.resource_units,
        )
        if any(not math.isfinite(value) or value <= 0 for value in positive):
            raise ValueError("evaluation scales must be finite and positive")
        threshold = self.max_self_death_probability
        if threshold is not None and (
            not math.isfinite(threshold) or not 0 <= threshold <= 1
        ):
            raise ValueError("death-probability guardrail must lie in [0, 1]")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(asdict(self))


@dataclass(frozen=True, slots=True)
class UnitValuePolicy:
    """External evaluation context for friendly-life preservation."""

    version: str = UNIT_VALUE_POLICY_VERSION
    default_value: float = 1.0
    actor_values: tuple[tuple[str, float], ...] = ()

    def __post_init__(self) -> None:
        if not self.version:
            raise ValueError("unit-value policy version must be nonempty")
        if not math.isfinite(self.default_value) or self.default_value <= 0:
            raise ValueError("default unit value must be finite and positive")
        normalized = tuple(sorted(self.actor_values))
        if len({actor_id for actor_id, _ in normalized}) != len(normalized):
            raise ValueError("unit-value policy contains duplicate actor IDs")
        for actor_id, value in normalized:
            if not actor_id:
                raise ValueError("unit-value actor ID must be nonempty")
            if not math.isfinite(value) or value <= 0:
                raise ValueError("unit values must be finite and positive")
        object.__setattr__(self, "actor_values", normalized)

    def value_for(self, actor_id: str) -> float:
        return next(
            (
                value
                for candidate_id, value in self.actor_values
                if candidate_id == actor_id
            ),
            self.default_value,
        )

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(asdict(self))


DEFAULT_EVALUATION_PROFILE = EvaluationProfile()
DEFAULT_UNIT_VALUE_POLICY = UnitValuePolicy()


@dataclass(frozen=True, slots=True)
class ComponentContribution:
    component_id: str
    normalized: MetricRange
    weight: float
    weighted: MetricRange
    selection_value: float


@dataclass(frozen=True, slots=True)
class TailRiskRecord:
    self_death_probability: MetricRange
    movement_interruption_probability: MetricRange
    unit_value: float
    penalty: MetricRange
    selection_penalty: float


@dataclass(frozen=True, slots=True)
class ExplanationFact:
    component_id: str
    contribution: float


@dataclass(frozen=True, slots=True)
class CandidateEvaluation:
    action_id: str
    evaluator_version: str
    evaluation_profile_version: str
    evaluation_profile_fingerprint: str
    unit_value_policy_version: str
    unit_value_policy_fingerprint: str
    features: TacticalFeatures
    components: tuple[ComponentContribution, ...]
    mean_tactical_value: float | None
    tactical_value_range: MetricRange
    base_selection_value: float
    tail_risk: TailRiskRecord
    uncertainty_span: float
    uncertainty_penalty: float
    ranking_value: float
    ranking_range: MetricRange
    irreversible_resource_cost: int
    guardrail_findings: tuple[str, ...]
    explanation_facts: tuple[ExplanationFact, ...]
    dominated_by: str | None = None
    information_sensitive: bool = False

    def __post_init__(self) -> None:
        reconciled = sum(fact.contribution for fact in self.explanation_facts)
        if not math.isclose(reconciled, self.ranking_value, abs_tol=1e-9):
            raise ValueError("explanation facts do not reconcile to ranking value")

    @property
    def guardrail_excluded(self) -> bool:
        return bool(self.guardrail_findings)


@dataclass(frozen=True, slots=True)
class TieBreakRecord:
    action_ids: tuple[str, ...]
    winner_action_id: str
    criteria: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DecisionSelection:
    candidates: tuple[CandidateEvaluation, ...]
    ranking: tuple[str, ...]
    chosen_action_id: str
    near_tie_groups: tuple[tuple[str, ...], ...]
    tie_breaks: tuple[TieBreakRecord, ...]
    information_sensitive: bool


@dataclass(frozen=True, slots=True)
class EpistemicRankingScenario:
    scenario_id: str
    assignments: tuple[EpistemicAssignment, ...]
    ranking: tuple[str, ...]
    chosen_action_id: str


@dataclass(frozen=True, slots=True)
class DecisionEvaluation:
    state_id: str
    information_profile: str
    evaluator_version: str
    evaluation_profile_version: str
    evaluation_profile_fingerprint: str
    unit_value_policy_version: str
    unit_value_policy_fingerprint: str
    mechanics_manifest_fingerprint: str
    candidates: tuple[CandidateEvaluation, ...]
    ranking: tuple[str, ...]
    chosen_action_id: str
    near_tie_groups: tuple[tuple[str, ...], ...]
    tie_breaks: tuple[TieBreakRecord, ...]
    epistemic_scenarios: tuple[EpistemicRankingScenario, ...]
    information_sensitive: bool


def _clip(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _selection_bounds(value: MetricRange) -> tuple[float, float]:
    assert value.selection_minimum is not None
    assert value.selection_maximum is not None
    return value.selection_minimum, value.selection_maximum


def _epistemic_bounds(value: MetricRange) -> tuple[float, float]:
    assert value.epistemic_minimum is not None
    assert value.epistemic_maximum is not None
    return value.epistemic_minimum, value.epistemic_maximum


def _multiply(value: MetricRange, multiplier: float) -> MetricRange:
    if multiplier < 0:
        raise ValueError("metric multiplier must be nonnegative")
    expected = None if value.expected is None else value.expected * multiplier
    selection_minimum, selection_maximum = _selection_bounds(value)
    epistemic_minimum, epistemic_maximum = _epistemic_bounds(value)
    return MetricRange(
        value.minimum * multiplier,
        value.maximum * multiplier,
        expected,
        selection_minimum=selection_minimum * multiplier,
        selection_maximum=selection_maximum * multiplier,
        epistemic_minimum=epistemic_minimum * multiplier,
        epistemic_maximum=epistemic_maximum * multiplier,
    )


def _normalized(
    value: MetricRange,
    scale: float,
    direction: float = 1.0,
) -> MetricRange:
    support = (
        _clip(direction * value.minimum / scale),
        _clip(direction * value.maximum / scale),
    )
    expected = (
        None if value.expected is None else _clip(direction * value.expected / scale)
    )
    selection_minimum, selection_maximum = _selection_bounds(value)
    selection = (
        _clip(direction * selection_minimum / scale),
        _clip(direction * selection_maximum / scale),
    )
    epistemic_minimum, epistemic_maximum = _epistemic_bounds(value)
    epistemic = (
        _clip(direction * epistemic_minimum / scale),
        _clip(direction * epistemic_maximum / scale),
    )
    return MetricRange(
        min(support),
        max(support),
        expected,
        selection_minimum=min(selection),
        selection_maximum=max(selection),
        epistemic_minimum=min(epistemic),
        epistemic_maximum=max(epistemic),
    )


def _average(values: tuple[MetricRange, ...]) -> MetricRange:
    if not values:
        return MetricRange.exact(0)
    count = len(values)
    expected = None
    if all(value.expected is not None for value in values):
        expected = (
            sum(value.expected for value in values if value.expected is not None)
            / count
        )
    selection = tuple(_selection_bounds(value) for value in values)
    epistemic = tuple(_epistemic_bounds(value) for value in values)
    return MetricRange(
        sum(value.minimum for value in values) / count,
        sum(value.maximum for value in values) / count,
        expected,
        selection_minimum=sum(bounds[0] for bounds in selection) / count,
        selection_maximum=sum(bounds[1] for bounds in selection) / count,
        epistemic_minimum=sum(bounds[0] for bounds in epistemic) / count,
        epistemic_maximum=sum(bounds[1] for bounds in epistemic) / count,
    )


def _weighted(value: MetricRange, weight: float) -> MetricRange:
    expected = None if value.expected is None else value.expected * weight
    selection_minimum, selection_maximum = _selection_bounds(value)
    epistemic_minimum, epistemic_maximum = _epistemic_bounds(value)
    return MetricRange(
        value.minimum * weight,
        value.maximum * weight,
        expected,
        selection_minimum=selection_minimum * weight,
        selection_maximum=selection_maximum * weight,
        epistemic_minimum=epistemic_minimum * weight,
        epistemic_maximum=epistemic_maximum * weight,
    )


def _add(values: tuple[MetricRange, ...]) -> MetricRange:
    if not values:
        return MetricRange.exact(0)
    expected = None
    if all(value.expected is not None for value in values):
        expected = sum(value.expected for value in values if value.expected is not None)
    selection = tuple(_selection_bounds(value) for value in values)
    epistemic = tuple(_epistemic_bounds(value) for value in values)
    return MetricRange(
        sum(value.minimum for value in values),
        sum(value.maximum for value in values),
        expected,
        selection_minimum=sum(bounds[0] for bounds in selection),
        selection_maximum=sum(bounds[1] for bounds in selection),
        epistemic_minimum=sum(bounds[0] for bounds in epistemic),
        epistemic_maximum=sum(bounds[1] for bounds in epistemic),
    )


def _subtract(left: MetricRange, right: MetricRange) -> MetricRange:
    expected = None
    if left.expected is not None and right.expected is not None:
        expected = left.expected - right.expected
    left_selection = _selection_bounds(left)
    right_selection = _selection_bounds(right)
    left_epistemic = _epistemic_bounds(left)
    right_epistemic = _epistemic_bounds(right)
    return MetricRange(
        left.minimum - right.maximum,
        left.maximum - right.minimum,
        expected,
        selection_minimum=left_selection[0] - right_selection[1],
        selection_maximum=left_selection[1] - right_selection[0],
        epistemic_minimum=left_epistemic[0] - right_epistemic[1],
        epistemic_maximum=left_epistemic[1] - right_epistemic[0],
    )


def _shift(value: MetricRange, amount: float) -> MetricRange:
    expected = None if value.expected is None else value.expected + amount
    selection_minimum, selection_maximum = _selection_bounds(value)
    epistemic_minimum, epistemic_maximum = _epistemic_bounds(value)
    return MetricRange(
        value.minimum + amount,
        value.maximum + amount,
        expected,
        selection_minimum=selection_minimum + amount,
        selection_maximum=selection_maximum + amount,
        epistemic_minimum=epistemic_minimum + amount,
        epistemic_maximum=epistemic_maximum + amount,
    )


def _selection_value(value: MetricRange) -> float:
    """Use expectation when justified, otherwise the conservative lower bound."""

    if value.expected is not None:
        return value.expected
    selection_minimum, _ = _selection_bounds(value)
    return selection_minimum


def _penalty_selection(value: MetricRange) -> float:
    """Use expectation when justified, otherwise the conservative upper loss."""

    if value.expected is not None:
        return value.expected
    _, selection_maximum = _selection_bounds(value)
    return selection_maximum


def _component(
    component_id: str,
    terms: tuple[MetricRange, ...],
    weight: float,
) -> ComponentContribution:
    normalized = _average(terms)
    weighted = _weighted(normalized, weight)
    return ComponentContribution(
        component_id,
        normalized,
        weight,
        weighted,
        _selection_value(weighted),
    )


def _enemy_component(
    features: TacticalFeatures,
    profile: EvaluationProfile,
) -> ComponentContribution:
    scales = profile.scales
    return _component(
        "enemy_effect",
        (
            _normalized(
                features.enemy_effect.expected_hp_damage,
                scales.hp_damage,
            ),
            _normalized(
                features.enemy_effect.expected_armor_damage,
                scales.armor_damage,
            ),
            _normalized(features.enemy_effect.kill_probability, 1.0),
        ),
        profile.weights.enemy_effect,
    )


def _friendly_component(
    features: TacticalFeatures,
    profile: EvaluationProfile,
    actor_value: float,
    ally_value: float,
) -> ComponentContribution:
    scales = profile.scales
    return _component(
        "immediate_friendly_harm",
        (
            _normalized(
                _multiply(
                    features.friendly_harm.expected_self_hp_damage,
                    actor_value,
                ),
                scales.hp_damage,
                -1.0,
            ),
            _normalized(
                _multiply(
                    features.friendly_harm.expected_ally_hp_damage,
                    ally_value,
                ),
                scales.hp_damage,
                -1.0,
            ),
            _normalized(
                features.friendly_harm.movement_interruption_probability,
                1.0,
                -1.0,
            ),
        ),
        profile.weights.immediate_friendly_harm,
    )


def _exposure_component(
    features: TacticalFeatures,
    profile: EvaluationProfile,
) -> ComponentContribution:
    scales = profile.scales
    return _component(
        "post_action_exposure",
        (
            _normalized(
                features.threat.adjacent_hostile_pressure,
                scales.hostile_pressure,
                -1.0,
            ),
            _normalized(
                features.threat.hostile_zoc_pressure,
                scales.hostile_pressure,
                -1.0,
            ),
            _normalized(
                features.threat.ranged_los_exposure,
                scales.ranged_exposure,
                -1.0,
            ),
        ),
        profile.weights.post_action_exposure,
    )


def _position_component(
    features: TacticalFeatures,
    profile: EvaluationProfile,
) -> ComponentContribution:
    scales = profile.scales
    return _component(
        "position_control_ally_protection",
        (
            _normalized(
                features.position.elevation_change,
                scales.elevation_delta,
            ),
            _normalized(
                features.position.elevation_advantage_contacts,
                scales.elevation_contacts,
            ),
            _normalized(
                features.position.elevation_disadvantage_contacts,
                scales.elevation_contacts,
                -1.0,
            ),
            _normalized(
                features.formation.created_direct_screen_links,
                scales.formation_links,
            ),
            _normalized(
                features.formation.lost_direct_screen_links,
                scales.formation_links,
                -1.0,
            ),
            _normalized(
                features.control.flanked_hostiles,
                scales.flanked_hostiles,
            ),
            _normalized(
                features.mobility.open_adjacent_reposition_tiles,
                scales.open_reposition_tiles,
            ),
        ),
        profile.weights.position_control_protection,
    )


def _resource_component(
    features: TacticalFeatures,
    profile: EvaluationProfile,
) -> ComponentContribution:
    scales = profile.scales
    template_count = features.future_capacity.current_cost_template_count
    template_scale = max(1.0, float(template_count))
    return _component(
        "resource_fat_future_capacity",
        (
            _normalized(
                features.resources.remaining_action_points,
                scales.action_points,
            ),
            _normalized(
                features.resources.fatigue_headroom,
                scales.fatigue_headroom,
            ),
            _normalized(
                features.future_capacity.ap_fat_feasible_template_count,
                template_scale,
            ),
            _normalized(
                MetricRange.exact(features.resources.ammo_consumed),
                scales.resource_units,
                -1.0,
            ),
            _normalized(
                MetricRange.exact(features.resources.charges_consumed),
                scales.resource_units,
                -1.0,
            ),
        ),
        profile.weights.resource_future_capacity,
    )


def _tempo_component(
    features: TacticalFeatures,
    profile: EvaluationProfile,
) -> ComponentContribution:
    return _component(
        "tempo_turn_order",
        (
            _normalized(features.tempo.actor_has_waited, 1.0),
            _normalized(features.tempo.actor_may_wait, 1.0),
            _normalized(features.tempo.turn_ended, 1.0, -1.0),
        ),
        profile.weights.tempo,
    )


def _components(
    features: TacticalFeatures,
    profile: EvaluationProfile,
    actor_value: float,
    ally_value: float,
) -> tuple[ComponentContribution, ...]:
    return (
        _enemy_component(features, profile),
        _friendly_component(
            features,
            profile,
            actor_value,
            ally_value,
        ),
        _exposure_component(features, profile),
        _position_component(features, profile),
        _resource_component(features, profile),
        _tempo_component(features, profile),
    )


def _tail_risk(
    features: TacticalFeatures,
    profile: EvaluationProfile,
    unit_value: float,
) -> TailRiskRecord:
    death = features.friendly_harm.self_death_probability
    multiplier = profile.tail_risk_weight * unit_value
    penalty = _multiply(death, multiplier)
    return TailRiskRecord(
        death,
        features.friendly_harm.movement_interruption_probability,
        unit_value,
        penalty,
        _penalty_selection(penalty),
    )


def score_candidate_features(
    features: TacticalFeatures,
    actor_id: str,
    profile: EvaluationProfile = DEFAULT_EVALUATION_PROFILE,
    unit_value_policy: UnitValuePolicy = DEFAULT_UNIT_VALUE_POLICY,
) -> CandidateEvaluation:
    """Score one feature record without changing or hiding its raw values."""

    if not actor_id:
        raise ValueError("actor_id must be nonempty")
    actor_value = unit_value_policy.value_for(actor_id)
    components = _components(
        features,
        profile,
        actor_value,
        unit_value_policy.default_value,
    )
    tactical_range = _add(tuple(component.weighted for component in components))
    base_selection_value = sum(component.selection_value for component in components)
    tail = _tail_risk(features, profile, actor_value)
    before_uncertainty = _subtract(tactical_range, tail.penalty)
    epistemic_minimum, epistemic_maximum = _epistemic_bounds(before_uncertainty)
    uncertainty_span = epistemic_maximum - epistemic_minimum
    uncertainty_penalty = profile.uncertainty_weight * uncertainty_span
    ranking_range = _shift(before_uncertainty, -uncertainty_penalty)
    ranking_value = base_selection_value - tail.selection_penalty - uncertainty_penalty
    irreversible_resource_cost = (
        features.resources.ammo_consumed + features.resources.charges_consumed
    )

    findings: tuple[str, ...] = ()
    threshold = profile.max_self_death_probability
    if threshold is not None and (tail.self_death_probability.maximum > threshold):
        findings = ("MAX_SELF_DEATH_PROBABILITY",)

    explanation = tuple(
        ExplanationFact(
            component.component_id,
            component.selection_value,
        )
        for component in components
    ) + (
        ExplanationFact(
            "tail_risk_penalty",
            -tail.selection_penalty,
        ),
        ExplanationFact(
            "uncertainty_robustness_adjustment",
            -uncertainty_penalty,
        ),
    )
    return CandidateEvaluation(
        features.action_id,
        MODEL_VERSION,
        profile.version,
        profile.fingerprint,
        unit_value_policy.version,
        unit_value_policy.fingerprint,
        features,
        components,
        tactical_range.expected,
        tactical_range,
        base_selection_value,
        tail,
        uncertainty_span,
        uncertainty_penalty,
        ranking_value,
        ranking_range,
        irreversible_resource_cost,
        findings,
        explanation,
    )


def _dominates(
    left: CandidateEvaluation,
    right: CandidateEvaluation,
) -> bool:
    benefit_no_worse = (
        left.tactical_value_range.minimum
        >= right.tactical_value_range.maximum - _TOLERANCE
    )
    risk_no_worse = (
        left.tail_risk.penalty.maximum <= right.tail_risk.penalty.minimum + _TOLERANCE
    )
    strictly_better = (
        left.tactical_value_range.minimum
        > right.tactical_value_range.maximum + _TOLERANCE
        or left.tail_risk.penalty.maximum < right.tail_risk.penalty.minimum - _TOLERANCE
    )
    return benefit_no_worse and risk_no_worse and strictly_better


def _with_dominance(
    candidates: tuple[CandidateEvaluation, ...],
) -> tuple[CandidateEvaluation, ...]:
    updated = []
    for candidate in candidates:
        dominators = sorted(
            other.action_id
            for other in candidates
            if other.action_id != candidate.action_id and _dominates(other, candidate)
        )
        updated.append(
            replace(
                candidate,
                dominated_by=dominators[0] if dominators else None,
            )
        )
    return tuple(updated)


def _tie_key(
    candidate: CandidateEvaluation,
) -> tuple[float, float, int, str]:
    return (
        candidate.tail_risk.selection_penalty,
        candidate.uncertainty_span,
        candidate.irreversible_resource_cost,
        candidate.action_id,
    )


def _score_groups(
    candidates: tuple[CandidateEvaluation, ...],
    margin: float,
) -> tuple[tuple[CandidateEvaluation, ...], ...]:
    pending = list(
        sorted(
            candidates,
            key=lambda item: (-item.ranking_value, item.action_id),
        )
    )
    groups = []
    while pending:
        anchor = pending[0].ranking_value
        group = []
        while pending and anchor - pending[0].ranking_value <= margin + _TOLERANCE:
            group.append(pending.pop(0))
        groups.append(tuple(sorted(group, key=_tie_key)))
    return tuple(groups)


def select_candidate_evaluations(
    candidates: tuple[CandidateEvaluation, ...],
    profile: EvaluationProfile = DEFAULT_EVALUATION_PROFILE,
) -> DecisionSelection:
    """Apply dominance diagnostics, guardrails, near ties, and frozen ties."""

    if not candidates:
        raise ValueError("selection requires at least one candidate")
    if len({candidate.action_id for candidate in candidates}) != len(candidates):
        raise ValueError("selection requires unique action IDs")

    candidates = _with_dominance(candidates)
    eligible = tuple(
        candidate for candidate in candidates if not candidate.guardrail_excluded
    )
    excluded = tuple(
        candidate for candidate in candidates if candidate.guardrail_excluded
    )
    partitions = (eligible, excluded) if eligible else (excluded,)
    ordered_groups = tuple(
        group
        for partition in partitions
        if partition
        for group in _score_groups(
            partition,
            profile.near_tie_margin,
        )
    )
    ordered = tuple(candidate for group in ordered_groups for candidate in group)
    near_ties = tuple(
        tuple(candidate.action_id for candidate in group)
        for group in ordered_groups
        if len(group) > 1
    )
    criteria = (
        "lower_tail_risk",
        "lower_epistemic_uncertainty",
        "lower_irreversible_resource_cost",
        "stable_action_id",
    )
    tie_breaks = tuple(
        TieBreakRecord(
            tuple(candidate.action_id for candidate in group),
            group[0].action_id,
            criteria,
        )
        for group in ordered_groups
        if len(group) > 1
    )
    chosen = ordered[0]
    return DecisionSelection(
        ordered,
        tuple(candidate.action_id for candidate in ordered),
        chosen.action_id,
        near_ties,
        tie_breaks,
        chosen.information_sensitive,
    )


def _assignment_domain_key(
    assignments: tuple[EpistemicAssignment, ...],
) -> tuple[tuple[str, str], ...]:
    return tuple((assignment.actor_id, assignment.field) for assignment in assignments)


def _assignment_sort_key(
    assignments: tuple[EpistemicAssignment, ...],
) -> tuple[tuple[str, str, int], ...]:
    return tuple(
        (assignment.actor_id, assignment.field, assignment.value)
        for assignment in assignments
    )


def _joint_epistemic_assignments(
    scenario_features: dict[str, tuple[EpistemicFeatureScenario, ...]],
) -> tuple[tuple[EpistemicAssignment, ...], ...]:
    domains: dict[
        tuple[tuple[str, str], ...],
        set[tuple[EpistemicAssignment, ...]],
    ] = {}
    for scenarios in scenario_features.values():
        for scenario in scenarios:
            key = _assignment_domain_key(scenario.assignments)
            domains.setdefault(key, set()).add(scenario.assignments)
    if not domains:
        return ()

    ordered_domains = tuple(
        tuple(sorted(domains[key], key=_assignment_sort_key)) for key in sorted(domains)
    )
    joint: set[tuple[EpistemicAssignment, ...]] = set()
    for combination in product(*ordered_domains):
        merged: dict[tuple[str, str], EpistemicAssignment] = {}
        compatible = True
        for assignments in combination:
            for assignment in assignments:
                key = (assignment.actor_id, assignment.field)
                existing = merged.get(key)
                if existing is not None and existing.value != assignment.value:
                    compatible = False
                    break
                merged[key] = assignment
            if not compatible:
                break
        if compatible:
            joint.add(tuple(sorted(merged.values())))
    return tuple(sorted(joint, key=_assignment_sort_key))


def _scenario_candidate(
    base: CandidateEvaluation,
    joint: dict[tuple[str, str], int],
    scenario_evaluations: dict[
        str,
        tuple[tuple[tuple[EpistemicAssignment, ...], CandidateEvaluation], ...],
    ],
) -> CandidateEvaluation:
    matches = []
    for assignments, evaluation in scenario_evaluations.get(base.action_id, ()):
        if all(
            joint.get((assignment.actor_id, assignment.field)) == assignment.value
            for assignment in assignments
        ):
            matches.append(evaluation)
    if len(matches) > 1:
        raise ValueError("multiple scenario evaluations matched one joint hidden state")
    return matches[0] if matches else base


def _apply_epistemic_sensitivity(
    selection: DecisionSelection,
    scenario_features: dict[str, tuple[EpistemicFeatureScenario, ...]],
    scenario_evaluations: dict[
        str,
        tuple[tuple[tuple[EpistemicAssignment, ...], CandidateEvaluation], ...],
    ],
    profile: EvaluationProfile,
) -> tuple[DecisionSelection, tuple[EpistemicRankingScenario, ...]]:
    joint_assignments = _joint_epistemic_assignments(scenario_features)
    if not joint_assignments:
        return selection, ()

    rank_positions = {candidate.action_id: set() for candidate in selection.candidates}
    chosen_action_ids: set[str] = set()
    records = []
    for assignments in joint_assignments:
        joint = {
            (assignment.actor_id, assignment.field): assignment.value
            for assignment in assignments
        }
        candidates = tuple(
            _scenario_candidate(candidate, joint, scenario_evaluations)
            for candidate in selection.candidates
        )
        scenario_selection = select_candidate_evaluations(candidates, profile)
        for rank, action_id in enumerate(scenario_selection.ranking):
            rank_positions[action_id].add(rank)
        chosen_action_ids.add(scenario_selection.chosen_action_id)
        scenario_id = canonical_sha256(
            tuple(
                (assignment.actor_id, assignment.field, assignment.value)
                for assignment in assignments
            )
        )
        records.append(
            EpistemicRankingScenario(
                scenario_id,
                assignments,
                scenario_selection.ranking,
                scenario_selection.chosen_action_id,
            )
        )

    updated_candidates = tuple(
        replace(
            candidate,
            information_sensitive=len(rank_positions[candidate.action_id]) > 1,
        )
        for candidate in selection.candidates
    )
    return (
        replace(
            selection,
            candidates=updated_candidates,
            information_sensitive=len(chosen_action_ids) > 1,
        ),
        tuple(records),
    )


def evaluate_decision(
    authority: MechanicsAuthority,
    state: TacticalState,
    profile: EvaluationProfile = DEFAULT_EVALUATION_PROFILE,
    unit_value_policy: UnitValuePolicy = DEFAULT_UNIT_VALUE_POLICY,
    *,
    timing_sink: StageTimingSink | None = None,
    stage_observer: StageObserver | None = None,
    counter_sink: CounterSink | None = None,
) -> Result[DecisionEvaluation]:
    """Evaluate the complete canonical current affordance set fail-closed.

    Optional diagnostics sinks observe elapsed stage time and deterministic
    counters without becoming ranking inputs or part of decision identity.
    """

    def record_timing(stage: str, started_ns: int) -> None:
        if timing_sink is not None:
            timing_sink(stage, perf_counter_ns() - started_ns)

    def record_stage(stage: str) -> None:
        if stage_observer is not None:
            stage_observer(stage)

    def record_counter(name: str, value: int) -> None:
        if counter_sink is not None:
            counter_sink(name, value)

    record_stage("validation")
    stage_started = perf_counter_ns()
    try:
        normalized = state.normalized()
    except (TypeError, ValueError) as exc:
        record_timing("validation", stage_started)
        record_counter("validation_problem_count", 1)
        return Result.validation_failure(
            Problem(
                ErrorCode.VALIDATION_FAILED,
                str(exc),
                "state",
            )
        )
    except Exception:
        record_timing("validation", stage_started)
        raise
    record_timing("validation", stage_started)

    record_stage("coverage")
    stage_started = perf_counter_ns()
    try:
        coverage = authority.classify(normalized)
    finally:
        record_timing("coverage", stage_started)
    record_counter("coverage_problem_count", len(coverage.problems))
    if coverage.status is not ResultStatus.SUCCESS:
        return Result(
            coverage.status,
            problems=coverage.problems,
        )
    if not normalized.action_affordances.actions:
        record_counter("validation_problem_count", 1)
        return Result.validation_failure(
            Problem(
                ErrorCode.VALIDATION_FAILED,
                "complete affordance set contains no current actions",
                "action_affordances.actions",
            )
        )

    evaluations = []
    scenario_features: dict[str, tuple[EpistemicFeatureScenario, ...]] = {}
    scenario_evaluations: dict[
        str,
        tuple[tuple[tuple[EpistemicAssignment, ...], CandidateEvaluation], ...],
    ] = {}
    actions = sorted(
        normalized.action_affordances.actions,
        key=lambda candidate: candidate.action_id,
    )
    record_counter("legal_candidate_count", len(actions))
    epistemic_input_scenarios = 0
    for action in actions:
        record_stage("outcome_and_features")
        stage_started = perf_counter_ns()
        try:
            feature_result = extract_candidate_features(
                authority,
                normalized,
                action.action_id,
            )
            if feature_result.value is None:
                record_counter("evaluated_candidate_count", len(evaluations))
                return Result(
                    feature_result.status,
                    problems=feature_result.problems,
                )
            scenario_result = extract_candidate_feature_scenarios(
                authority,
                normalized,
                action.action_id,
            )
        finally:
            record_timing("outcome_and_features", stage_started)
        if scenario_result.value is None:
            record_counter("evaluated_candidate_count", len(evaluations))
            return Result(
                scenario_result.status,
                problems=scenario_result.problems,
            )
        scenario_features[action.action_id] = scenario_result.value
        epistemic_input_scenarios += len(scenario_result.value)

        record_stage("scoring")
        stage_started = perf_counter_ns()
        try:
            evaluations.append(
                score_candidate_features(
                    feature_result.value,
                    action.actor_id,
                    profile,
                    unit_value_policy,
                )
            )
            scenario_evaluations[action.action_id] = tuple(
                (
                    scenario.assignments,
                    score_candidate_features(
                        scenario.features,
                        action.actor_id,
                        profile,
                        unit_value_policy,
                    ),
                )
                for scenario in scenario_result.value
            )
        finally:
            record_timing("scoring", stage_started)
        record_counter("evaluated_candidate_count", len(evaluations))

    record_counter("epistemic_input_scenario_count", epistemic_input_scenarios)
    record_stage("selection")
    stage_started = perf_counter_ns()
    try:
        selection = select_candidate_evaluations(
            tuple(evaluations),
            profile,
        )
        selection, epistemic_scenarios = _apply_epistemic_sensitivity(
            selection,
            scenario_features,
            scenario_evaluations,
            profile,
        )
    finally:
        record_timing("selection", stage_started)
    record_counter("epistemic_ranking_scenario_count", len(epistemic_scenarios))
    assert coverage.value is not None
    return Result.success(
        DecisionEvaluation(
            normalized.state_id,
            normalized.information_profile.value,
            MODEL_VERSION,
            profile.version,
            profile.fingerprint,
            unit_value_policy.version,
            unit_value_policy.fingerprint,
            coverage.value.manifest_fingerprint,
            selection.candidates,
            selection.ranking,
            selection.chosen_action_id,
            selection.near_tie_groups,
            selection.tie_breaks,
            epistemic_scenarios,
            selection.information_sensitive,
        )
    )
