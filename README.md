# BB-Agent

Battle Brothers tactical/strategic agent project.

## Current phase: specification only

BB-Agent is intentionally **not in development yet**. The repository is being used first to define and challenge the product, architecture, game-state contracts, decision model, validation strategy, and integration boundaries.

Production implementation is deferred to Codex after the first specification gate is explicitly closed.

## Working principles

- **Spec before code.** Research and architecture questions become GitHub issues and are resolved before implementation tickets are opened.
- **Tactical slice first.** The first milestone should prove that the agent can understand a Battle Brothers combat state and make reproducible, defensible tactical recommendations before attempting autonomous execution or whole-campaign play.
- **No-cheat decision boundary.** The decision engine should not gain an advantage from hidden information unavailable to a legitimate player. Exact rules and exceptions must be specified before development.
- **Reproducible decisions.** A recommendation should be explainable and replayable from a captured canonical state.
- **Separate from BB-Save-Toolkit.** Reuse should happen through explicit contracts or stable shared components, not by casually coupling the repositories.
- **Codex implements after freeze.** This repository's initial issues are specification/research work. Implementation backlog comes only after the M1 spec-freeze gate.

## Initial target

The initial target is a tactical agent architecture that can progress through offline fixtures, advisor/shadow operation, supervised execution, and eventually autonomous combat without forcing those later stages into the first implementation milestone.

See the repository issues for the active specification program.