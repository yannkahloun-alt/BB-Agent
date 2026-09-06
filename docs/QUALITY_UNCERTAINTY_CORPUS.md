# M1 Tactical Quality, Uncertainty, and No-Cheat Corpus

Ticket #25 completes the promoted gated M1 validation corpus defined by frozen specs #2, #5, #6, #10, and #13.

## Corpus shape

The durable #25 corpus lives in `tests/fixtures/ticket_25/` as canonical `FixtureEnvelope` JSON. It contains **21 promoted gated fixtures**. Combined with ticket #24's 33 fixtures, the M1 corpus now contains **54 gated fixtures**, including the existing **10 SAFETY_CRITICAL** fixtures.

The #25 corpus is deliberately weighted toward epistemic and tactical-quality behavior rather than duplicating #24 mechanics/safety cases. At least eight #25 fixtures carry the `uncertainty_no_cheat` taxonomy, satisfying the frozen uncertainty/no-cheat quantity gate across the total corpus.

## Tactical-quality coverage

The quality fixtures exercise the supported M1 feature families without inventing unsupported search or future legality:

- zero-damage repositioning that creates a direct screen for a vulnerable ally;
- high-ground positional gain and elevation-contact advantage;
- surround/flank control as independent tactical value;
- movement into an open tile that improves future reposition flexibility;
- fatigue-heavy action versus a more sustainable current option;
- Recover versus acting as an explicit fatigue-headroom versus residual-AP tradeoff;
- beneficial Wait versus premature End Turn;
- acting now when waiting is materially worse;
- equal-target near-tie handling with deterministic resolution;
- supported threat-priority ordering using only mechanics already present in the M1 manifest.

The corpus does not force a golden top action when only a component relationship is defensible. In particular, Recover/resource tradeoffs are gated on inspectable resource/future-capacity relationships rather than pretending one action is universally correct. This follows #10's expert-disagreement policy.

## Player-legal versus omniscient-debug pairs

The corpus contains paired `player_legal` and `omniscient_debug` fixtures derived from the same raw-capture identity.

The pairs prove three different outcomes are legitimate:

1. **Stable under uncertainty** — the player-legal state carries legal hidden HP/armor beliefs, the trace shows nonzero epistemic uncertainty, but all coherent hidden-state scenarios retain the same recommendation.
2. **Information-sensitive flip** — a player-legal hidden-HP set produces different scenario winners and the decision is explicitly marked information-sensitive. Omniscient low-HP and high-HP twins remove the epistemic uncertainty and choose different exact-state winners.
3. **Preview without hidden defense** — a player-visible displayed hit chance remains valid production input while exact enemy defense is not supplied as debug truth to the player-legal state.

The permanent corpus test recursively verifies that the player-legal pair states contain no `DEBUG_GROUND_TRUTH` `KnownValue` and that paired legal/debug fixtures retain the same raw capture identity.

## Aleatory RNG versus epistemic uncertainty

`t25-no-cheat-aleatory-only-debug` uses a fully exact omniscient movement state with a supplied AOO reaction. Its immediate self-damage distribution has real hit/miss/damage spread, but the candidate's epistemic `uncertainty_span` remains exactly zero and the decision is not information-sensitive.

This protects the frozen #6 distinction:

- combat RNG is aleatory uncertainty and remains even in `omniscient_debug`;
- hidden/incomplete state is epistemic uncertainty and disappears when exact legitimate debug state is supplied.

The fixture does not use Battle Brothers' hidden future RNG state. The current M1 AOO/ordinary-attack models remain exact branch enumeration, so no simulator seed is needed for these cases.

## Uncertain position and failure health

The belief-bearing position fixture keeps a hostile location as an inferred finite set and requires a threat range rather than midpoint substitution. This prevents unknown position from silently becoming one fabricated exact tile.

The player-legal coverage-health fixture intentionally includes unsupported material mechanics and requires `INCOMPLETE_COVERAGE`, visible legal candidates, structured coverage diagnostics, and no tactical ranking. No debug truth is permitted to rescue the unsupported decision.

## UnitValuePolicy pair

The two `t25-unit-value-*` fixtures contain an **identical canonical TacticalState**. The tactical state does not contain strategic/campaign value.

The permanent test evaluates one copy with the default common-preservation policy and the other with an explicitly supplied 4x strategic value for the vulnerable brother. It requires:

- identical canonical state identity;
- different `UnitValuePolicy` fingerprints in trace engine context;
- `tail_risk.unit_value` changing from 1 to 4;
- a strictly larger tail-risk selection penalty under the high-value policy.

This proves strategic unit value changes friendly-loss/tail-risk valuation through evaluation context only and does not introduce BB-Save-Toolkit into the synchronous tactical runtime.

## Combined M1 taxonomy gate

The permanent #25 test runs the generic #23 harness across both ticket #24 and ticket #25 directories and requires all twelve frozen #10 families to be represented:

- `core_legality_affordability`
- `movement_path_zoc`
- `los_ranged_aoe`
- `obvious_offense_kill_secure`
- `survival_catastrophic_risk`
- `protection_formation`
- `elevation_positioning`
- `fatigue_resource_economy`
- `tempo_wait_end_turn`
- `control_disable_threat_priority`
- `uncertainty_no_cheat`
- `trace_failure_coverage`

All 54 fixtures are promoted and gated; there are no calibration fixtures in this initial corpus. Any future genuinely ambiguous expectation should be broadened, expressed as a relation, or demoted to calibration rather than allowing a random gated failure.

## Scope boundary

Ticket #25 remains an offline M1 corpus task. It adds no live capture, adapter transport, keyboard/mouse execution, autonomous turns, deep hypothetical search, online Bayesian learner, network/LLM dependency, campaign logic, or BB-Save-Toolkit tactical runtime dependency.

The complete current `ActionAffordanceSet` remains authoritative for executable current commands under #13. The fixtures exercise evaluator behavior over supplied current actions and beliefs; they do not reconstruct hypothetical Battle Brothers legality.