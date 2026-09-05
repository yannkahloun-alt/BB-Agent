from __future__ import annotations

import re
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"expected one replacement in {path}, found {text.count(old)}")
    file_path.write_text(text.replace(old, new), encoding="utf-8")


def regex_once(path: str, pattern: str, replacement: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"expected one regex replacement in {path}, found {count}")
    file_path.write_text(updated, encoding="utf-8")


# Preserve raw support while separately carrying the robust selection envelope
# and the epistemic projection after aleatory probabilities have been integrated.
replace_once(
    "src/bb_agent/features.py",
    '''@dataclass(frozen=True, slots=True)\nclass MetricRange:\n    """A raw metric with bounds and an optional justified expectation."""\n\n    minimum: float\n    maximum: float\n    expected: float | None = None\n\n    def __post_init__(self) -> None:\n        if not math.isfinite(self.minimum) or not math.isfinite(self.maximum):\n            raise ValueError("feature bounds must be finite")\n        if self.minimum > self.maximum:\n            raise ValueError("feature minimum exceeds maximum")\n        if self.expected is not None:\n            if not math.isfinite(self.expected):\n                raise ValueError("feature expectation must be finite")\n            if not self.minimum - 1e-9 <= self.expected <= self.maximum + 1e-9:\n                raise ValueError("feature expectation lies outside its bounds")\n\n    @classmethod\n    def exact(cls, value: int | float) -> MetricRange:\n        number = float(value)\n        return cls(number, number, number)\n''',
    '''@dataclass(frozen=True, slots=True)\nclass MetricRange:\n    """Raw support plus robust and epistemic projections for one metric.\n\n    ``minimum``/``maximum`` preserve all represented variation, including\n    aleatory branch support. ``selection_*`` integrates justified aleatory\n    probabilities before retaining any non-probabilistic robustness envelope.\n    ``epistemic_*`` is narrower still: it tracks only hidden-information\n    variation that may legitimately drive #6 information sensitivity.\n    """\n\n    minimum: float\n    maximum: float\n    expected: float | None = None\n    selection_minimum: float | None = None\n    selection_maximum: float | None = None\n    epistemic_minimum: float | None = None\n    epistemic_maximum: float | None = None\n\n    def __post_init__(self) -> None:\n        if not math.isfinite(self.minimum) or not math.isfinite(self.maximum):\n            raise ValueError("feature bounds must be finite")\n        if self.minimum > self.maximum:\n            raise ValueError("feature minimum exceeds maximum")\n        if self.expected is not None:\n            if not math.isfinite(self.expected):\n                raise ValueError("feature expectation must be finite")\n            if not self.minimum - 1e-9 <= self.expected <= self.maximum + 1e-9:\n                raise ValueError("feature expectation lies outside its bounds")\n\n        selection_minimum = self.selection_minimum\n        selection_maximum = self.selection_maximum\n        if (selection_minimum is None) != (selection_maximum is None):\n            raise ValueError("selection projection requires both bounds")\n        if selection_minimum is None:\n            if self.expected is not None:\n                selection_minimum = self.expected\n                selection_maximum = self.expected\n            else:\n                selection_minimum = self.minimum\n                selection_maximum = self.maximum\n\n        epistemic_minimum = self.epistemic_minimum\n        epistemic_maximum = self.epistemic_maximum\n        if (epistemic_minimum is None) != (epistemic_maximum is None):\n            raise ValueError("epistemic projection requires both bounds")\n        if epistemic_minimum is None:\n            if self.expected is not None:\n                epistemic_minimum = self.expected\n                epistemic_maximum = self.expected\n            else:\n                epistemic_minimum = selection_minimum\n                epistemic_maximum = selection_maximum\n\n        projected = (\n            selection_minimum,\n            selection_maximum,\n            epistemic_minimum,\n            epistemic_maximum,\n        )\n        if any(not math.isfinite(value) for value in projected):\n            raise ValueError("feature projections must be finite")\n        if selection_minimum > selection_maximum:\n            raise ValueError("selection projection minimum exceeds maximum")\n        if epistemic_minimum > epistemic_maximum:\n            raise ValueError("epistemic projection minimum exceeds maximum")\n        if not self.minimum - 1e-9 <= selection_minimum <= self.maximum + 1e-9:\n            raise ValueError("selection minimum lies outside raw support")\n        if not self.minimum - 1e-9 <= selection_maximum <= self.maximum + 1e-9:\n            raise ValueError("selection maximum lies outside raw support")\n        if not self.minimum - 1e-9 <= epistemic_minimum <= self.maximum + 1e-9:\n            raise ValueError("epistemic minimum lies outside raw support")\n        if not self.minimum - 1e-9 <= epistemic_maximum <= self.maximum + 1e-9:\n            raise ValueError("epistemic maximum lies outside raw support")\n\n        object.__setattr__(self, "selection_minimum", selection_minimum)\n        object.__setattr__(self, "selection_maximum", selection_maximum)\n        object.__setattr__(self, "epistemic_minimum", epistemic_minimum)\n        object.__setattr__(self, "epistemic_maximum", epistemic_maximum)\n\n    @classmethod\n    def exact(cls, value: int | float) -> MetricRange:\n        number = float(value)\n        return cls(number, number, number)\n\n    @property\n    def epistemic_span(self) -> float:\n        assert self.epistemic_minimum is not None\n        assert self.epistemic_maximum is not None\n        return self.epistemic_maximum - self.epistemic_minimum\n''',
)

