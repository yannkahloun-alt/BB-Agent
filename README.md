# BB-Agent

Battle Brothers tactical/strategic agent project.

## Current phase: M1 implementation

The first BB-Agent milestone has completed its specification and adversarial-review phase. **M1 is frozen and implementation is delegated to Codex through the repository's dependency-ordered implementation issues.**

M1 is deliberately an **offline tactical decision kernel**, not a live bot. Given a canonical current tactical state plus a complete current `ActionAffordanceSet`, it will evaluate supported commands deterministically and risk-sensitively, then emit an inspectable, replayable recommendation.

The specification freeze is recorded in issue **#12**. The adversarial review is **#11**, and the action-affordance / player-visible preview / mechanics-coverage correction is **#13**.

## Working principles

- **Spec before code.** M1 contracts were defined and challenged before implementation tickets were opened. Any implementation discovery that contradicts a frozen contract goes back to specification rather than being patched around in code.
- **Tactical slice first.** M1 proves current-decision quality from deterministic offline fixtures before live capture, execution, autonomous combat, or campaign play.
- **Explicit information profiles.** Normal decisions use `player_legal`; `omniscient_debug` is available for diagnostics. Legitimate player-visible action previews are allowed without exposing the hidden runtime inputs used to compute them.
- **Current action affordances, not cloned legality.** M1 consumes the complete commands currently executable from the fixture/future game adapter. Independent hypothetical-state legality belongs to later search/planning work.
- **Manifest-driven mechanics coverage.** Unsupported materially competing commands produce `INCOMPLETE_COVERAGE`; they are never silently dropped or approximated with fake generic semantics.
- **Reproducible decisions.** Recommendations must expose real score/risk/uncertainty components and replay deterministically from captured inputs.
- **Separate from BB-Save-Toolkit.** BB-Save-Toolkit may later provide explicit strategic enrichment, but it is not a synchronous dependency of the tactical decision loop.
- **Codex implements M1.** Issues **#14–#26** form the implementation/validation backlog; **#27** is the M1 closure gate.

## Agent workflow and validation policy

BB-Agent consumes the shared `yannkahloun-alt/codex-agent-workflow` repository through the pinned `.agent-workflow` Git submodule. Root `AGENTS.md` specializes that workflow with BB-Agent's frozen product and engineering invariants.

Fresh clones/worktrees should initialize the dependency with:

```powershell
git submodule update --init --recursive
```

The project-specific quality and CI contract is in [`docs/TESTING.md`](docs/TESTING.md). Initial M1 CI targets Python 3.12 and stable PR checks named `tests`, `ruff`, and `pyflakes`; issue #14 owns their first executable implementation. Green CI is necessary for merge readiness but never overrides a failed frozen-spec, safety-critical, or mechanics-coverage gate.

See [`docs/AGENT_WORKFLOW_DEPENDENCY.md`](docs/AGENT_WORKFLOW_DEPENDENCY.md) for the behavioral dependency and upgrade policy.

The versioned offline fixture envelope and replay-input boundary are documented
in [`docs/FIXTURES.md`](docs/FIXTURES.md).

## M1 implementation sequence

1. Project/test/version skeleton — #14
2. Canonical tactical state + ActionAffordance contracts — #15
3. Fixture/replay input envelope — #16
4. Mechanics coverage manifest + rules/content substrate — #17
5. Ordinary single-target attack outcome model — #18
6. MOVE_TO / AOO / simple action transitions — #19
7. Position/threat/formation/future-capacity features — #20
8. Risk-sensitive evaluator and deterministic selection — #21
9. Decision trace/replay/performance diagnostics — #22
10. Validation harness — #23
11. Core mechanics/safety fixture corpus — #24
12. Tactical-quality/uncertainty/no-cheat corpus — #25
13. Evaluator calibration — #26
14. M1 closure gate — #27

## Beyond M1

Live Battle Brothers state/action-affordance capture, shadow/advisor operation, supervised execution, autonomous tactical combat, and campaign strategy remain post-M1 work. They require a new specification/research phase after #27 closes rather than being added opportunistically to the M1 implementation.
