# Testing and CI Policy

BB-Agent's M1 quality gates are part of the frozen implementation policy. CI proves that an implementation satisfies the repository's deterministic engineering checks; it does **not** override a failed frozen-spec, safety, or coverage gate.

## Runtime baseline

M1 targets **Python 3.12** as the initial supported CI/runtime baseline.

Do not add a Python-version matrix during M1 unless a separate compatibility decision explicitly expands support. Keeping one interpreter baseline reduces unrelated variability while the tactical contracts and mechanics are still being implemented.

## Fresh checkout prerequisite

Every local/CI validation path must initialize the shared behavioral workflow dependency:

```powershell
git submodule update --init --recursive
```

A missing, stale, or broken `.agent-workflow` pin is a validation failure, not a condition to work around by ignoring project policy.

## Routine task iteration

During implementation:

- run focused tests for the changed behavior and adjacent contracts;
- add explicit regression tests for bug fixes and semantic corrections;
- run the applicable static-analysis checks before declaring the task ready for review;
- inspect structured warnings/coverage failures rather than relying on exit code alone.

Tests and decision fixtures used by the M1 kernel must be deterministic, machine-independent, network-free, and independent of a locally installed Battle Brothers game or private save files.

## Stable PR checks

Pull requests targeting `main` must eventually expose these stable required GitHub Actions checks:

- `tests`
- `ruff`
- `pyflakes`

Issue #14 owns the first executable CI implementation of this policy. Check names are part of the branch-protection contract and should remain stable once introduced unless deliberately migrated.

### `tests`

The normal deterministic test suite for the current implementation stage. As M1 grows, this check must include all promoted fast/normal gates relevant to the touched contracts, including fixture/replay validation when those systems exist.

### `ruff`

Ruff formatting/lint/static checks as configured by the repository. New warnings/errors are not acceptable.

### `pyflakes`

Independent lightweight Python static analysis. New warnings/errors are not acceptable.

The exact commands/configuration are established by #14 and repository files; this policy defines the required outcomes and stable check identities.

## Local commands equivalent to CI

Use Python 3.12 from a clean checkout. Initialize and verify the shared workflow,
then install the project and pinned development tools:

```powershell
git submodule update --init --recursive
python tools/verify_workflow_dependency.py
python -m pip install -e ".[dev]"
```

Run the three stable checks with exactly these commands:

```powershell
python -m pytest
python -m ruff format --check .
python -m ruff check .
python -m pyflakes src tests tools
```

The two Ruff commands together constitute the `ruff` check. None of these checks
requires network access after the development dependencies have been installed.

## Merge policy

A PR is merge-ready only when:

1. all required deterministic CI checks are green;
2. repository-required independent review from the shared workflow is complete;
3. the implementation satisfies the assigned issue acceptance criteria;
4. no unresolved frozen-spec contradiction or safety/coverage failure remains;
5. the complete diff has been reviewed for unrelated changes.

**CI is authoritative for deterministic merge readiness, but CI success never overrides a failed frozen-spec, safety-critical fixture, or mechanics-coverage gate.**

Normal implementation should reach `main` through the repository's workflow-controlled PR lifecycle. Avoid casual direct implementation commits to `main`.

## Branch protection target

Once #14 establishes the first successful CI workflow, `main` should be configured to require the stable checks:

```text
tests
ruff
pyflakes
```

The repository may run on a free/single-account model where independent Agent B review is operational rather than a GitHub status check. That review remains mandatory under the shared workflow even when GitHub cannot enforce it as branch protection.

## Coverage policy

M1 starts with **no repository-wide coverage percentage gate**.

Reason: there is no meaningful implementation baseline yet, and choosing an arbitrary percentage would reward quantity rather than tactical-contract coverage.

Coverage expectations are instead semantic:

- new correctness branches need explicit assertions;
- mechanics/risk/knowledge-profile behavior needs focused regression fixtures;
- safety-critical and replay contracts cannot be considered covered by incidental line execution.