replace_once(
    "src/bb_agent/features.py",
    '''    semantic_ownership: tuple[FeatureOwnership, ...] = SEMANTIC_OWNERSHIP\n\n\n@dataclass(frozen=True, slots=True)\nclass _PostureBranch:\n''',
    '''    semantic_ownership: tuple[FeatureOwnership, ...] = SEMANTIC_OWNERSHIP\n\n\n@dataclass(frozen=True, slots=True, order=True)\nclass EpistemicAssignment:\n    """One concrete hidden-state fact used by a coherent player-legal scenario."""\n\n    actor_id: str\n    field: str\n    value: int\n\n\n@dataclass(frozen=True, slots=True)\nclass EpistemicFeatureScenario:\n    """Scenario-specific tactical features after integrating combat RNG."""\n\n    scenario_id: str\n    assignments: tuple[EpistemicAssignment, ...]\n    features: TacticalFeatures\n\n\n@dataclass(frozen=True, slots=True)\nclass _PostureBranch:\n''',
)

replace_once(
    "src/bb_agent/features.py",
    '''def _weighted_range(\n    values: Iterable[tuple[float, MetricRange]],\n) -> MetricRange:\n    items = tuple(values)\n    if not items:\n        return MetricRange.exact(0)\n    minimum = min(metric.minimum for _, metric in items)\n    maximum = max(metric.maximum for _, metric in items)\n    total_probability = sum(probability for probability, _ in items)\n    expected = None\n    if abs(total_probability - 1.0) <= 1e-9 and all(\n        metric.expected is not None for _, metric in items\n    ):\n        expected = sum(\n            probability * metric.expected  # type: ignore[operator]\n            for probability, metric in items\n        )\n    return MetricRange(minimum, maximum, expected)\n''',
    '''def _weighted_range(\n    values: Iterable[tuple[float, MetricRange]],\n) -> MetricRange:\n    items = tuple(values)\n    if not items:\n        return MetricRange.exact(0)\n    minimum = min(metric.minimum for _, metric in items)\n    maximum = max(metric.maximum for _, metric in items)\n    total_probability = sum(probability for probability, _ in items)\n    normalized_probability = abs(total_probability - 1.0) <= 1e-9\n    expected = None\n    if normalized_probability and all(\n        metric.expected is not None for _, metric in items\n    ):\n        expected = sum(\n            probability * metric.expected  # type: ignore[operator]\n            for probability, metric in items\n        )\n\n    if normalized_probability:\n        selection_minimum = sum(\n            probability * float(metric.selection_minimum)\n            for probability, metric in items\n        )\n        selection_maximum = sum(\n            probability * float(metric.selection_maximum)\n            for probability, metric in items\n        )\n        epistemic_minimum = sum(\n            probability * float(metric.epistemic_minimum)\n            for probability, metric in items\n        )\n        epistemic_maximum = sum(\n            probability * float(metric.epistemic_maximum)\n            for probability, metric in items\n        )\n        return MetricRange(\n            minimum,\n            maximum,\n            expected,\n            selection_minimum=selection_minimum,\n            selection_maximum=selection_maximum,\n            epistemic_minimum=epistemic_minimum,\n            epistemic_maximum=epistemic_maximum,\n        )\n    return MetricRange(minimum, maximum, expected)\n''',
)

