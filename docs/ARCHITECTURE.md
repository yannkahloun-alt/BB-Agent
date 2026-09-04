# M1 Architecture Boundaries

M1 is the offline current-decision kernel frozen by GitHub issues #1–#13. Issue
#12 is the freeze gate, and issue #13 supersedes earlier current-command legality,
movement-affordance, preview, and mechanics-coverage wording. Root `AGENTS.md` and
`docs/TESTING.md` are mandatory implementation and validation policy.

## Module ownership

- `bb_agent.versions` is the single authoritative location for frozen contract
  identifiers and future ranking-affecting mechanics/model/config versions.
- `bb_agent.serialization` owns only deterministic JSON bytes and content hashing.
  Later contract tickets own semantic normalization, including ordering of
  semantically unordered collections and exclusion of debug annotations.
- `bb_agent.results` provides the shared non-exception result boundary for
  validation failures and honest `INCOMPLETE_COVERAGE` outcomes.
- Later M1 modules will own canonical state and affordances (#15), fixtures and
  replay inputs (#16), mechanics coverage/catalog data (#17), outcome models
  (#18–#19), tactical features (#20), evaluation (#21), traces (#22), and the
  validation corpus (#23–#26).

## Dependency direction

The decision path may depend on canonical inputs, a local versioned rules/content
catalog, deterministic outcome/feature/evaluation code, and explicit configuration.
It must not depend on network or LLM calls, Battle Brothers runtime/UI objects,
live capture or execution, private saves, or BB-Save-Toolkit runtime analysis.

Current executable commands will come from the complete supplied
`ActionAffordanceSet`; M1 will not invent commands or clone arbitrary game
legality. Player-visible resolved previews and debug ground truth remain distinct.
Unsupported materially competing mechanics must yield structured
`EVALUATION_UNSUPPORTED` and decision-level `INCOMPLETE_COVERAGE`, never a guessed
score.

Live adapters, UI, supervised/autonomous execution, hypothetical-state search,
and campaign behavior are post-M1 concerns and have no package boundary here.
