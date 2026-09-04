# Shared Agent Workflow Dependency

BB-Agent uses `yannkahloun-alt/codex-agent-workflow` as its reusable behavioral
workflow through the `.agent-workflow` Git submodule.

## Policy split

The shared workflow defines **how Codex works**: issue handoff, role selection,
worktree/branch discipline, CI-owned routine validation, independent review,
handoff, and normal pull-request lifecycle.

BB-Agent's root `AGENTS.md` defines **what this project must preserve**: the
frozen M1 specification, information-profile separation, affordance boundary,
mechanics coverage policy, deterministic replay requirements, and escalation
conditions.

Project policy overrides shared defaults when the two conflict, as defined by
the shared workflow's instruction precedence.

## Approved version policy

- Current approved pin: `v1.1.3`
- Commit: `ff0647d3dc205a47734d569ae5247ee4ba9109e9`
- Allowed routine selector: greatest non-prerelease SemVer tag in `v1.x`
- Moving to a new major workflow series requires explicit project-policy review.

Workflow upgrades should be isolated lifecycle changes. Do not mix a workflow
pin change into an unrelated BB-Agent implementation ticket.

## Ticket lifecycle specialization

The shared workflow owns the generic lifecycle. For one named BB-Agent ticket,
normal operation uses one ticket branch/worktree and one implementation PR.
All later implementation commits, CI fixes, review fixes, and exact-head review
generations continue on that same PR. A workflow-freshness bump remains a
separate maintenance prerequisite and is not the ticket's implementation PR.

If the ticket PR cannot safely continue because of a concrete host or
repository limitation, record and report that limitation; do not silently
create a replacement implementation PR.

Independent review is subagent-first and fail-closed. When trustworthy fresh
subagent isolation is available, use a fresh read-only subagent in the existing
ticket workspace. A separate review task, thread, or worktree is a fallback
only after a concrete host/tool limitation has been established and recorded,
or when stronger explicit project policy requires it. BB-Agent retains its
project-specific frozen-spec, safety, and mechanics-coverage review criteria.

## Fresh clone / worktree

Initialize the dependency with:

```powershell
git submodule update --init --recursive
```

The project must remain understandable from its own `AGENTS.md` and frozen
GitHub specification issues; the shared workflow must not become a hidden source
of product or tactical semantics.
