from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVENANCE = ROOT / "companion_mod/scripts/bb_agent/runtime_provenance.nut"


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
