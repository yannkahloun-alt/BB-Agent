from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = ROOT / "companion_mod/scripts/bb_agent"
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
VALIDATION = SCRIPT_ROOT / "runtime_debug_oracle_movement_validation.nut"
FATIGUE = SCRIPT_ROOT / "runtime_debug_oracle_movement_validation_fatigue.nut"
LEGALITY = SCRIPT_ROOT / "runtime_debug_oracle_movement_validation_legality.nut"
GEOMETRY = SCRIPT_ROOT / "runtime_debug_oracle_movement_validation_geometry.nut"
REMEMBERED = SCRIPT_ROOT / "runtime_debug_oracle_movement_validation_remembered.nut"
INSTALLER = ROOT / "tools/install_combat_sandbox.ps1"


def test_combat_sandbox_installer_tracks_companion_version() -> None:
    preload = PRELOAD.read_text(encoding="utf-8")
    installer = INSTALLER.read_text(encoding="utf-8")
    version = re.search(r'Version = "([0-9.]+)"', preload)
    assert version is not None
    version_text = version.group(1)
    escaped_version = version_text.replace(".", r"\.")
    assert f'Version = "{escaped_version}"' in installer
    assert f"companion: {version_text}" in installer


def test_native_movement_validation_loads_after_ally_probe_before_export() -> None:
    preload = PRELOAD.read_text(encoding="utf-8")
    roster = preload.index("runtime_debug_oracle_ally_jump_roster_probe")
    validation = preload.index("runtime_debug_oracle_movement_validation")
    fatigue = preload.index("runtime_debug_oracle_movement_validation_fatigue")
    legality = preload.index("runtime_debug_oracle_movement_validation_legality")
    geometry = preload.index("runtime_debug_oracle_movement_validation_geometry")
    remembered = preload.index("runtime_debug_oracle_movement_validation_remembered")
    export = preload.index("scripts/bb_agent/live_export")
    assert roster < validation < fatigue < legality < geometry < remembered < export


def test_native_movement_validation_is_debug_only_and_staged() -> None:
    text = VALIDATION.read_text(encoding="utf-8")
    assert "MovementValidationSampleCap <- 6" in text
    assert "if (!oracle.Enabled) return ret;" in text
    assert 'if (_job.kind == "movement_validation_sample")' in text
    assert '"debug_oracle_disabled"' in text
    assert '"movement_validation_sample"' in text
    assert '"debug_movement_validation"' in text
    assert "foreach (index, sample in samples)" in text


def test_native_movement_validation_samples_bounded_representative_roles() -> None:
    text = VALIDATION.read_text(encoding="utf-8")
    for role in (
        "nearest_reachable",
        "farthest_reachable",
        "highest_cost_reachable",
        "zoc_entry",
        "zoc_exit",
        "model_unreachable_visible",
    ):
        assert role in text
    assert "if (!tile.IsEmpty) continue;" in text


def test_native_calls_only_exist_in_debug_validation_sample_path() -> None:
    text = VALIDATION.read_text(encoding="utf-8")
    sample_start = text.index("oracle._movementValidationSample <- function")
    process_start = text.index("local originalSandboxProcessJob")
    sample = text[sample_start:process_start]
    assert "navigator.findPath(" in sample
    assert "navigator.getCostForPath(" in sample
    assert "reachability_agreement" in sample
    assert "cost_agreement" in sample

    production_graph = (SCRIPT_ROOT / "runtime_movement_graph_compat.nut").read_text(
        encoding="utf-8"
    )
    assert "findPath(" not in production_graph
    assert "getCostForPath(" not in production_graph


def test_native_validation_distinguishes_path_and_execution_fatigue() -> None:
    text = FATIGUE.read_text(encoding="utf-8")
    for required in (
        "_movementValidationPathFatigue",
        "matched.step.path_fatigue",
        "model_execution_fatigue",
        "model_path_fatigue",
        "native_matches_execution_fatigue",
        "native_matches_path_fatigue",
    ):
        assert required in text
    assert "findPath(" not in text
    assert "getCostForPath(" not in text


def test_native_validation_separates_legality_from_resource_reachability() -> None:
    text = LEGALITY.read_text(encoding="utf-8")
    for required in (
        "_movementValidationLegalTiles",
        "model_legal",
        "native_found",
        "legality_agreement",
        "model_legal_resource_unreachable",
    ):
        assert required in text
    assert "findPath(" not in text
    assert "getCostForPath(" not in text


def test_native_validation_compares_bounded_path_geometry_summaries() -> None:
    text = GEOMETRY.read_text(encoding="utf-8")
    for required in (
        "_movementValidationModelPath",
        "model_path_tile_ids",
        "model_first_tile_id",
        "model_end_tile_id",
        "tile_count_agreement",
        "endpoint_agreement",
    ):
        assert required in text
    assert "findPath(" not in text
    assert "getCostForPath(" not in text


def test_remembered_validation_reuses_incremental_tile_discovery() -> None:
    text = REMEMBERED.read_text(encoding="utf-8")
    for required in (
        "RememberedMovementValidationSampleCap <- 2",
        'tile.visibility != "REMEMBERED"',
        'role = "remembered_nearest"',
        'role = "remembered_farthest"',
        "native_tile_by_id",
        "tile_discovery_complete",
        "remembered_validation_requested",
        "remembered_validation_plan_scheduled",
        "originalProcessDiscovery",
        'isTile = _job.kind == "discover_tile"',
        "_scheduleRememberedMovementValidationPlan",
    ):
        assert required in text
    assert "getMapSize()" not in text
    assert "for (local x" not in text
    assert "for (local y" not in text


def test_remembered_validation_is_debug_only_and_native_calls_are_sample_scoped() -> (
    None
):
    text = REMEMBERED.read_text(encoding="utf-8")
    assert "if (!oracle.Enabled || this.State == null) return;" in text
    sample_start = text.index("oracle._rememberedMovementValidationSample <- function")
    schedule_start = text.index("sandbox._scheduleRememberedMovementValidationPlan")
    sample = text[sample_start:schedule_start]
    assert "navigator.findPath(" in sample
    assert "navigator.getCostForPath(" in sample
    rest = text[:sample_start] + text[schedule_start:]
    assert "navigator.findPath(" not in rest
    assert "navigator.getCostForPath(" not in rest
