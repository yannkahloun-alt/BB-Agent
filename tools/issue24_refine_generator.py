from pathlib import Path

path = Path("tools/issue24_generate_corpus.py")
text = path.read_text()
block = '''                    "required_explanations": [
                        {"action_id": move.action_id, "component_ids": ["position_control_protection"]}
                    ],
'''
if block not in text:
    raise SystemExit("formation explanation block not found")
path.write_text(text.replace(block, "", 1))