replace_once(
    "src/bb_agent/features.py",
    '''    if adjacent_hostiles.maximum == 0:\n        hostile_zoc = MetricRange.exact(0)\n    else:\n        hostile_zoc = MetricRange(0, adjacent_hostiles.maximum)\n''',
    '''    if adjacent_hostiles.maximum == 0:\n        hostile_zoc = MetricRange.exact(0)\n    else:\n        # This is an intentionally bounded threat proxy, not hidden-state\n        # uncertainty. Keep the robust range but give it zero epistemic width.\n        hostile_zoc = MetricRange(\n            0,\n            adjacent_hostiles.maximum,\n            epistemic_minimum=0,\n            epistemic_maximum=0,\n        )\n''',
)

scenario_function = '''\n\ndef extract_candidate_feature_scenarios(\n    authority: MechanicsAuthority,\n    state: TacticalState,\n    action: CandidateReference,\n) -> Result[tuple[EpistemicFeatureScenario, ...]]:\n    """Preserve coherent unweighted hidden-state scenarios for #21 ranking.\n\n    Ordinary-attack outcomes already separate one plausible hidden target state\n    from its complete aleatory RNG distribution. This adapter converts each such\n    state into scenario-specific tactical features by integrating the RNG inside\n    that scenario. It deliberately does not synthesize scenarios from unrelated\n    per-metric bounds.\n    """\n\n    candidate = resolve_current_candidate(authority, state, action)\n    if candidate.value is None:\n        return Result(candidate.status, problems=candidate.problems)\n    if "ordinary_attack" not in candidate.value.structural_coverage.family_ids:\n        return Result.success(())\n\n    canonical_state = candidate.value.state\n    canonical_action = candidate.value.action\n    attack_result = evaluate_ordinary_attack(\n        authority,\n        canonical_state,\n        canonical_action.action_id,\n    )\n    if attack_result.value is None:\n        return Result(attack_result.status, problems=attack_result.problems)\n    attack = attack_result.value\n    if not attack.epistemic_scenarios:\n        return Result.success(())\n\n    try:\n        if canonical_action.target_actor_id is None:\n            _invalid(canonical_action, "epistemic attack scenario has no target actor")\n        target_actor_id = canonical_action.target_actor_id\n        scenarios = []\n        for scenario in sorted(\n            attack.epistemic_scenarios,\n            key=lambda item: (\n                item.target_hp,\n                item.target_head_armor,\n                item.target_body_armor,\n            ),\n        ):\n            assignments = (\n                EpistemicAssignment(\n                    target_actor_id,\n                    "resources.hit_points",\n                    scenario.target_hp,\n                ),\n                EpistemicAssignment(\n                    target_actor_id,\n                    "resources.head_armor",\n                    scenario.target_head_armor,\n                ),\n                EpistemicAssignment(\n                    target_actor_id,\n                    "resources.body_armor",\n                    scenario.target_body_armor,\n                ),\n            )\n            scenario_outcome = replace(\n                attack,\n                branches=scenario.branches,\n                epistemic_scenarios=(),\n                epistemic=False,\n            )\n            scenario_features = _build_features(\n                canonical_state,\n                canonical_action,\n                scenario_outcome,\n                None,\n            )\n            scenario_id = (\n                f"{target_actor_id}:hp={scenario.target_hp}:"\n                f"head={scenario.target_head_armor}:"\n                f"body={scenario.target_body_armor}"\n            )\n            scenarios.append(\n                EpistemicFeatureScenario(\n                    scenario_id,\n                    assignments,\n                    scenario_features,\n                )\n            )\n        return Result.success(tuple(scenarios))\n    except (EvaluationUnsupported, EvaluationInvalid) as exc:\n        return evaluation_failure_result(exc)\n'''
replace_once(
    "src/bb_agent/features.py",
    "\n\ndef extract_candidate_features(\n",
    scenario_function + "\n\ndef extract_candidate_features(\n",
)

