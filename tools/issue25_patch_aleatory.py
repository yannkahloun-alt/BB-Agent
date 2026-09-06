from pathlib import Path

path = Path("tools/issue25_build_corpus.py")
text = path.read_text(encoding="utf-8")
old = '''    state = _movement_state(authority, move)\n    state = rebuild(\n        state,\n        raw_capture_id="t25-capture-aleatory",\n        action_affordances=replace(state.action_affordances, actions=(move, _wait())),\n    )\n'''
new = '''    state = _movement_state(authority, move)\n    state = rebuild(\n        state,\n        raw_capture_id="t25-capture-aleatory",\n        tiles=tuple(\n            replace(\n                tile,\n                blocking=KnownValue.exact(False),\n                traversable=KnownValue.exact(True),\n                blocks_line_of_sight=KnownValue.exact(False),\n            )\n            for tile in state.tiles\n        ),\n        action_affordances=replace(state.action_affordances, actions=(move, _wait())),\n    )\n'''
assert old in text
path.write_text(text.replace(old, new), encoding="utf-8")
