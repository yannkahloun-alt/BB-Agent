# Shared Agent Workflow Dependency

BB-Agent uses `yannkahloun-alt/codex-agent-workflow` as its reusable behavioral
workflow through the `.agent-workflow` Git submodule.

## Policy split

The shared workflow defines **how Codex works**: issue handoff, role selection,
worktree/branch discipline, validation, independent review, handoff, and normal
pull-request lifecycle.

BB-Agent's root `AGENTS.md` defines **what this project must preserve**: the
frozen M1 specification, information-profile separation, affordance boundary,
mechanics coverage policy, deterministic replay requirements, and escalation
conditions.

Project policy overrides shared defaults when the two conflict, as defined by
the shared workflow's instruction precedence.

## Approved version policy

- Current approved pin: `v1.1.2`
- Commit: `4171010e1a17643876036b3dfd463b2e3a615c5f`
- Allowed routine selector: greatest non-prerelease SemVer tag in `v1.x`
- Moving to a new major workflow series requires explicit project-policy review.

Workflow upgrades should be isolated lifecycle changes. Do not mix a workflow
pin change into an unrelated BB-Agent implementation ticket.

## Fresh clone / worktree

Initialize the dependency with:

```powershell
git submodule update --init --recursive
```

The project must remain understandable from its own `AGENTS.md` and frozen
GitHub specification issues; the shared workflow must not become a hidden source
of product or tactical semantics.