# Export the new scenario-preserving feature seam.
replace_once(
    "src/bb_agent/__init__.py",
    '''from bb_agent.features import (\n    MetricRange,\n    TacticalFeatures,\n    extract_candidate_features,\n)\n''',
    '''from bb_agent.features import (\n    EpistemicAssignment,\n    EpistemicFeatureScenario,\n    MetricRange,\n    TacticalFeatures,\n    extract_candidate_feature_scenarios,\n    extract_candidate_features,\n)\n''',
)
replace_once(
    "src/bb_agent/__init__.py",
    '''    "EVALUATOR_MODEL_VERSION",\n    "EvaluationProfile",\n''',
    '''    "EVALUATOR_MODEL_VERSION",\n    "EpistemicAssignment",\n    "EpistemicFeatureScenario",\n    "EvaluationProfile",\n''',
)
replace_once(
    "src/bb_agent/__init__.py",
    '''    "evaluate_ordinary_attack",\n    "extract_candidate_features",\n''',
    '''    "evaluate_ordinary_attack",\n    "extract_candidate_feature_scenarios",\n    "extract_candidate_features",\n''',
)

# Evaluator: propagate raw/selection/epistemic projections through every transform.
replace_once(
    "src/bb_agent/evaluator.py",
    '''import math\nfrom dataclasses import asdict, dataclass, replace\n''',
    '''import math\nfrom dataclasses import asdict, dataclass, replace\nfrom itertools import product\n''',
)
replace_once(
    "src/bb_agent/evaluator.py",
    '''from bb_agent.features import (\n    MetricRange,\n    TacticalFeatures,\n    extract_candidate_features,\n)\n''',
    '''from bb_agent.features import (\n    EpistemicAssignment,\n    EpistemicFeatureScenario,\n    MetricRange,\n    TacticalFeatures,\n    extract_candidate_feature_scenarios,\n    extract_candidate_features,\n)\n''',
)

replace_once(
    "src/bb_agent/evaluator.py",
    '''@dataclass(frozen=True, slots=True)\nclass DecisionEvaluation:\n''',
    '''@dataclass(frozen=True, slots=True)\nclass EpistemicRankingScenario:\n    scenario_id: str\n    assignments: tuple[EpistemicAssignment, ...]\n    ranking: tuple[str, ...]\n    chosen_action_id: str\n\n\n@dataclass(frozen=True, slots=True)\nclass DecisionEvaluation:\n''',
)
replace_once(
    "src/bb_agent/evaluator.py",
    '''    near_tie_groups: tuple[tuple[str, ...], ...]\n    tie_breaks: tuple[TieBreakRecord, ...]\n    information_sensitive: bool\n\n\ndef _clip''',
    '''    near_tie_groups: tuple[tuple[str, ...], ...]\n    tie_breaks: tuple[TieBreakRecord, ...]\n    epistemic_scenarios: tuple[EpistemicRankingScenario, ...]\n    information_sensitive: bool\n\n\ndef _clip''',
)

