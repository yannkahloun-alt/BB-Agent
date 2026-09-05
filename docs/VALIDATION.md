# M1 validation harness and fixture expectations

Issue #23 implements the generic validation/regression harness required by the frozen #7/#10 contract and the #13 affordance amendment. It deliberately does **not** add the final 40+ fixture corpus; #24/#25 can author fixture content against this schema without adding scenario-specific Python to the runner.

## Versions

- expectation payload: `m1-fixture-expectations.v1`
- harness: `m1-validation-harness.v1`

Expectations remain envelope/authoring data. They do not enter `TacticalState.state_id`, decision scoring, or `DecisionTrace.output_fingerprint`.

A `PROMOTED` fixture must carry an expectation payload whose version matches `FixtureMetadata.expectation_version`. Draft/reviewed fixtures may temporarily omit expectations; the harness reports that as review work rather than inventing a tactical gate.

## Generic expectation payload

The `FixtureEnvelope.expectations` object may contain any compatible subset of:

```json
{
  "version": "m1-fixture-expectations.v1",
  "expected_status": "SUCCESS",
  "acceptable_top1": ["action:A", "action:B"],
  "forbidden_top1": ["action:catastrophic"],
  "required_orderings": [["action:A", "action:C"]],
  "top_k": [{"any_of": ["action:B", "action:C"], "k": 3}],
  "near_ties": [{"action_ids": ["action:A", "action:B"], "expected": true}],
  "numeric_relations": [
    {
      "left": {"action_id": "action:A", "path": "evaluation.tail_risk.selection_penalty"},
      "op": "<",
      "right": {"action_id": "action:B", "path": "evaluation.tail_risk.selection_penalty"}
    }
  ],
  "information_sensitive": false,
  "required_explanations": [
    {"action_id": "$chosen", "component_ids": ["enemy_effect", "tail_risk_penalty"]}
  ],
  "required_legal_action_ids": ["action:A"],
  "forbidden_legal_action_ids": ["action:impossible"],
  "exact_legal_action_ids": ["action:A", "action:B"],
  "action_facts": [
    {"action_id": "action:A", "path": "ap_cost.value", "equals": 4}
  ],
  "expected_problem_codes": ["EVALUATION_UNSUPPORTED"],
  "expected_mechanic_ids": ["mod.unknown_aoe"],
  "expected_output_fingerprint": null,
  "assert_oracle_affordance_set": false,
  "allow_model_version_change": false
}
```

Unknown schema fields are rejected. Ranking assertions cannot be combined with a declared non-success decision status.

### Action references

Most fields use stable canonical action IDs. The harness also accepts the trace-relative tokens:

- `$chosen` / `$top1`
- `$runner_up`

These tokens are resolved only against the generated trace and never become decision inputs.

### Numeric component/risk relations

A numeric relation references a candidate record plus a dotted path. Normal mapping traversal is supported. Lists of component records may be addressed by their `component_id`, for example:

```text
evaluation.components.enemy_effect.selection_value
evaluation.tail_risk.selection_penalty
evaluation.uncertainty_span
evaluation.features.friendly_harm.expected_self_hp_damage.expected
```

Supported operators are `<`, `<=`, `==`, `!=`, `>=`, and `>`. Equality uses an explicit finite tolerance (default `1e-9`). This keeps the harness generic instead of adding one Python branch per tactical scenario.

## Hard gates versus calibration review

The harness separates correctness from tactical calibration.

Always-hard checks include:

- fixture/state normalization and state identity;
- exact equality between the complete canonical `ActionAffordanceSet` and trace legal candidates;
- exact replay of output fingerprint, ranking, and chosen action;
- explicit legal-set/action-fact assertions;
- expected structured coverage/problem/mechanic identifiers;
- oracle affordance-set equality when requested;
- an explicitly pinned output fingerprint.

For `CORE`, `QUALITY`, and `SAFETY_CRITICAL` fixtures, tactical expectation failures (`acceptable_top1`, forbidden top1, ordering, top-K, near ties, component/risk relations, information sensitivity, explanation IDs) are gated failures.

For `CALIBRATION` fixtures, the same tactical mismatches are emitted as `REVIEW` findings and do not by themselves fail M1 acceptance. Structural/replay/legality corruption still fails even on a calibration fixture.

An `INCOMPLETE_COVERAGE` fixture can explicitly assert that status and its mechanic/error diagnostics. Any fixture carrying ranking assertions implicitly requires a successful complete-coverage ranking; the harness therefore fails closed rather than scoring around unsupported legal affordances.

## Oracle/capture boundary

Per #13, the harness does not reconstruct Battle Brothers current-command legality. The fixture's complete `ActionAffordanceSet` is authoritative input.

When captured fixture authoring provides game-oracle completeness metadata, `assert_oracle_affordance_set` expects envelope-only annotations shaped as:

```json
{
  "affordance_set_complete": true,
  "legal_action_ids": ["action:A", "action:B"]
}
```

The harness compares those IDs with the canonical/trace affordance set. Oracle annotations remain outside decision input hashing and player-legal state.

## Corpus report

`run_validation_corpus()` returns every per-fixture report plus deterministic coverage summaries needed by the M1 gate:

- total, gated, calibration, and safety-critical fixture counts;
- taxonomy counts;
- severity counts;
- information-profile counts;
- review-status counts;
- blocking assertion failures and review findings;
- diagnostic median/p95/max decision time derived from trace stage timings.

The timing summary is diagnostic on ordinary CI hardware. #10/#13 keep the 3-second release ceiling tied to a documented local/reference machine rather than shared hosted CI.

The corpus report passes only when there are zero blocking failures. There is intentionally no aggregate tactical-accuracy percentage that can hide a failed promoted safety/core assertion.

Exact replay preserves the original JSON numeric representation of versioned evaluator/profile and UnitValuePolicy fields (for example `1` remains `1`, rather than being rewritten to `1.0`). This keeps configuration identity byte-stable while leaving numeric scoring semantics unchanged.

## Regression classification

`classify_trace_change()` combines #22 `TraceDiff` with fixture expectations and reports one of:

- `NO_CHANGE`
- `HARD_GATED_FAILURE`
- `ACCEPTABLE_SET_SUBSTITUTION`
- `INTENDED_MODEL_VERSION_CHANGE`
- `CALIBRATION_REVIEW_REQUIRED`
- `REVIEW_REQUIRED_CHANGE`

A version/config change is called intended only when the fixture explicitly sets `allow_model_version_change`. A recommendation swapping between two members of the fixture's `acceptable_top1` set is distinguished from a true gated failure. Trace/component deltas remain attached to the classification so #24–#26 reviews can explain why output changed.
