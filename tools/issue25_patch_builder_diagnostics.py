from pathlib import Path

path = Path("tools/issue25_build_corpus.py")
text = path.read_text(encoding="utf-8")
old = "    assert report.passed, report.blocking_failures\n"
new = """    if not report.passed:\n        for fixture_report in report.fixtures:\n            for failure in fixture_report.blocking_failures:\n                print(\n                    \"FAIL\",\n                    fixture_report.fixture_id,\n                    failure.assertion_id,\n                    failure.message,\n                )\n        raise AssertionError(\"combined #24/#25 corpus has blocking failures\")\n"""
assert old in text
path.write_text(text.replace(old, new), encoding="utf-8")
