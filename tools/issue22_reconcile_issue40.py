from pathlib import Path


state_path = Path("src/bb_agent/tactical_state.py")
text = state_path.read_text(encoding="utf-8")
wrong_block = '''    reactions = action.get("contingent_reactions")
    if isinstance(reactions, list):
        for reaction in reactions:
            if not isinstance(reaction, dict):
                continue
            hit_chance = reaction.get("hit_chance")
            if isinstance(hit_chance, dict):
                hit_chance.pop("authority", None)

'''
if text.count(wrong_block) != 1:
    raise SystemExit(f"unexpected contingent authority strip count: {text.count(wrong_block)}")
state_path.write_text(text.replace(wrong_block, "", 1), encoding="utf-8")


test_path = Path("tests/test_trace.py")
text = test_path.read_text(encoding="utf-8")
old_name = "def test_contingent_reaction_authority_does_not_change_state_or_trace_identity():"
new_name = "def test_contingent_reaction_authority_remains_semantic_state_and_trace_identity():"
if text.count(old_name) != 1:
    raise SystemExit("reaction-authority trace regression name changed")
text = text.replace(old_name, new_name, 1)
old_assertions = '''    assert fixture_state.state_id == game_state.state_id
    assert fixture_action.action_id == game_action.action_id

    fixture_trace = run_decision_trace(authority, fixture_state)
    game_trace = run_decision_trace(authority, game_state)

    assert fixture_trace.input["canonical_state"] != game_trace.input["canonical_state"]
    assert fixture_trace.selection == game_trace.selection
    assert fixture_trace.output_fingerprint == game_trace.output_fingerprint
    assert fixture_trace.trace_id == game_trace.trace_id
'''
new_assertions = '''    assert fixture_action.action_id == game_action.action_id
    assert fixture_state.state_id != game_state.state_id

    fixture_trace = run_decision_trace(authority, fixture_state)
    game_trace = run_decision_trace(authority, game_state)

    assert fixture_trace.input["canonical_state"] != game_trace.input["canonical_state"]
    assert fixture_trace.selection == game_trace.selection
    assert fixture_trace.output_fingerprint != game_trace.output_fingerprint
    assert fixture_trace.trace_id != game_trace.trace_id
'''
if text.count(old_assertions) != 1:
    raise SystemExit("reaction-authority trace assertions changed")
test_path.write_text(text.replace(old_assertions, new_assertions, 1), encoding="utf-8")


doc_path = Path("docs/TRACE.md")
text = doc_path.read_text(encoding="utf-8")
old_bullet = "- affordance capture/provenance/debug metadata and resolution-authority labels that the canonical state contract deliberately excludes from `state_id`;\n"
new_bullet = "- affordance capture/provenance/debug metadata and current-action cost/preview authority labels that the canonical state contract deliberately excludes from `state_id`;\n"
if text.count(old_bullet) != 1:
    raise SystemExit("identity exclusion bullet changed")
text = text.replace(old_bullet, new_bullet, 1)
old_sentence = "Resolution-authority provenance is excluded consistently for resolved costs, player-visible previews, and contingent-reaction hit-chance previews; their resolved values/stages remain semantic inputs.\n"
new_sentence = (
    "Current-action resolved cost and player-visible preview authority labels are "
    "provenance-only for canonical state identity. Contingent reactions are the "
    "intentional #40 exception: reaction consequences do not redefine `action_id`, "
    "but supplied reaction facts, including hit-chance resolution authority, remain "
    "part of canonical state/evaluation identity and therefore trace identity.\n"
)
if text.count(old_sentence) != 1:
    raise SystemExit("reaction authority documentation sentence changed")
doc_path.write_text(text.replace(old_sentence, new_sentence, 1), encoding="utf-8")
