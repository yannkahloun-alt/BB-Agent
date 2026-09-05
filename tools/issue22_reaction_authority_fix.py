from pathlib import Path


state_path = Path("src/bb_agent/tactical_state.py")
text = state_path.read_text(encoding="utf-8")
needle = '''    preview = action.get("preview")
    if not isinstance(preview, dict):
        return
'''
replacement = '''    reactions = action.get("contingent_reactions")
    if isinstance(reactions, list):
        for reaction in reactions:
            if not isinstance(reaction, dict):
                continue
            hit_chance = reaction.get("hit_chance")
            if isinstance(hit_chance, dict):
                hit_chance.pop("authority", None)

    preview = action.get("preview")
    if not isinstance(preview, dict):
        return
'''
if text.count(needle) != 1:
    raise SystemExit(f"unexpected authority-strip anchor count: {text.count(needle)}")
state_path.write_text(text.replace(needle, replacement, 1), encoding="utf-8")


test_path = Path("tests/test_trace.py")
text = test_path.read_text(encoding="utf-8")
old_import = (
    "from test_mechanics import _attack, _authority, _ordinary_attack_state, _snapshot, _wait\n"
)
new_import = '''from test_mechanics import (
    _attack,
    _authority,
    _move_action,
    _movement_state,
    _ordinary_attack_state,
    _reaction,
    _snapshot,
    _wait,
)
'''
if old_import not in text:
    raise SystemExit("test_mechanics import shape changed")
text = text.replace(old_import, new_import, 1)

addition = r'''


def test_contingent_reaction_authority_does_not_change_state_or_trace_identity():
    authority = _authority()
    base = _movement_state(authority, _move_action(reactions=(_reaction(),)))
    fixture_state = _with_affordance_diagnostic_metadata(
        base,
        "fixture-reaction-generation",
        AffordanceProvenance.HANDCRAFTED_FIXTURE,
        ResolutionAuthority.HANDCRAFTED_FIXTURE,
    )
    game_state = _with_affordance_diagnostic_metadata(
        base,
        "game-reaction-generation",
        AffordanceProvenance.GAME_PLAYER_AFFORDANCE,
        ResolutionAuthority.GAME_PLAYER_AFFORDANCE,
    )

    fixture_action = fixture_state.action_affordances.actions[0]
    game_action = game_state.action_affordances.actions[0]
    assert fixture_action.contingent_reactions
    assert game_action.contingent_reactions
    assert (
        fixture_action.contingent_reactions[0].hit_chance.authority
        is ResolutionAuthority.HANDCRAFTED_FIXTURE
    )
    assert (
        game_action.contingent_reactions[0].hit_chance.authority
        is ResolutionAuthority.GAME_PLAYER_AFFORDANCE
    )
    assert fixture_state.state_id == game_state.state_id
    assert fixture_action.action_id == game_action.action_id

    fixture_trace = run_decision_trace(authority, fixture_state)
    game_trace = run_decision_trace(authority, game_state)

    assert fixture_trace.input["canonical_state"] != game_trace.input["canonical_state"]
    assert fixture_trace.selection == game_trace.selection
    assert fixture_trace.output_fingerprint == game_trace.output_fingerprint
    assert fixture_trace.trace_id == game_trace.trace_id
'''
if "test_contingent_reaction_authority_does_not_change_state_or_trace_identity" in text:
    raise SystemExit("reaction-authority regression already present")
test_path.write_text(text + addition, encoding="utf-8")


doc_path = Path("docs/TRACE.md")
text = doc_path.read_text(encoding="utf-8")
needle = (
    "The trace still preserves the complete diagnostic action/state records. "
    "For output identity, candidate generation is projected to stable legal action IDs "
    "and coverage codes, while candidate evaluations omit diagnostic action provenance "
    "and the documentation-only feature ownership table. The canonical `state_id` already "
    "commits to the semantic command costs/previews and decision input.\n"
)
replacement = needle + (
    "Resolution-authority provenance is excluded consistently for resolved costs, "
    "player-visible previews, and contingent-reaction hit-chance previews; their "
    "resolved values/stages remain semantic inputs.\n"
)
if needle not in text:
    raise SystemExit("trace identity documentation anchor changed")
doc_path.write_text(text.replace(needle, replacement, 1), encoding="utf-8")
