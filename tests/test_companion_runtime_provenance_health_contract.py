from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
PROVENANCE = ROOT / "companion_mod/scripts/bb_agent/runtime_provenance.nut"
CAPTURE = ROOT / "companion_mod/scripts/bb_agent/capture_substrate.nut"


def test_capture_provenance_exposes_companion_version_directly() -> None:
    text = PROVENANCE.read_text(encoding="utf-8")
    preload = PRELOAD.read_text(encoding="utf-8")
    assert 'Version = "0.2.1"' in preload
    assert "capture.CompanionVersion <- ::BBAGENT_Mod.Version;" in text
    assert text.count("CompanionVersion = this.CompanionVersion") >= 2


def test_runtime_compatibility_allowlist_is_narrow_and_source_pin_is_unchanged() -> (
    None
):
    text = PROVENANCE.read_text(encoding="utf-8")
    capture = CAPTURE.read_text(encoding="utf-8")

    assert (
        'capture.SupportedRuntimeGameVersions <- ["1.5.2.2", "1.5.2.3"];' in text
    )
    assert "capture._isSupportedRuntimeGameVersion <- function" in text
    assert "if (!this._isSupportedRuntimeGameVersion(runtimeGameVersion))" in text
    assert "runtimeGameVersion != this.SupportedRuntimeGameVersion" not in text
    assert (
        'SupportedScriptsRevision = "162f498ac7c49b4c317bbf54718a595ecef6a65a"'
        in capture
    )
    assert (
        'SupportedGameVersion = "scripts-162f498ac7c49b4c317bbf54718a595ecef6a65a"'
        in capture
    )
    assert (
        'RulesetContentFingerprint = "4c4b714832d1989740a6f07dce058c11aa1e9123056966ede06ce42d1df182bd"'
        in capture
    )


def test_successful_runtime_provenance_refresh_clears_stale_health_error() -> None:
    text = PROVENANCE.read_text(encoding="utf-8")
    refresh = text[
        text.index("capture._refreshRuntimeProvenance <- function") : text.index(
            "capture.isRuntimeCompatible <- function"
        )
    ]

    failure = refresh.index("if (reason != null)")
    clear = refresh.index("this.State.LastError = null;", failure)
    success = refresh.index("return true;", clear)

    assert failure < clear < success
