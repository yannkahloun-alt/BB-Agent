# M1 decision trace and replay

Issue #22 implements the frozen #6/#7 trace/replay contract around the offline
current-decision evaluator. The trace is a machine-readable diagnostic and replay
artifact. Human advisor text remains a later derived view and is never needed to
reproduce a decision.

## Trace schema

The implementation schema is `bb-agent-decision-trace.v1`. A `DecisionTrace`
contains:

- `input`: fixture identity when available, canonical `state_id`, shared
  `raw_capture_id`, information profile, ruleset identity, and the complete
  normalized canonical tactical state;
- `engine`: frozen contract identifiers, evaluator/config identity, the complete
  versioned `EvaluationProfile`, the complete `UnitValuePolicy`, mechanics
  manifest identity, outcome-model versions, and deterministic simulator facts;
- `generation`: the complete current legal `ActionAffordanceSet` represented as
  canonical action objects, decision/coverage status, and structured coverage
  diagnostics;
- `evaluations`: one record per evaluated candidate containing its canonical
  action, resolved deterministic costs, outcome method/counts, raw tactical
  features, normalized/weighted components, risk records, uncertainty records,
  final ranking value, dominance/guardrail findings, and explanation facts;
- `selection`: chosen action, total ranking, near ties, tie-break records,
  dominance/guardrail findings, runner-up deltas, and coherent epistemic ranking
  scenarios;
- `failure`: structured failing stage/status/problems when no recommendation can
  be produced;
- `performance`: measured stage timings and deterministic health/candidate
  counters;
- `output_fingerprint`: SHA-256 over the deterministic semantic output.

The trace embeds canonical state rather than requiring an external game/UI
session. A `FixtureEnvelope` or `ReplayInput` may still supply a stable fixture
ID for diagnostics.

## Deterministic identity

`output_fingerprint` covers the ranking-relevant input identity, engine/config
identity, complete candidate generation/evaluation records, selection, and
structured failure semantics. `trace_id` is content-derived from the trace
version, canonical state identity, and output fingerprint.

The following are deliberately excluded from deterministic output identity:

- wall-clock timestamps;
- measured stage durations;
- host/CPU/OS metadata;
- other runtime telemetry that cannot affect the recommendation.

This means two evaluations may report different nanosecond timings while still
having exactly the same `output_fingerprint` and `trace_id`.

## Outcome and simulator facts

`TacticalFeatures` includes an `OutcomeModelFacts` record so trace generation does
not re-run the outcome model just to discover diagnostics. Current M1 models use
exact analytic/discrete processing:

- ordinary attacks and stochastic AOO transitions report
  `exact_branch_enumeration` plus their branch count;
- one-branch transitions report `deterministic_transition`;
- `sample_count` is zero and no simulator seed is present until a future
  explicitly supported deterministic sampling model is introduced.

Aleatory branch counts remain diagnostic facts and do not become epistemic
uncertainty.

## Performance diagnostics

`evaluate_decision()` accepts optional diagnostic sinks. Normal callers are
unchanged. When `run_decision_trace()` supplies those sinks, the evaluator emits
elapsed time for:

- state validation;
- mechanics coverage;
- outcome/feature extraction;
- scoring;
- selection.

It also reports candidate, coverage, branch/sample and epistemic-scenario
counters. These observations do not enter `DecisionEvaluation`, scoring, tie
handling, or the deterministic output fingerprint.

The frozen #10/#13 latency targets remain reference-machine benchmark policy;
shared GitHub CI is a correctness gate, not a stable performance runner.

## Failure traces

`run_decision_trace()` preserves structured `VALIDATION_FAILURE` and
`INCOMPLETE_COVERAGE` results rather than reducing them to an exception string.
When the evaluator raises an unexpected exception, the wrapper records an
`EVALUATION_EXCEPTION` failure stage without reclassifying it as mechanics
coverage. Canonical serialization rejects NaN/Inf; if semantic trace output
cannot be serialized, the trace falls back to an `INVALID_NUMERIC_OUTPUT`
failure artifact where practical.

Unsupported materially competing affordances therefore still prevent a ranking
while leaving enough state/config/diagnostic context to investigate the failure.

## Exact replay

`replay_decision_trace()` reconstructs the embedded `TacticalState`,
`EvaluationProfile`, and `UnitValuePolicy`, then runs the normal evaluator again.
It checks:

- output fingerprint equality;
- full ranking equality;
- chosen-action equality.

Replay uses BB-Agent model/config identity. It never attempts to reproduce Battle
Brothers' hidden future RNG stream.

## Regression comparison

`compare_traces()` provides structured deltas for:

- added/removed candidate action IDs;
- rank-position changes;
- chosen-action changes;
- component contribution changes, including tail-risk and uncertainty
  adjustments;
- output-fingerprint changes.

This is diagnostic comparison across intentional model/config generations. A
changed fingerprint is not automatically a tactical regression; the promoted
fixture expectations implemented by #23–#25 decide whether the semantic change
is acceptable.

<!-- trusted-head round-trip -->