regex_once(
    "src/bb_agent/evaluator.py",
    r'''def _multiply\(value: MetricRange, multiplier: float\) -> MetricRange:.*?\n\ndef _selection_value''',
    '''def _selection_bounds(value: MetricRange) -> tuple[float, float]:\n    assert value.selection_minimum is not None\n    assert value.selection_maximum is not None\n    return value.selection_minimum, value.selection_maximum\n\n\ndef _epistemic_bounds(value: MetricRange) -> tuple[float, float]:\n    assert value.epistemic_minimum is not None\n    assert value.epistemic_maximum is not None\n    return value.epistemic_minimum, value.epistemic_maximum\n\n\ndef _multiply(value: MetricRange, multiplier: float) -> MetricRange:\n    if multiplier < 0:\n        raise ValueError("metric multiplier must be nonnegative")\n    expected = None if value.expected is None else value.expected * multiplier\n    selection_minimum, selection_maximum = _selection_bounds(value)\n    epistemic_minimum, epistemic_maximum = _epistemic_bounds(value)\n    return MetricRange(\n        value.minimum * multiplier,\n        value.maximum * multiplier,\n        expected,\n        selection_minimum=selection_minimum * multiplier,\n        selection_maximum=selection_maximum * multiplier,\n        epistemic_minimum=epistemic_minimum * multiplier,\n        epistemic_maximum=epistemic_maximum * multiplier,\n    )\n\n\ndef _normalized(\n    value: MetricRange,\n    scale: float,\n    direction: float = 1.0,\n) -> MetricRange:\n    support = (\n        _clip(direction * value.minimum / scale),\n        _clip(direction * value.maximum / scale),\n    )\n    expected = (\n        None if value.expected is None else _clip(direction * value.expected / scale)\n    )\n    selection_minimum, selection_maximum = _selection_bounds(value)\n    selection = (\n        _clip(direction * selection_minimum / scale),\n        _clip(direction * selection_maximum / scale),\n    )\n    epistemic_minimum, epistemic_maximum = _epistemic_bounds(value)\n    epistemic = (\n        _clip(direction * epistemic_minimum / scale),\n        _clip(direction * epistemic_maximum / scale),\n    )\n    return MetricRange(\n        min(support),\n        max(support),\n        expected,\n        selection_minimum=min(selection),\n        selection_maximum=max(selection),\n        epistemic_minimum=min(epistemic),\n        epistemic_maximum=max(epistemic),\n    )\n\n\ndef _average(values: tuple[MetricRange, ...]) -> MetricRange:\n    if not values:\n        return MetricRange.exact(0)\n    count = len(values)\n    expected = None\n    if all(value.expected is not None for value in values):\n        expected = (\n            sum(value.expected for value in values if value.expected is not None)\n            / count\n        )\n    selection = tuple(_selection_bounds(value) for value in values)\n    epistemic = tuple(_epistemic_bounds(value) for value in values)\n    return MetricRange(\n        sum(value.minimum for value in values) / count,\n        sum(value.maximum for value in values) / count,\n        expected,\n        selection_minimum=sum(bounds[0] for bounds in selection) / count,\n        selection_maximum=sum(bounds[1] for bounds in selection) / count,\n        epistemic_minimum=sum(bounds[0] for bounds in epistemic) / count,\n        epistemic_maximum=sum(bounds[1] for bounds in epistemic) / count,\n    )\n\n\ndef _weighted(value: MetricRange, weight: float) -> MetricRange:\n    expected = None if value.expected is None else value.expected * weight\n    selection_minimum, selection_maximum = _selection_bounds(value)\n    epistemic_minimum, epistemic_maximum = _epistemic_bounds(value)\n    return MetricRange(\n        value.minimum * weight,\n        value.maximum * weight,\n        expected,\n        selection_minimum=selection_minimum * weight,\n        selection_maximum=selection_maximum * weight,\n        epistemic_minimum=epistemic_minimum * weight,\n        epistemic_maximum=epistemic_maximum * weight,\n    )\n\n\ndef _add(values: tuple[MetricRange, ...]) -> MetricRange:\n    if not values:\n        return MetricRange.exact(0)\n    expected = None\n    if all(value.expected is not None for value in values):\n        expected = sum(value.expected for value in values if value.expected is not None)\n    selection = tuple(_selection_bounds(value) for value in values)\n    epistemic = tuple(_epistemic_bounds(value) for value in values)\n    return MetricRange(\n        sum(value.minimum for value in values),\n        sum(value.maximum for value in values),\n        expected,\n        selection_minimum=sum(bounds[0] for bounds in selection),\n        selection_maximum=sum(bounds[1] for bounds in selection),\n        epistemic_minimum=sum(bounds[0] for bounds in epistemic),\n        epistemic_maximum=sum(bounds[1] for bounds in epistemic),\n    )\n\n\ndef _subtract(left: MetricRange, right: MetricRange) -> MetricRange:\n    expected = None\n    if left.expected is not None and right.expected is not None:\n        expected = left.expected - right.expected\n    left_selection = _selection_bounds(left)\n    right_selection = _selection_bounds(right)\n    left_epistemic = _epistemic_bounds(left)\n    right_epistemic = _epistemic_bounds(right)\n    return MetricRange(\n        left.minimum - right.maximum,\n        left.maximum - right.minimum,\n        expected,\n        selection_minimum=left_selection[0] - right_selection[1],\n        selection_maximum=left_selection[1] - right_selection[0],\n        epistemic_minimum=left_epistemic[0] - right_epistemic[1],\n        epistemic_maximum=left_epistemic[1] - right_epistemic[0],\n    )\n\n\ndef _shift(value: MetricRange, amount: float) -> MetricRange:\n    expected = None if value.expected is None else value.expected + amount\n    selection_minimum, selection_maximum = _selection_bounds(value)\n    epistemic_minimum, epistemic_maximum = _epistemic_bounds(value)\n    return MetricRange(\n        value.minimum + amount,\n        value.maximum + amount,\n        expected,\n        selection_minimum=selection_minimum + amount,\n        selection_maximum=selection_maximum + amount,\n        epistemic_minimum=epistemic_minimum + amount,\n        epistemic_maximum=epistemic_maximum + amount,\n    )\n\n\ndef _selection_value''',
)

