# M1 evaluator calibration

Ticket #26 calibrates the frozen M1 risk-sensitive evaluator against the complete promoted #24/#25 tactical corpus. The result is a deliberately small generic change rather than a retuning exercise.

## Final profile

The final M1 evaluation configuration is:

- profile version: `m1-evaluation-profile.v2`;
- profile fingerprint: `2e0ff58c4c57a80dc37eb86da5d49ef573057abd73eb158801f5c600c0c6ffcb`;
- evaluator model: `risk-evaluator.v1`;
- default UnitValuePolicy: `m1-common-preservation.v1`;
- default UnitValuePolicy fingerprint: `170f540b3f76cb01ca88048dcb13cb66f57f96b2ea464c6a122292309179c2b7`.

The numeric family weights, normalization scales, tail-risk coefficient, uncertainty coefficient, near-tie margin and guardrail policy are unchanged from v1. The corpus supplied no defensible evidence that those numbers needed retuning, and changing them merely because calibration was scheduled would risk overfitting.

## Generic calibration change: future-capacity de-duplication

The v1 `resource_fat_future_capacity` family scored both:

- `ap_fat_feasible_template_count` positively; and
- `ap_fat_locked_template_count` negatively.

For the current-cost template set these are complementary views of the same AP/FAT feasibility partition. Scoring both therefore counted the same loss of current future-action capacity twice inside one component.

Profile v2 keeps both raw values in `TacticalFeatures` and in traces, but only the feasible-template count participates in the normalized resource score. The locked-template count remains diagnostic evidence and can still be asserted directly by fixtures. This is a generic transform independent of fixture ID, actor identity, map geometry or content name.

The resource family now averages five scored terms:

1. remaining AP;
2. fatigue headroom;
3. AP/FAT-feasible current cost templates;
4. ammo consumed;
5. charges consumed.

No per-fixture bonus, blacklist, map/entity exception, mechanics expansion or hidden-information shortcut is introduced.

## Full-corpus calibration audit

Before implementing the v2 transform, a self-cleaning audit compared the existing v1 scorer with the proposed de-duplicated resource family over all **54 promoted gated fixtures** from tickets #24 and #25.

Baseline v1 identity:

- profile version: `m1-evaluation-profile.v1`;
- fingerprint: `8d4ccf45414aa2728168327c1e007ea456a2841212e46619fc458df7a45c9f34`.

Audit result:

- gated failures after de-duplication: **0**;
- ranking changes: **0**;
- score-only changes: **50 fixtures**;
- safety-critical fixture count: **10**, unchanged;
- no safety expectation was weakened or reclassified.

Because the transform changes the numerical score projection even though this corpus's ranking stays unchanged, it is explicitly versioned as evaluation profile v2 and therefore changes profile/trace identity as required.

## Component overlap review

Calibration reviewed the material overlap called out by #26.

### Damage, armor and kill value

`enemy_effect` retains HP damage, armor damage and kill probability as separate raw terms within one averaged family. They are correlated but not equivalent: armor removal can matter without immediate HP loss, and kill probability captures threat removal rather than another copy of raw HP damage. They share one family weight rather than receiving independent top-level weights. No corpus evidence justified changing their current scales.

### Expected harm and catastrophic risk

Expected self/ally HP harm remains in `immediate_friendly_harm`; self-death probability remains in the separate `tail_risk_penalty`. This overlap is intentional under frozen #5: mean loss and catastrophic-tail risk must both remain inspectable. The tail penalty does not independently charge expected HP damage.

Movement interruption remains visible in the immediate-harm component and in the `TailRiskRecord` for diagnostics, but the tail selection penalty itself is derived from self-death probability only. It is therefore not charged a second time by the tail penalty.

### Position and exposure

`post_action_exposure` measures hostile pressure/LOS against the resulting state. `position_control_ally_protection` measures distinct positive/negative positional consequences such as elevation contacts, screening, flank control and open reposition options. Calibration retained both because one represents incoming threat exposure while the other represents control/protection/flexibility; the gated corpus exercises cases where either can change independently.

### Fatigue and future capacity

The only unexplained material duplication found was the feasible/locked-template complement. That duplication is removed in v2. Remaining AP, fatigue headroom and feasible-template count are related but not identical: they expose raw resources and the consequence of those resources for currently represented action-cost templates. The current scales were retained because all gated resource relationships pass without scenario-specific tuning.

## Near ties and deterministic selection

The final near-tie margin remains `0.05`.

The full-corpus audit found exactly one near-tie fixture: `t25-quality-near-tie-equal-targets`, the deliberately symmetric expert-choice case. The smallest nonzero top-score gap among the other audited ranking fixtures was approximately `0.0621693`, so the margin does not accidentally absorb the nearest distinct top ordering in the current corpus.

The frozen tie sequence remains:

1. lower tail risk;
2. lower epistemic uncertainty;
3. lower irreversible resource cost;
4. stable `action_id`.

Permanent calibration tests pin that the symmetric fixture remains the only near-tie case and that the tie criteria remain unchanged.

## UnitValuePolicy

Calibration leaves the default UnitValuePolicy unchanged. The #25 identical-state policy pair already demonstrates that an externally supplied high strategic value changes friendly-loss/tail-risk valuation without mutating `TacticalState` or adding BB-Save-Toolkit to the tactical runtime. #26 pins the default policy version/fingerprint separately from the calibrated evaluation profile.

## Determinism

Permanent #26 validation runs the complete 54-fixture corpus twice with the final profile and requires identical per-fixture semantic output fingerprints, statuses, chosen actions and rankings. Coverage/safety assertions must pass on both runs.

## Performance diagnostic

The pre-change calibration audit ran on GitHub-hosted Ubuntu 24.04 / Python 3.12.14, x86_64, local repository files only, with the workflow dependency pinned at `ff0647d3dc205a47734d569ae5247ee4ba9109e9`.

Observed v1 full-corpus decision timings from the generic validation harness were:

- median: about **37.5 ms**;
- p95: about **67.2 ms**;
- maximum: about **93.1 ms**.

The de-duplicated candidate experiment measured about **37.2 ms median / 74.8 ms p95 / 90.8 ms maximum** in the same hosted run. These are diagnostic numbers, not the frozen #10 named local/reference-machine acceptance result: shared hosted hardware is explicitly not a stable performance gate. They show no evidence of a calibration-induced performance regression and remain far below the engineering targets in this diagnostic environment.

Ticket #27 owns the final documented reference-machine latency gate with full provenance before declaring M1 closed.

## Calibration verdict

The corpus does not justify broad weight or scale tuning. The final calibration therefore removes one generic future-capacity double-count, versions the change, preserves every promoted gate and ranking, retains the frozen risk/no-cheat architecture, and records the final reproducible profile identity without scenario-specific exceptions.