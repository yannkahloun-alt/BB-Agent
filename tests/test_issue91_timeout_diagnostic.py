from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRACTOR = ROOT / "tools/extract_live_ready_timing.py"
VALIDATOR = ROOT / "tools/validate_live_production.ps1"


def test_extractor_writes_diagnostic_json_when_no_complete_pair() -> None:
    text = EXTRACTOR.read_text(encoding="utf-8")
    assert '"diagnostic_status": "no_complete_ready_timing_pair"' in text
    assert '"diagnostic_error": str(exc)' in text
    assert "_write_json(args.out, diagnostic)" in text
    assert "return 2" in text


def test_validator_preserves_incomplete_pair_diagnostic_json() -> None:
    text = VALIDATOR.read_text(encoding="utf-8")
    assert "if ($null -ne $timing)" in text
    assert "Diagnostic JSON preserved: $Out" in text
    assert "companion_version -NotePropertyValue '0.2.38'" in text
    assert "source_commit -NotePropertyValue $head" in text
