# M1 tactical evaluation

Issue #21 implements the frozen #5/#6 risk-sensitive evaluator over the raw
features produced by #20. The evaluator is deliberately a policy layer over
canonical current-action affordances; it does not discover commands, simulate a
full enemy response, call an LLM, or import BB-Save-Toolkit.

## Versioned policy

The implementation model remains `risk-evaluator.v1`. Ticket #26 freezes the
final M1 profile as `m1-evaluation-profile.v2`, with fingerprint
`2e0ff58c4c57a80dc37eb86da5d49ef573057abd73eb158801f5c600c0c6ffcb`.
Every profile has a deterministic SHA-256 fingerprint covering all scales,
family weights, risk policy, uncertainty penalty, near-tie margin, and optional
guardrail. These values are calibration parameters constrained by the gated
corpus, not universal Battle Brothers truths. The detailed v1-to-v2 audit and
rationale are recorded in [`CALIBRATION.md`](CALIBRATION.md).

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

The calibrated v2 resource family scores remaining AP, fatigue headroom,
AP/FAT-feasible current cost templates, ammo consumption, and charge
consumption. `ap_fat_locked_template_count` remains an inspectable raw diagnostic
but is not also scored: for the current template set it is the complement of the
feasible-template count, so scoring both would double-count the same future-
capacity loss.

## Unknowns and robustness

`MetricRange` keeps three views separate. Raw `minimum`/`maximum` preserve
the complete represented support, including combat-RNG branches. The robust
selection projection first integrates any justified aleatory probabilities and
then retains conservative bounds for non-probabilistic uncertainty. A separate
epistemic projection tracks only hidden-information variation. Consequently an
AOO can retain a wide raw damage support while contributing zero epistemic width
when its hit/damage distribution is fully known. Bounded model proxies such as
current ZOC pressure may remain robust ranges without being mislabeled as hidden
information.

A range without a justified expectation never receives a midpoint. Tactical
benefits use the conservative robust-selection lower bound and losses use the
corresponding upper bound. The uncertainty/robustness adjustment is charged only
from the post-tail **epistemic** projection width, so ordinary combat RNG cannot
lose a tie on the `lower_epistemic_uncertainty` criterion.

Information sensitivity is not inferred from overlapping aggregate envelopes.
Where the outcome model exposes coherent unweighted `EpistemicScenario` hidden
states, #21 converts each scenario to tactical features after integrating its RNG
branches, forms compatible joint hidden states across candidates, and records the
actual deterministic ranking in each state. A recommendation is information-
sensitive only when those plausible hidden states materially change the selected
action under the normal near-tie/tie policy. `omniscient_debug` has no such
hidden-state scenario set while retaining the same aleatory combat model.

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