replace_once(
    "src/bb_agent/evaluator.py",
    '''    return value.expected if value.expected is not None else value.minimum\n\n\ndef _penalty_selection''',
    '''    if value.expected is not None:\n        return value.expected\n    selection_minimum, _ = _selection_bounds(value)\n    return selection_minimum\n\n\ndef _penalty_selection''',
)
replace_once(
    "src/bb_agent/evaluator.py",
    '''    return value.expected if value.expected is not None else value.maximum\n''',
    '''    if value.expected is not None:\n        return value.expected\n    _, selection_maximum = _selection_bounds(value)\n    return selection_maximum\n''',
)
replace_once(
    "src/bb_agent/evaluator.py",
    '''    uncertainty_span = before_uncertainty.maximum - before_uncertainty.minimum\n''',
    '''    epistemic_minimum, epistemic_maximum = _epistemic_bounds(before_uncertainty)\n    uncertainty_span = epistemic_maximum - epistemic_minimum\n''',
)

regex_once(
    "src/bb_agent/evaluator.py",
    r'''\n\ndef _ranges_overlap\(.*?\n\ndef _tie_key\(''',
    '''\n\ndef _tie_key(''',
)
replace_once(
    "src/bb_agent/evaluator.py",
    '''    candidates = _with_dominance(candidates)\n    candidates = _with_information_sensitivity(\n        candidates,\n        profile.near_tie_margin,\n    )\n''',
    '''    candidates = _with_dominance(candidates)\n''',
)

# Replace the evaluator tail with coherent joint hidden-state scenario ranking.
evaluator_path = Path("src/bb_agent/evaluator.py")
evaluator_text = evaluator_path.read_text(encoding="utf-8")
marker = "\ndef evaluate_decision(\n"
if evaluator_text.count(marker) != 1:
    raise RuntimeError("could not locate evaluator decision entry point")
prefix = evaluator_text.split(marker, 1)[0]
new_tail = r'''

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
        tuple(sorted(domains[key], key=_assignment_sort_key))
        for key in sorted(domains)
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
) -> Result[DecisionEvaluation]:
    """Evaluate the complete canonical current affordance set fail-closed."""

    try:
        normalized = state.normalized()
    except (TypeError, ValueError) as exc:
        return Result.validation_failure(
            Problem(
                ErrorCode.VALIDATION_FAILED,
                str(exc),
                "state",
            )
        )

    coverage = authority.classify(normalized)
    if coverage.status is not ResultStatus.SUCCESS:
        return Result(
            coverage.status,
            problems=coverage.problems,
        )
    if not normalized.action_affordances.actions:
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
    for action in actions:
        feature_result = extract_candidate_features(
            authority,
            normalized,
            action.action_id,
        )
        if feature_result.value is None:
            return Result(
                feature_result.status,
                problems=feature_result.problems,
            )
        evaluations.append(
            score_candidate_features(
                feature_result.value,
                action.actor_id,
                profile,
                unit_value_policy,
            )
        )

        scenario_result = extract_candidate_feature_scenarios(
            authority,
            normalized,
            action.action_id,
        )
        if scenario_result.value is None:
            return Result(
                scenario_result.status,
                problems=scenario_result.problems,
            )
        scenario_features[action.action_id] = scenario_result.value
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
'''
evaluator_path.write_text(prefix + new_tail, encoding="utf-8")

# Public package export for the trace-ready ranking-scenario record.
replace_once(
    "src/bb_agent/__init__.py",
    '''    DecisionEvaluation,\n    DecisionSelection,\n''',
    '''    DecisionEvaluation,\n    DecisionSelection,\n    EpistemicRankingScenario,\n''',
)
replace_once(
    "src/bb_agent/__init__.py",
    '''    "DecisionSelection",\n    "EVALUATION_CONFIG_VERSION",\n''',
    '''    "DecisionSelection",\n    "EpistemicRankingScenario",\n    "EVALUATION_CONFIG_VERSION",\n''',
)

