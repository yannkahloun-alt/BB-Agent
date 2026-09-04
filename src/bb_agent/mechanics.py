"""Offline mechanics authority, fail-closed coverage, and resolution ownership.

Coverage declarations are contracts, not outcome implementations. The shipped
manifest deliberately enables no model until its implementation ticket lands.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from importlib.resources import files
from pathlib import Path

from bb_agent.results import ErrorCode, Problem, Result, ResultStatus
from bb_agent.serialization import canonical_sha256
from bb_agent.tactical_state import (
    ActionAffordance,
    ActionKind,
    Representation,
    ResolutionAuthority,
    ResolutionStage,
    ResolvedCost,
    ResolvedPreviewValue,
    RulesetIdentity,
    TacticalState,
    TargetKind,
)
from bb_agent.versions import CURRENT_VERSIONS

CATALOG_VERSION = "bb-agent-catalog.v1"
MANDATORY_FAMILIES = frozenset(
    {
        "ordinary_attack",
        "move",
        "aoo",
        "wait",
        "end_turn",
        "equip",
        "recover",
        "reload",
        "special",
    }
)


class CoverageStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    EVALUATION_UNSUPPORTED = "EVALUATION_UNSUPPORTED"


@dataclass(frozen=True, slots=True)
class Provenance:
    repository: str
    revision: str
    paths: tuple[str, ...]
    derivation_version: str


@dataclass(frozen=True, slots=True)
class ContentEntry:
    content_id: str
    family_id: str
    category: str
    # Scalar static facts only: no mutable nested dictionaries in the catalog.
    facts: tuple[tuple[str, str | int | float | bool], ...]


@dataclass(frozen=True, slots=True)
class RulesCatalog:
    schema_version: str
    game_version: str
    mods: tuple[str, ...]
    provenance: Provenance
    entries: tuple[ContentEntry, ...]
    content_fingerprint: str

    @property
    def ruleset(self) -> RulesetIdentity:
        return RulesetIdentity(self.game_version, self.content_fingerprint, self.mods)

    def entry(self, content_id: str) -> ContentEntry | None:
        return next(
            (entry for entry in self.entries if entry.content_id == content_id), None
        )


@dataclass(frozen=True, slots=True)
class FamilyDeclaration:
    family_id: str
    status: CoverageStatus
    action_kinds: tuple[ActionKind, ...]
    content_ids: tuple[str, ...]
    outcome_effects: tuple[str, ...]
    model_version: str | None
    reason: str | None
    requires: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MechanicsManifest:
    version: str
    content_fingerprint: str
    families: tuple[FamilyDeclaration, ...]
    fingerprint: str

    def family(self, family_id: str) -> FamilyDeclaration:
        return next(family for family in self.families if family.family_id == family_id)


@dataclass(frozen=True, slots=True)
class AffordanceCoverage:
    action_id: str
    status: CoverageStatus
    family_ids: tuple[str, ...]
    model_versions: tuple[tuple[str, str], ...]
    problems: tuple[Problem, ...]


@dataclass(frozen=True, slots=True)
class CoverageReport:
    state_id: str
    information_profile: str
    content_fingerprint: str
    manifest_fingerprint: str
    affordances: tuple[AffordanceCoverage, ...]


def _object(value: object, keys: set[str]) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"expected object with fields {sorted(keys)}")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("expected nonempty string")
    return value


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError("expected string array")
    values = tuple(_text(item) for item in value)
    if len(set(values)) != len(values):
        raise ValueError("duplicate string array entry")
    return tuple(sorted(values))


def _read(path: Path) -> dict:
    def unique(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON field: {key}")
            result[key] = value
        return result

    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    canonical_sha256(value)  # Also rejects NaN/infinity, even in unknown fields.
    return value


def load_catalog(path: Path) -> Result[RulesCatalog]:
    """Load and verify a pinned local catalog; never fetch or refresh references."""
    try:
        data = _object(
            _read(path),
            {
                "schema_version",
                "game_version",
                "mods",
                "provenance",
                "entries",
                "content_fingerprint",
            },
        )
        if data["schema_version"] != CATALOG_VERSION:
            raise ValueError("unsupported catalog schema")
        provenance = _object(
            data["provenance"],
            {"repository", "revision", "paths", "derivation_version"},
        )
        revision = _text(provenance["revision"])
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError("provenance revision must be a full lowercase commit SHA")
        paths = _strings(provenance["paths"])
        if not paths:
            raise ValueError("provenance requires source paths")
        source = Provenance(
            _text(provenance["repository"]),
            revision,
            paths,
            _text(provenance["derivation_version"]),
        )
        if not isinstance(data["entries"], list):
            raise ValueError("entries must be an array")
        entries = []
        for raw in data["entries"]:
            raw = _object(raw, {"content_id", "family_id", "category", "facts"})
            if not isinstance(raw["facts"], dict):
                raise ValueError("facts must be an object of scalars")
            facts = []
            for key, value in raw["facts"].items():
                if type(value) not in (str, int, float, bool):
                    raise ValueError("catalog facts must be scalar")
                facts.append((_text(key), value))
            category = _text(raw["category"])
            if category not in {"skill", "item", "rule"}:
                raise ValueError("unknown content category")
            fact_map = dict(facts)
            if fact_map.get("source_path") not in paths or not re.fullmatch(
                r"[0-9a-f]{40}", str(fact_map.get("source_blob", ""))
            ):
                raise ValueError("content entry requires pinned source path and blob")
            entries.append(
                ContentEntry(
                    _text(raw["content_id"]),
                    _text(raw["family_id"]),
                    category,
                    tuple(sorted(facts)),
                )
            )
        entries.sort(key=lambda entry: entry.content_id)
        if len({entry.content_id for entry in entries}) != len(entries):
            raise ValueError("duplicate content ID")
        # Catalog identity includes provenance, static values and ordered mod set.
        # Array ordering is part of the versioned artifact; no hidden normalization.
        fingerprint = canonical_sha256(
            {key: value for key, value in data.items() if key != "content_fingerprint"}
        )
        if data["content_fingerprint"] != fingerprint:
            raise ValueError("catalog content fingerprint mismatch")
        mods = data["mods"]
        _strings(mods)
        return Result.success(
            RulesCatalog(
                CATALOG_VERSION,
                _text(data["game_version"]),
                tuple(mods),
                source,
                tuple(entries),
                fingerprint,
            )
        )
    except (OSError, ValueError, TypeError) as exc:
        return Result.validation_failure(
            Problem(ErrorCode.CATALOG_INVALID, str(exc), "catalog")
        )


def load_manifest(path: Path, catalog: RulesCatalog) -> Result[MechanicsManifest]:
    """Validate exact content mapping and dependency closure before classification."""
    try:
        data = _object(_read(path), {"version", "content_fingerprint", "families"})
        if data["version"] != CURRENT_VERSIONS.mechanics_manifest:
            raise ValueError("unsupported mechanics manifest version")
        if data["content_fingerprint"] != catalog.content_fingerprint:
            raise ValueError("manifest/catalog fingerprint mismatch")
        if not isinstance(data["families"], list):
            raise ValueError("families must be an array")
        families = []
        mapped = set()
        for raw in data["families"]:
            raw = _object(
                raw,
                {
                    "family_id",
                    "status",
                    "action_kinds",
                    "content_ids",
                    "outcome_effects",
                    "model_version",
                    "reason",
                    "requires",
                },
            )
            family_id = _text(raw["family_id"])
            status = CoverageStatus(raw["status"])
            model_version, reason = raw["model_version"], raw["reason"]
            if status is CoverageStatus.SUPPORTED:
                _text(model_version)
                if reason is not None:
                    raise ValueError("supported family cannot carry unsupported reason")
            else:
                _text(reason)
                if model_version is not None:
                    raise ValueError("unsupported family cannot claim a model version")
            ids = _strings(raw["content_ids"])
            for content_id in ids:
                entry = catalog.entry(content_id)
                if (
                    entry is None
                    or entry.family_id != family_id
                    or content_id in mapped
                ):
                    raise ValueError(f"invalid/duplicate content mapping: {content_id}")
                mapped.add(content_id)
            families.append(
                FamilyDeclaration(
                    family_id,
                    status,
                    tuple(ActionKind(kind) for kind in _strings(raw["action_kinds"])),
                    ids,
                    _strings(raw["outcome_effects"]),
                    model_version,
                    reason,
                    _strings(raw["requires"]),
                )
            )
        families.sort(key=lambda family: family.family_id)
        by_id = {family.family_id: family for family in families}
        if len(by_id) != len(families) or not MANDATORY_FAMILIES <= by_id.keys():
            raise ValueError("missing mandatory or duplicate family declaration")
        if mapped != {entry.content_id for entry in catalog.entries}:
            raise ValueError("every catalog entry requires an explicit family mapping")
        if "aoo" not in by_id["move"].requires:
            raise ValueError(
                "movement coverage must require AOO/disengagement coverage"
            )

        def visit(family_id: str, ancestors: frozenset[str]) -> None:
            if family_id not in by_id or family_id in ancestors:
                raise ValueError("unknown or cyclic family dependency")
            for dependency in by_id[family_id].requires:
                visit(dependency, ancestors | {family_id})

        for family_id in by_id:
            visit(family_id, frozenset())
        return Result.success(
            MechanicsManifest(
                data["version"],
                catalog.content_fingerprint,
                tuple(families),
                canonical_sha256(data),
            )
        )
    except (OSError, ValueError, TypeError) as exc:
        return Result.validation_failure(
            Problem(ErrorCode.MANIFEST_INVALID, str(exc), "manifest")
        )


def load_builtin_mechanics() -> Result[MechanicsAuthority]:
    """Load package-owned artifacts once at startup, outside tactical evaluation."""
    root = files("bb_agent").joinpath("data")
    catalog = load_catalog(Path(str(root.joinpath("catalog.v1.json"))))
    if catalog.value is None:
        return Result.validation_failure(*catalog.problems)
    manifest = load_manifest(
        Path(str(root.joinpath("manifest.v1.json"))), catalog.value
    )
    if manifest.value is None:
        return Result.validation_failure(*manifest.problems)
    return Result.success(MechanicsAuthority(catalog.value, manifest.value))


@dataclass(frozen=True, slots=True)
class MechanicsAuthority:
    catalog: RulesCatalog
    manifest: MechanicsManifest

    def __post_init__(self) -> None:
        if self.catalog.content_fingerprint != self.manifest.content_fingerprint:
            raise ValueError("manifest/catalog fingerprint mismatch")

    def classify(self, state: TacticalState) -> Result[CoverageReport]:
        """Classify the entire validated set. SUCCESS means coverage, never ranking."""
        try:
            state = state.normalized()
        except (ValueError, TypeError) as exc:
            return Result.validation_failure(
                Problem(ErrorCode.VALIDATION_FAILED, str(exc), "state")
            )
        if state.ruleset != self.catalog.ruleset:
            return Result.validation_failure(
                Problem(
                    ErrorCode.CATALOG_MISMATCH,
                    "state/catalog ruleset mismatch",
                    "ruleset",
                )
            )
        results = tuple(
            self._classify_action(state, action)
            for action in sorted(
                state.action_affordances.actions, key=lambda action: action.action_id
            )
        )
        report = CoverageReport(
            state.state_id,
            state.information_profile.value,
            self.catalog.content_fingerprint,
            self.manifest.fingerprint,
            results,
        )
        problems = tuple(problem for result in results for problem in result.problems)
        if problems:
            return Result(ResultStatus.INCOMPLETE_COVERAGE, report, problems)
        return Result.success(report)

    def _classify_action(
        self, state: TacticalState, action: ActionAffordance
    ) -> AffordanceCoverage:
        problems = []
        family_ids = set()
        models = {}

        def unsupported(reason: str, mechanic_id: str) -> None:
            problems.append(
                Problem(
                    ErrorCode.EVALUATION_UNSUPPORTED,
                    reason,
                    f"action_affordances.{action.action_id}",
                    mechanic_id,
                )
            )

        family_id = {
            ActionKind.MOVE_TO: "move",
            ActionKind.WAIT: "wait",
            ActionKind.END_TURN: "end_turn",
            ActionKind.EQUIP_ITEM: "equip",
        }.get(action.kind)
        content_id = action.skill_id
        if action.kind is ActionKind.EQUIP_ITEM:
            actor = next(
                actor for actor in state.combatants if actor.actor_id == action.actor_id
            )
            item = next(
                (item for item in actor.equipment if item.item_id == action.item_id),
                None,
            )
            if (
                item is None
                or item.content.representation is not Representation.EXACT
                or not isinstance(item.content.value, str)
            ):
                unsupported("item content is unresolved", action.item_id or "equip")
            else:
                content_id = item.content.value
        if content_id:
            entry = self.catalog.entry(content_id)
            expected_category = (
                "item" if action.kind is ActionKind.EQUIP_ITEM else "skill"
            )
            if entry is None or entry.category != expected_category:
                unsupported("unmapped content ID", content_id)
            else:
                family_id = entry.family_id
        if family_id is None:
            unsupported("no declared mechanic family", content_id or action.kind.value)
        else:
            family = self.manifest.family(family_id)
            expected_target = {
                "ordinary_attack": TargetKind.ACTOR,
                "recover": TargetKind.SELF,
                "reload": TargetKind.SELF,
            }.get(family_id)
            if (
                expected_target is not None
                and action.target_kind is not expected_target
            ):
                unsupported("target shape outside declared family", family_id)
            if action.kind not in family.action_kinds:
                unsupported("action kind is not declared by family", family_id)

            def require(name: str) -> None:
                if name in family_ids:
                    return
                family_ids.add(name)
                declaration = self.manifest.family(name)
                if declaration.status is CoverageStatus.EVALUATION_UNSUPPORTED:
                    unsupported(declaration.reason or "unsupported family", name)
                else:
                    models[name] = declaration.model_version
                for dependency in declaration.requires:
                    require(dependency)

            require(family_id)
        if action.kind is ActionKind.EQUIP_ITEM:
            entry = self.catalog.entry(content_id) if content_id else None
            if entry is not None and action.target_slot != dict(entry.facts).get(
                "slot"
            ):
                unsupported("target slot outside declared item class", content_id)
            if action.displaced_item_id is not None:
                unsupported(
                    "displaced item transition not declared", action.displaced_item_id
                )
        if action.parameters or action.mode_variant is not None or action.preview.facts:
            unsupported(
                "unmodelled extension, variant, or preview fact",
                content_id or action.kind.value,
            )
        status = (
            CoverageStatus.EVALUATION_UNSUPPORTED
            if problems
            else CoverageStatus.SUPPORTED
        )
        return AffordanceCoverage(
            action.action_id,
            status,
            tuple(sorted(family_ids)),
            tuple(sorted(models.items())),
            tuple(problems),
        )


class RulesStage(StrEnum):
    CURRENT_COST = "CURRENT_COST"
    CURRENT_HIT_CHANCE = "CURRENT_HIT_CHANCE"
    CURRENT_DAMAGE_PROFILE = "CURRENT_DAMAGE_PROFILE"
    TARGET_MITIGATION = "TARGET_MITIGATION"
    OUTCOME = "OUTCOME"


@dataclass(frozen=True, slots=True)
class ResolutionLedger:
    """Immutable per-value stage ledger; subsequent formulas retain input authority."""

    authority: str
    completed: tuple[RulesStage, ...]

    @classmethod
    def from_resolved(
        cls, value: ResolvedCost | ResolvedPreviewValue, stage: RulesStage
    ) -> ResolutionLedger:
        if value.stage not in (
            ResolutionStage.PREVIEW_RESOLVED,
            ResolutionStage.SOURCE_RESOLVED,
        ):
            raise ValueError("value is not terminal at a resolved stage")
        if value.authority is ResolutionAuthority.DEBUG_ORACLE:
            raise ValueError("debug oracle is not a production rules authority")
        if stage not in (
            RulesStage.CURRENT_COST,
            RulesStage.CURRENT_HIT_CHANCE,
            RulesStage.CURRENT_DAMAGE_PROFILE,
        ):
            raise ValueError("preview cannot claim a downstream outcome stage")
        if isinstance(value, ResolvedCost) and stage is not RulesStage.CURRENT_COST:
            raise ValueError("cost value must own current cost stage")
        return cls(value.authority.value, (stage,))

    @classmethod
    def calculated(cls, model_version: str) -> ResolutionLedger:
        return cls(f"BB_AGENT_RULES:{_text(model_version)}", ())

    @classmethod
    def for_action_field(cls, action: ActionAffordance, field: str) -> ResolutionLedger:
        """Bind a canonical field to its owning stage, without caller stage guessing."""
        if field in {
            "ap_cost",
            "fatigue_cost",
            "charge_cost",
            "ammo_cost",
            "item_action_cost",
        }:
            return cls.from_resolved(getattr(action, field), RulesStage.CURRENT_COST)
        stage = {
            "displayed_hit_chance": RulesStage.CURRENT_HIT_CHANCE,
            "displayed_damage": RulesStage.CURRENT_DAMAGE_PROFILE,
        }.get(field)
        if stage is None:
            raise ValueError("field has no declared rules resolution stage")
        value = getattr(action.preview, field)
        if value is None:
            raise ValueError("field has no resolved preview value")
        return cls.from_resolved(value, stage)

    def apply(self, stage: RulesStage) -> Result[ResolutionLedger]:
        if not isinstance(stage, RulesStage):
            raise ValueError("unknown rules stage")
        order = list(RulesStage)
        if stage in self.completed or any(
            order.index(stage) < order.index(done) for done in self.completed
        ):
            return Result.validation_failure(
                Problem(
                    ErrorCode.RESOLUTION_STAGE_CONFLICT,
                    "rules stage already resolved or precedes resolved input",
                    stage.value,
                )
            )
        return Result.success(
            ResolutionLedger(self.authority, self.completed + (stage,))
        )
