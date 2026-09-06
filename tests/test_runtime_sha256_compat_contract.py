from __future__ import annotations

import base64
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
SHA_COMPAT = ROOT / "companion_mod/scripts/bb_agent/runtime_sha256_compat.nut"

REAL_STREAM_START_B64 = (
    "eyJjYXB0dXJlX2NvbnRyYWN0X3ZlcnNpb24iOiJiYi1hZ2VudC1saXZlLWNhcHR1cmUudjEiLCJj"
    "b21wYW5pb25fdmVyc2lvbiI6IjAuMi40IiwiZW52ZWxvcGVfdmVyc2lvbiI6ImJiLWFnZW50LWxp"
    "dmUtZW52ZWxvcGUudjEiLCJrZXJuZWxfaWRlbnRpdHkiOnsiYWN0aW9uX2FmZm9yZGFuY2UiOiJp"
    "c3N1ZS00LmFtZW5kZWQtYnktMTMuY29udGluZ2VudC1yZWFjdGlvbnMtMTkuaWRlbnRpdHktNDAi"
    "LCJkZWNpc2lvbl90cmFjZV9jb250cmFjdCI6Imlzc3VlLTcuYW1lbmRlZC1ieS0xMyIsImV2YWx1"
    "YXRpb25fY29uZmlnIjoibTEtZXZhbHVhdGlvbi1wcm9maWxlLnYyIiwiZXZhbHVhdGlvbl9jb250"
    "cmFjdCI6Imlzc3VlLTUuYW1lbmRlZC1ieS0xMyIsImV2YWx1YXRpb25fcHJvZmlsZV9maW5nZXJw"
    "cmludCI6IjJlMGZmNThjNGM1N2E4MGRjMzdlYjg2ZGE1ZDQ5ZWY1NzMwNTdhYmQ3M2ViMTU4ODAx"
    "ZjVjNjAwYzBjNmZmY2IiLCJldmFsdWF0b3JfbW9kZWwiOiJyaXNrLWV2YWx1YXRvci52MSIsImlu"
    "Zm9ybWF0aW9uX3BvbGljeSI6Imlzc3VlLTIuYW1lbmRlZC1ieS0xMyIsIm0xX3NwZWMiOiJpc3N1"
    "ZXMtMS10aHJvdWdoLTEzLmZyZWV6ZS0xIiwibWVjaGFuaWNzX21hbmlmZXN0IjoiYmItYWdlbnQt"
    "bWVjaGFuaWNzLW1hbmlmZXN0LnYxIiwibWVjaGFuaWNzX21hbmlmZXN0X2ZpbmdlcnByaW50Ijoi"
    "OWY2OTJiYWY3MzE0NWVhZDViZTY1NGM1MDQ0YzE2Y2Y3MGM4ZDVkN2RhZDgzZWNlOTUyNWJhZTI1"
    "MmJiNjdlOCIsIm91dGNvbWVfbW9kZWwiOiJvcmRpbmFyeS1hdHRhY2sudjEiLCJ0YWN0aWNhbF9z"
    "dGF0ZSI6Imlzc3VlLTMuYW1lbmRlZC1ieS0xMy5jb250aW5nZW50LXJlYWN0aW9ucy0xOS5pZGVu"
    "dGl0eS00MCIsInRyYWNlX3NjaGVtYSI6ImJiLWFnZW50LWRlY2lzaW9uLXRyYWNlLnYxIiwidW5j"
    "ZXJ0YWludHlfY29udHJhY3QiOiJpc3N1ZS02LmFtZW5kZWQtYnktMTMiLCJ1bml0X3ZhbHVlX3Bv"
    "bGljeV9maW5nZXJwcmludCI6IjE3MGY1NDBiM2Y3NmNiMDFjYTg4MDQ4ZGNiMTNjYjY2ZjU3Zjk2"
    "YjJlYTQ2NGM2YTEyMjI5MjMwOTE3OWMyYjciLCJ1bml0X3ZhbHVlX3BvbGljeV92ZXJzaW9uIjoi"
    "bTEtY29tbW9uLXByZXNlcnZhdGlvbi52MSJ9LCJtb2RzIjpbImRsY19saW5kd3VybUAxLjAuMCIs"
    "Im1vZF9iYl9hZ2VudF9jYXB0dXJlQDAuMi40IiwibW9kX21vZGVybl9ob29rc0AwLjYuMCIsInZh"
    "bmlsbGFAMS41LjItMyJdLCJyZWNvcmRfdHlwZSI6IlNUUkVBTV9TVEFSVCIsInJ1bGVzZXRfY29u"
    "dGVudF9maW5nZXJwcmludCI6IjRjNGI3MTQ4MzJkMTk4OTc0MGE2ZjA3ZGNlMDU4YzExYWExZTkx"
    "MjMwNTY5NjZlZGUwNmNlNDJkMWRmMTgyYmQiLCJydWxlc2V0X2dhbWVfdmVyc2lvbiI6InNjcmlw"
    "dHMtMTYyZjQ5OGFjN2M0OWI0YzMxN2JiZjU0NzE4YTU5NWVjZWY2YTY1YSIsInJ1bnRpbWVfZ2Ft"
    "ZV92ZXJzaW9uIjoiMS41LjIuMyJ9"
)
OLD_BAD_DIGEST = "d723a68172c470ce9080e2c87eda76966c624af7a68533dd1403445081ef8b4a"
EXPECTED_DIGEST = "60e2d13e0327065b63639980da9aa008d8e41cc653cc4445395889044ce49060"


def test_sha_compat_loads_before_tactical_hook() -> None:
    preload = PRELOAD.read_text(encoding="utf-8")
    join_compat = preload.index('::include("scripts/bb_agent/runtime_join_compat")')
    sha_compat = preload.index('::include("scripts/bb_agent/runtime_sha256_compat")')
    hook = preload.index('::include("scripts/bb_agent/hooks/tactical_state")')
    assert join_compat < sha_compat < hook


def test_sha_compat_uses_explicit_logical_right_shift() -> None:
    text = SHA_COMPAT.read_text(encoding="utf-8")
    assert "wire._ushr <- function(_value, _bits)" in text
    assert "return (_value >> _bits) & (2147483647 >> (_bits - 1));" in text
    assert "this._ushr(this._u32(_value), _bits)" in text
    assert "this._ushr(this._u32(w[i - 15]), 3)" in text
    assert "this._ushr(this._u32(w[i - 2]), 10)" in text


def test_real_stream_start_reference_digest() -> None:
    payload = base64.urlsafe_b64decode(REAL_STREAM_START_B64 + "==")
    assert len(payload) == 1446
    assert hashlib.sha256(payload).hexdigest() == EXPECTED_DIGEST
    assert OLD_BAD_DIGEST != EXPECTED_DIGEST


def test_sha_compat_preserves_safety_boundary() -> None:
    text = SHA_COMPAT.read_text(encoding="utf-8")
    for forbidden in (
        "Math.rand(",
        "::Math.rand(",
        ".payForAction(",
        ".equip(",
        ".unequip(",
        ".swap(",
        ".use(",
        ".wait(",
        ".endTurn(",
        "getNavigator().travel(",
        "DEBUG_GROUND_TRUTH",
        "DEBUG_ORACLE",
        "omniscient_debug",
    ):
        assert forbidden not in text