A numeric branch/line coverage baseline may be introduced later only after representative M1 code and tests exist. That change must document the measured baseline and intended enforcement.

## Mutation testing

Mutation testing is **not** part of routine PR CI for M1.

It may be introduced later for targeted correctness-critical modules once the mechanics/evaluator code and test corpus are mature enough for the signal to be useful. Do not add expensive mutation work merely to imitate BB-Save-Toolkit's mature release process.

## External dependencies prohibited from CI decision tests

Normal M1 CI must not require:

- network access during the tactical decision/test path;
- Battle Brothers installed locally;
- private save files;
- live game processes;
- UI/OCR capture;
- BB-Save-Toolkit as a synchronous tactical runtime dependency;
- LLM/API calls for tactical ranking or explanations.

Static, pinned, repository-owned/reference-derived test data is allowed when its provenance and version/fingerprint are explicit.

## M1 gate growth by implementation stage

The `tests` check must grow with the implementation rather than leaving important gates manual.

### Contract stage — #14–#17

Promote deterministic tests for:

- project/version/error skeleton;
- canonical state validation and hashing;
- `player_legal` / `omniscient_debug` separation;
- ActionAffordance freshness/completeness semantics;
- fixture loading/replay input normalization;
- mechanics-manifest coverage classification.

### Mechanics/features stage — #18–#20

Promote deterministic tests for:

- ordinary attack distributions and supported formulas;
- movement/AP/FAT transitions;
- AOO/disengagement branches;
- position/threat/formation/future-capacity feature extraction;
- explicit unsupported-mechanics behavior.

### Evaluator/replay stage — #21–#23

Promote deterministic tests for:

- risk-sensitive ranking and tie behavior;
- uncertainty/information-sensitivity handling;
- decision-trace reconciliation;
- exact replay/output fingerprints;
- generic validation-harness semantics.

### Corpus/calibration stage — #24–#26

The complete promoted **gated** fixture corpus becomes part of required validation. Calibration-only fixtures may report disagreement without failing CI when #10/#23 metadata explicitly classifies them that way.

Safety/core failures must never be hidden behind aggregate accuracy.

## Final M1 closure — #27

Issue #27 may declare `M1 CLOSED` only after the required CI checks pass and the frozen M1 closure requirements are met, including:

- >= 40 gated fixtures;
- >= 10 `SAFETY_CRITICAL` fixtures;
- >= 8 uncertainty/no-cheat cases;
- all promoted gated assertions passing;
- no supported ranking fixture ending in `INCOMPLETE_COVERAGE`;
- deterministic repeated replay/output fingerprints;
- no debug-ground-truth leakage into `player_legal`;
- unsupported mechanics failing visibly rather than being guessed;
- documented latency benchmark with provenance.

A green PR is necessary but not sufficient for this final product gate.

## Flaky-test policy

M1 decision tests are expected to be deterministic. Do not use blind retry-to-green as the normal response to a failing test.

When a test flakes:

1. determine whether nondeterminism comes from ordering, seeds/sampling, timestamps, environment, concurrency, or the test itself;
2. fix or explicitly quarantine the cause with a tracked issue and evidence;
3. do not normalize unexplained flakes into accepted CI behavior.

## Definition of done for an implementation ticket

Unless the ticket explicitly defines a stronger gate, it is done when:

1. assigned behavior is implemented within frozen scope;
2. focused tests/regression fixtures exist and pass;
3. the normal required test/static-analysis gates pass;
4. deterministic/replay/coverage diagnostics applicable to the touched subsystem are clean;
5. documentation is updated where commands/contracts changed;
6. independent review and the normal shared-workflow PR lifecycle complete successfully.

If satisfying any gate requires contradicting or materially expanding #1–#13, stop and escalate to the relevant specification issue rather than weakening CI or hardcoding around the conflict.