# Replace the old envelope-overlap test with direct aleatory and coherent-scenario regressions.
replace_once(
    "tests/test_evaluator.py",
    "from dataclasses import replace\n",
    "from dataclasses import fields, replace\n",
)
replace_once(
    "tests/test_evaluator.py",
    '''    EvaluationProfile,\n    UnitValuePolicy,\n''',
    '''    EvaluationProfile,\n    EvaluationWeights,\n    UnitValuePolicy,\n''',
)
replace_once(
    "tests/test_evaluator.py",
    '''from bb_agent.results import ResultStatus\nfrom test_mechanics import _attack, _authority, _snapshot, _wait\n''',
    '''from bb_agent.results import ResultStatus\nfrom bb_agent.tactical_state import (\n    HexCoord,\n    InformationProfile,\n    KnowledgeClass,\n    KnownValue,\n    Representation,\n    TacticalState,\n    Tile,\n)\nfrom test_mechanics import (\n    _attack,\n    _authority,\n    _move_action,\n    _movement_state,\n    _ordinary_attack_state,\n    _reaction,\n    _snapshot,\n    _wait,\n)\n''',
)

helper = r'''

def _scenario_flip_state(authority, *, omniscient_hp: int | None = None):
    state = _ordinary_attack_state(authority, hit_points=10)
    brother = next(actor for actor in state.combatants if actor.actor_id == "brother")
    enemy = next(actor for actor in state.combatants if actor.actor_id == "enemy")
    if omniscient_hp is None:
        enemy_hp = KnownValue(
            Representation.SET,
            KnowledgeClass.INFERRED,
            candidates=(5, 20),
            basis=("visible-wound-band",),
        )
        information_profile = InformationProfile.PLAYER_LEGAL
    else:
        enemy_hp = KnownValue.exact(
            omniscient_hp,
            KnowledgeClass.DEBUG_GROUND_TRUTH,
        )
        information_profile = InformationProfile.OMNISCIENT_DEBUG

    enemy_one = replace(
        enemy,
        resources=replace(enemy.resources, hit_points=enemy_hp),
    )
    enemy_two = replace(
        enemy,
        actor_id="enemy-2",
        position=KnownValue.exact("northeast"),
        resources=replace(
            enemy.resources,
            hit_points=KnownValue.exact(10),
        ),
    )

    attack_one = state.action_affordances.actions[0]
    preview = attack_one.preview
    if preview.affected_tile_ids is not None:
        preview = replace(
            preview,
            affected_tile_ids=replace(
                preview.affected_tile_ids,
                value=["northeast"],
            ),
        )
    attack_two = replace(
        attack_one,
        action_id="attack:enemy-2",
        target_actor_id="enemy-2",
        preview=preview,
    )

    origin = next(tile for tile in state.tiles if tile.tile_id == "origin")
    east = next(tile for tile in state.tiles if tile.tile_id == "east")
    origin = replace(
        origin,
        neighbors=("east", "northeast", None, None, None, None),
    )
    east = replace(
        east,
        neighbors=(None, None, "northeast", "origin", None, None),
    )
    northeast = Tile(
        "northeast",
        HexCoord(1, -1),
        0,
        KnownValue.exact("plain"),
        (None, None, None, None, "origin", "east"),
        "enemy-2",
    )

    values = {field.name: getattr(state, field.name) for field in fields(state)}
    values.update(
        state_id="",
        information_profile=information_profile,
        combatants=(brother, enemy_one, enemy_two),
        tiles=(origin, east, northeast),
        action_affordances=replace(
            state.action_affordances,
            actions=(attack_one, attack_two),
        ),
    )
    return TacticalState.create(**values)
'''
replace_once(
    "tests/test_evaluator.py",
    '''def test_complete_decision_evaluation_is_exactly_deterministic():\n''',
    helper + "\n\ndef test_complete_decision_evaluation_is_exactly_deterministic():\n",
)

