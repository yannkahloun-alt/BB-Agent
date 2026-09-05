# M1 tactical evaluation

Issue #21 implements the frozen #5/#6 risk-sensitive evaluator over the raw
features produced by #20. The evaluator is deliberately a policy layer over
canonical current-action affordances; it does not discover commands, simulate a
full enemy response, call an LLM, or import BB-Save-Toolkit.

## Versioned policy

The implementation model is `risk-evaluator.v1` and the initial profile is
`m1-evaluation-profile.v1`. Every profile has a deterministic SHA-256 fingerprint
covering all scales, family weights, risk policy, uncertainty penalty, near-tie
margin, and optional guardrail. These values are initial calibration parameters,
not universal Battle Brothers truths. Ticket #26 may tune them only through a
new versioned generic profile or justified generic transforms.

The default component families remain separate:

- `enemy_effect`;
- `immediate_friendly_harm`;
- `post_action_exposure`;
- `position_control_ally_protection`;
- `resource_fat_future_capacity`;
- `tempo_turn_order`;
- `tail_risk_penalty`;
- `uncertainty_robustness_adjustment`.

Raw HP, armor, probability, threat, formation, resource, mobility, and tempo
quantities remain in `TacticalFeatures`. Each mean-value family records its
normalized range, profile weight, weighted range, and the exact value used for
selection. Tail risk and epistemic uncertainty are not folded invisibly into a
mean component.

## Unknowns and robustness

A `MetricRange` with a justified expectation uses that expectation for the
selection value. A range without a justified expectation never receives a
midpoint. The evaluator instead uses the conservative lower bound for tactical
benefit and the conservative upper bound for a loss/penalty. The complete score
envelope remains recorded.

The uncertainty adjustment is derived from the width of the post-tail-risk score
envelope. Selection is marked information-sensitive when an uncertain
candidate's ranking envelope materially overlaps another candidate under the
same guardrail eligibility. `omniscient_debug` inputs that collapse the relevant
feature ranges therefore remove that epistemic sensitivity while combat RNG
expectations remain intact.

## Friendly unit value

`UnitValuePolicy` is explicit evaluation context. The default
`m1-common-preservation.v1` policy assigns the same positive preservation value
to every player-controlled life. An optional strategic provider can supply
actor-specific positive multipliers. The policy has its own deterministic
fingerprint and changes friendly-harm/tail-loss valuation without mutating
`TacticalState` or adding a toolkit runtime dependency.

## Tail risk and guardrails

M1 tail risk currently uses the supported immediate self-death probability from
the candidate feature record. The death-tail penalty is distinct from expected
self/ally HP harm. Movement interruption remains separately inspectable in the
tail record and immediate-harm family.

There is no default absolute death-risk veto. A profile may explicitly declare
`max_self_death_probability`; only then does the candidate receive the
`MAX_SELF_DEATH_PROBABILITY` guardrail finding and rank behind non-excluded
candidates. This keeps hard handling limited to declared policy rather than
inventing a universal "never take risk" rule.

## Dominance, near ties, and deterministic selection

Strict dominance is diagnostic and conservative. Candidate A is marked as
dominated only when another candidate is provably no worse across the complete
tactical-value range and no worse across the tail-risk range, with at least one
strict improvement. Dominated candidates remain in the full ranking and are not
silently pruned.

Candidates within the versioned near-tie margin are resolved with the frozen tie
sequence:

1. lower tail risk;
2. lower epistemic uncertainty;
3. lower irreversible ammo/charge consumption;
4. stable `action_id`.

Every nontrivial tie group records the candidate IDs, winner, and applied
criteria. Optional guardrail eligibility is applied before these score groups.

## Explanation reconciliation

Every candidate exposes structured `ExplanationFact` records built directly from
the component selection values plus the explicit tail-risk and uncertainty
adjustments. Their numeric sum must equal the final ranking value; construction
fails if they do not reconcile. Human-facing prose in later advisor work must be
derived from these facts rather than inventing post-hoc reasons.

## Complete-affordance failure boundary

`evaluate_decision()` first validates and classifies the complete canonical
`ActionAffordanceSet`. Any structurally or concretely unsupported materially
competing action returns `INCOMPLETE_COVERAGE` with no recommendation. Supported
candidates are never used to score around an unsupported legal command.

The returned `DecisionEvaluation` records the normalized state/profile identity,
evaluator/profile/UnitValuePolicy identities and fingerprints, mechanics-manifest
fingerprint, all candidate evaluations, total deterministic ranking, chosen
action, near-tie groups, tie-break paths, dominance/guardrail findings, and
information-sensitivity status. Ticket #22 builds the replay-complete
`DecisionTrace` and deterministic output fingerprint around this record.

<!-- temporary ci retrigger -->
