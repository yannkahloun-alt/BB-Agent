# AGENTS.md — BB-Agent

First apply the shared workflow pinned at `.agent-workflow/AGENTS.md`. If the
directory is absent in a fresh clone or worktree, initialize it with:

```powershell
git submodule update --init --recursive
```

This file specializes that workflow for BB-Agent. Explicit user instructions
still take precedence.

## Shared workflow dependency

- Workflow submodule path: `.agent-workflow`
- Workflow upstream: `yannkahloun-alt/codex-agent-workflow`
- Current pin: `v1.1.1` (`ecdf075c7baf35414c131db54f9409e5c82b3a6e`)
- Approved stable selector: greatest non-prerelease SemVer tag in the `v1.x`
  series

Dedicated workflow-bump work may advance the pin within `v1.x` after review. A
new major workflow series requires an explicit project-policy decision.

## Mission

Build a reproducible, explainable Battle Brothers tactical agent that progresses
from a validated offline decision kernel toward later shadow/advisor and
execution modes without smuggling later autonomy into M1.

## Frozen M1 authority

The M1 specification is frozen by GitHub issue #12. Issues #1–#13 are the
product/specification record; #13 supersedes conflicting earlier wording about
current-command legality, movement affordances, player-visible previews, and
mechanics coverage.

Implementation tickets #14–#26 are governed by that frozen specification. Issue
#27 is the M1 closure gate.

If implementation evidence contradicts or materially expands a frozen contract,
**stop and reopen/escalate the relevant specification issue**. Do not invent a
new architecture in code merely to complete the implementation ticket.

## M1 non-negotiable invariants

1. **Current actions come from affordances.** M1 consumes a complete current
   `ActionAffordanceSet` supplied by fixtures (and later by a game adapter). It
   does not independently clone arbitrary Battle Brothers current-command
   legality, targetability, item-use, or pathfinding rules.
2. **Decision information profiles stay explicit.** `player_legal` and
   `omniscient_debug` are separate semantic views. They may share raw capture
   identity, but debug ground truth must never silently enter a player-legal
   decision.
3. **Debug omniscience is a diagnostic tool, not production state.** Paired
   legal/debug runs are encouraged for diagnosis; traces must always identify
   the active information profile.
4. **Unknown is not exact.** Hidden or uncertain values use the frozen knowledge
   representation. Never substitute debug truth, magic sentinels, or convenient
   midpoint values without an explicitly specified uncertainty policy.
5. **Unsupported mechanics fail visibly.** A materially competing unsupported
   action/mechanic must produce structured `INCOMPLETE_COVERAGE` /
   `EVALUATION_UNSUPPORTED` behavior, never a guessed neutral/generic score.
6. **Resolved preview values are applied once.** Player-visible preview facts
   such as resolved AP/FAT cost or displayed hit chance may be legitimate
   inputs; do not reconstruct hidden inputs merely to reapply the same modifier.
7. **Decisions are deterministic and replayable.** Identical canonical state,
   information profile, rules/content fingerprint, model/config versions, and
   deterministic simulation settings must reproduce ranking and trace identity.
8. **Risk stays inspectable.** Expected tactical value, friendly harm,
   post-action exposure, fatigue/future capacity, tail risk, and epistemic
   uncertainty must not collapse into opaque post-hoc reasoning.
9. **No network/LLM dependency in the tactical decision loop.** M1 must operate
   locally and deterministically from versioned inputs.
10. **No BB-Save-Toolkit tactical runtime dependency.** Strategic/toolkit data
    may become an explicit later input, but per-candidate tactical evaluation
    must not shell out to or import toolkit analysis as a hidden dependency.
11. **M1 remains offline.** No live game adapter, in-game execution, mouse/
    keyboard automation, shadow-mode UX, autonomous combat loop, or campaign
    agent belongs in M1 unless the specification is explicitly reopened.
12. **Tests must not redefine semantics.** Fix the implementation or reopen the
    specification; do not change frozen behavior solely to make a test pass.

## Required context before implementation

Before editing for an M1 issue:

1. read the assigned GitHub issue completely;
2. read issue #12 (M1 freeze gate) and issue #13 (action-affordance/mechanics
   boundary);
3. read every frozen spec issue named by the assigned ticket;
4. read `README.md` and `docs/AGENT_WORKFLOW_DEPENDENCY.md`;
5. inspect existing implementation and tests before choosing a design.

Keep one coherent task per branch/worktree. Add focused regression tests for
behavioral fixes, run the repository's documented gates, review the complete
diff, and keep commits scoped to the issue.

## Implementation sequencing

Respect explicit ticket dependencies. In particular, do not let later scorer or
calibration work compensate for missing contract validation, mechanics coverage,
transition correctness, or raw tactical features.

Calibration may change versioned generic configuration or justified generic
feature transforms; it may not introduce per-fixture bonuses, entity/map hacks,
hidden debug truth, or silent mechanics expansion.

## Completion / escalation

A normal `work on ticket #N` handoff follows the shared workflow through the
repository-defined lifecycle. However, encountering a frozen-spec contradiction
is a project-level escalation condition: document the evidence on the relevant
issue and stop that implementation path rather than improvising around it.