regex_once(
    "tests/test_evaluator.py",
    r'''def test_uncertain_score_envelope_marks_information_sensitive_ranking\(\):.*?\n\ndef test_near_tie_uses_frozen_resource_then_action_id_tie_path''',
    r'''def test_omniscient_aleatory_aoo_spread_is_not_epistemic_uncertainty():
    authority = _authority()
    move = _move_action(reactions=(_reaction(),))
    state = _movement_state(authority, move)

    result = evaluate_decision(authority, state)

    assert result.status is ResultStatus.SUCCESS
    assert result.value is not None
    candidate = result.value.candidates[0]
    damage = candidate.features.friendly_harm.expected_self_hp_damage
    assert damage.maximum > damage.minimum
    assert damage.expected is not None
    assert candidate.uncertainty_span == pytest.approx(0)
    assert candidate.information_sensitive is False
    assert result.value.information_sensitive is False
    facts = {
        fact.component_id: fact.contribution for fact in candidate.explanation_facts
    }
    assert facts["uncertainty_robustness_adjustment"] == pytest.approx(0)


def test_player_legal_rank_flip_uses_coherent_hidden_state_scenarios():
    authority = _authority()
    weights = EvaluationWeights(
        enemy_effect=1,
        immediate_friendly_harm=0,
        post_action_exposure=0,
        position_control_protection=0,
        resource_future_capacity=0,
        tempo=0,
    )
    profile = EvaluationProfile(
        weights=weights,
        tail_risk_weight=0,
        uncertainty_weight=0,
        near_tie_margin=0.001,
    )
    player_legal = _scenario_flip_state(authority)

    result = evaluate_decision(authority, player_legal, profile)

    assert result.status is ResultStatus.SUCCESS
    assert result.value is not None
    assert result.value.information_sensitive is True
    assert len(result.value.epistemic_scenarios) == 2
    assert len(
        {scenario.chosen_action_id for scenario in result.value.epistemic_scenarios}
    ) == 2
    assert {
        assignment.value
        for scenario in result.value.epistemic_scenarios
        for assignment in scenario.assignments
        if assignment.actor_id == "enemy"
        and assignment.field == "resources.hit_points"
    } == {5, 20}

    for hp in (5, 20):
        omniscient = evaluate_decision(
            authority,
            _scenario_flip_state(authority, omniscient_hp=hp),
            profile,
        )
        assert omniscient.status is ResultStatus.SUCCESS
        assert omniscient.value is not None
        assert omniscient.value.information_sensitive is False
        assert omniscient.value.epistemic_scenarios == ()


def test_near_tie_uses_frozen_resource_then_action_id_tie_path''',
)

# Document the corrected semantics explicitly.
replace_once(
    "docs/EVALUATION.md",
    '''A `MetricRange` with a justified expectation uses that expectation for the\nselection value. A range without a justified expectation never receives a\nmidpoint. The evaluator instead uses the conservative lower bound for tactical\nbenefit and the conservative upper bound for a loss/penalty. The complete score\nenvelope remains recorded.\n\nThe uncertainty adjustment is derived from the width of the post-tail-risk score\nenvelope. Selection is marked information-sensitive when an uncertain\ncandidate's ranking envelope materially overlaps another candidate under the\nsame guardrail eligibility. `omniscient_debug` inputs that collapse the relevant\nfeature ranges therefore remove that epistemic sensitivity while combat RNG\nexpectations remain intact.\n''',
    '''`MetricRange` keeps three views separate. Raw `minimum`/`maximum` preserve\nthe complete represented support, including combat-RNG branches. The robust\nselection projection first integrates any justified aleatory probabilities and\nthen retains conservative bounds for non-probabilistic uncertainty. A separate\nepistemic projection tracks only hidden-information variation. Consequently an\nAOO can retain a wide raw damage support while contributing zero epistemic width\nwhen its hit/damage distribution is fully known. Bounded model proxies such as\ncurrent ZOC pressure may remain robust ranges without being mislabeled as hidden\ninformation.\n\nA range without a justified expectation never receives a midpoint. Tactical\nbenefits use the conservative robust-selection lower bound and losses use the\ncorresponding upper bound. The uncertainty/robustness adjustment is charged only\nfrom the post-tail **epistemic** projection width, so ordinary combat RNG cannot\nlose a tie on the `lower_epistemic_uncertainty` criterion.\n\nInformation sensitivity is not inferred from overlapping aggregate envelopes.\nWhere the outcome model exposes coherent unweighted `EpistemicScenario` hidden\nstates, #21 converts each scenario to tactical features after integrating its RNG\nbranches, forms compatible joint hidden states across candidates, and records the\nactual deterministic ranking in each state. A recommendation is information-\nsensitive only when those plausible hidden states materially change the selected\naction under the normal near-tie/tie policy. `omniscient_debug` has no such\nhidden-state scenario set while retaining the same aleatory combat model.\n''',
)

print("issue #21 uncertainty semantics patch applied")
