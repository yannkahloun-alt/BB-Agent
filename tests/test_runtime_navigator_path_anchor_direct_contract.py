from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPAT = ROOT / "companion_mod/scripts/bb_agent/runtime_navigator_path_compat.nut"


def test_movement_mismatch_logs_engine_cost_anchors_before_failure() -> None:
    text = COMPAT.read_text(encoding="utf-8")
    for token in (
        "_oracleCostAnchorID",
        "_traceOracleCostAnchors",
        "native_cost_anchors label=",
        '"First"',
        '"SecondLastBeforeEnd"',
        '"LastBeforeEnd"',
        '"End"',
        'this._traceOracleCostAnchors("full", _costs);',
        'this._traceOracleCostAnchors("prefix_" + apBudget, prefix);',
    ):
        assert token in text

    full = text.index('this._traceOracleCostAnchors("full", _costs);')
    report = text.index("oracle.reportMovementTopologyMismatch(")
    failure = text.index(
        'throw "native movement prefix endpoint is not a canonical adjacent tile";'
    )
    assert full < report < failure
